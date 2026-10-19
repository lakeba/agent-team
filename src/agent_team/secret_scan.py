"""A secret check before every push the team makes.

Before `build` or `fix` commits, the staged changes are scanned for credentials: known key and
token formats, private keys, files that hold secrets (.env, *.pem ...), and any value saved in
agent-team's own keys file. Anything found stops the commit and the push; the report names the
file, line and kind of secret, never the value.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath

from . import github, keys
from .config import CONFIG_NAME, looks_like_secret

PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("Slack webhook", re.compile(r"hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----")),
]
KEY_ENV_LINE = re.compile(r"""^\s*api_key_env\s*=\s*(["'])(.*)\1""")
SECRET_FILES = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_ed25519", "*.keystore", ".npmrc",
                ".pypirc")
ALLOWED_FILES = (".env.example", ".env.sample", ".env.template")


def scan_text(path: str, added: list[tuple[int, str]]) -> list[str]:
    """Findings in a file's added lines: 'path:line: kind' (never the value)."""
    found = []
    saved = [v for v in keys.read().values() if len(v) >= 12]
    for n, line in added:
        for kind, rx in PATTERNS:
            if rx.search(line):
                found.append(f"{path}:{n}: looks like a {kind}")
        if any(v in line for v in saved):
            found.append(f"{path}:{n}: contains a value from agent-team's keys file")
        m = KEY_ENV_LINE.match(line) if PurePosixPath(path).name == CONFIG_NAME else None
        if m and looks_like_secret(m.group(2)):
            found.append(f"{path}:{n}: api_key_env holds what looks like a key, not a variable's name")
    return found


def secret_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name not in ALLOWED_FILES and any(fnmatch.fnmatch(name, p) for p in SECRET_FILES)


def _added_lines(diff: str) -> dict[str, list[tuple[int, str]]]:
    """{path: [(line number, text)]} for the + lines of a unified diff."""
    out: dict[str, list[tuple[int, str]]] = {}
    path, line = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            path = target[2:] if target.startswith("b/") else None
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", raw)
        if m:
            line = int(m.group(1))
            continue
        if path is None:
            continue
        if raw.startswith("+"):
            out.setdefault(path, []).append((line, raw[1:]))
            line += 1
        elif not raw.startswith("-"):
            line += 1
    return out


def check_staged(root) -> list[str]:
    """Findings in what's staged for commit in `root`."""
    names = github.git(root, "diff", "--cached", "--name-only", "--diff-filter=AM", check=False).split()
    findings = [f"{p}: files like this hold secrets and are never committed by the team" for p in names if secret_file(p)]
    diff = github.git(root, "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=AM", check=False)
    for path, added in _added_lines(diff).items():
        findings += scan_text(path, added)
    return findings


def guard(root) -> None:
    """Stop before committing if the staged changes hold a secret; unstage them first."""
    findings = check_staged(root)
    if findings:
        github.git(root, "reset", "-q", check=False)
        raise SystemExit("Not committed or pushed: the changes look like they contain secrets.\n  "
                         + "\n  ".join(findings[:20])
                         + "\nRemove them (keep secrets in environment variables) and try again.")
