"""`agent-team audit`: the team's own setup as an attack surface.

The prompts, skills, rules, tool servers, permissions and agent files a team works from are
instructions to models, so a poisoned skill or an over-broad permission matters as much as a bug.
This looks at:

  - .team.toml: remote members without TLS, tool servers started from unpinned packages, secrets
    written into it, members that write code with tools to run commands
  - the skills, rules and prompts members read, and the project's agent files (CLAUDE.md,
    AGENTS.md, .claude/agents/, .cursorrules, Copilot instructions): hidden characters, text that
    tries to override instructions, commands that pipe downloads into a shell, requests to send
    data out or read keys
  - Claude Code's project settings and .mcp.json: permission bypass, allow-everything rules, hooks
    that reach the network, secrets in server environments
  - files git tracks that look like keys or hold credentials

Each finding has a severity; the result is a score out of 100 and a grade.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from . import secret_scan
from .config import CONFIG_NAME, Team

WEIGHT = {"critical": 25, "high": 10, "medium": 4, "low": 1}
ORDER = ["critical", "high", "medium", "low"]

AGENT_FILES = ["CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules", ".windsurfrules", ".github/copilot-instructions.md"]
AGENT_DIRS = [".claude/agents", ".claude/commands", ".claude/skills", ".cursor/rules", "team/skills", "team/rules",
              "team/prompts"]
HIDDEN = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
INJECTION = [
    (re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|system|your)\b"
                r"[^.\n]{0,20}\b(instructions?|rules?|prompts?|guidelines?)", re.I), "high",
     "text that tries to override the model's instructions"),
    (re.compile(r"\b(do not|don't|never)\s+(tell|inform|mention|reveal)[^.\n]{0,30}\b(user|owner|human)", re.I), "high",
     "text that asks the model to hide something from the user"),
    (re.compile(r"\b(curl|wget|iwr|Invoke-WebRequest)\b[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z|da)?sh\b", re.I), "high",
     "a command that pipes a download into a shell"),
    (re.compile(r"(~|\$HOME)/\.(ssh|aws|gnupg|kube|docker)/|id_rsa|\.npmrc|\.pypirc", re.I), "medium",
     "a reference to credential files"),
    (re.compile(r"\b(send|post|upload|exfiltrate|forward)\b[^.\n]{0,60}\b(api[_ -]?keys?|tokens?|secrets?|credentials?|"
                r"passwords?|\.env)\b", re.I), "high", "text that asks the model to send secrets somewhere"),
    (re.compile(r"\bbase64\s+(-d|--decode)\b|[A-Za-z0-9+/]{200,}={0,2}"), "medium",
     "encoded content a reader can't check"),
]
NETWORK_CMD = re.compile(r"\b(curl|wget|nc|ncat|netcat|ssh|scp|Invoke-WebRequest|iwr)\b")
UNPINNED_NPX = re.compile(r"^(@?[\w.-]+(/[\w.-]+)?)$")      # a package name without @version


@dataclass
class Finding:
    severity: str
    where: str
    what: str
    fix: str = ""


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:500_000]
    except OSError:
        return ""


def scan_instructions(rel: str, text: str) -> list[Finding]:
    """Findings in a file that models read as instructions."""
    out = []
    hidden = HIDDEN.findall(text)
    if hidden:
        out.append(Finding("high", rel, f"{len(hidden)} hidden or direction-changing characters (text a person "
                           f"doesn't see but a model reads)", "remove them; review the file in a hex viewer"))
    for n, line in enumerate(text.splitlines(), 1):
        for pattern, sev, what in INJECTION:
            if pattern.search(line):
                out.append(Finding(sev, f"{rel}:{n}", what, f"read the line and remove it unless it's meant: "
                                                              f"{line.strip()[:100]!r}"))
    return out


def _npx_unpinned(command: str, args: list[str]) -> str:
    if Path(command).name not in ("npx", "bunx", "pnpx", "uvx", "pipx"):
        return ""
    pkgs = [a for a in args if not a.startswith("-")]
    pkg = pkgs[0] if pkgs else ""
    if Path(command).name == "pipx" and pkgs[:1] == ["run"]:
        pkg = pkgs[1] if len(pkgs) > 1 else ""
    name = pkg.split("@", 2)
    pinned = (pkg.startswith("@") and len(name) == 3) or (not pkg.startswith("@") and "@" in pkg) or "==" in pkg
    return "" if not pkg or pinned else pkg


def scan_team(team: Team) -> list[Finding]:
    out = []
    raw = _text(team.root / CONFIG_NAME)
    for n, hit in enumerate(secret_scan.scan_text(CONFIG_NAME, list(enumerate(raw.splitlines(), 1)))):
        out.append(Finding("critical", CONFIG_NAME, f"a credential written into the team file ({hit.split(': ', 1)[-1]})",
                           "move it to `agent-team keys set NAME` and name the variable instead"))
    for p in team.providers.values():
        if p.kind == "agent-http" and p.url.startswith("http://") and not re.match(r"http://(127\.|localhost|\[::1\])", p.url):
            out.append(Finding("high", f"[providers.{p.name}]", f"a remote member reached without TLS ({p.url}): its "
                               f"token and the project's code cross the network in clear", "serve it over https"))
        if p.kind == "agent-http" and not p.api_key_env:
            out.append(Finding("high", f"[providers.{p.name}]", "a remote member with no token",
                               "set api_key_env to the variable holding the node's token"))
    for s in team.mcp.values():
        pkg = _npx_unpinned(s.command, s.args)
        if pkg:
            out.append(Finding("medium", f"[mcp.{s.name}]", f"started from the unpinned package {pkg!r}: a new "
                               f"release runs without review", f"pin a version, e.g. {pkg}@1.2.3"))
        for k, v in s.env.items():
            if secret_scan.scan_text("env", [(1, f"{k}={v}")]) or re.search(r"(KEY|TOKEN|SECRET|PASSWORD)", k, re.I):
                out.append(Finding("critical", f"[mcp.{s.name}].env.{k}", "a secret written into the team file",
                                   "use env_from with the variable's name and keep the value in `agent-team keys`"))
    for a in team.agents.values():
        tools = [t for m in a.mcp for t in team.mcp[m].tools]
        risky = [t for t in tools if re.search(r"(shell|exec|run_command|terminal|bash|write_file|delete)", t, re.I)]
        if risky and a.role in ("builder", "qa", "docs"):
            out.append(Finding("medium", f"member {a.name}", f"writes code and can call {', '.join(risky[:3])}",
                               "give command tools to reviewers only, or run with [sandbox] mode = \"container\""))
    if team.sandbox.mode == "off":
        out.append(Finding("low", "[sandbox]", "tests the team writes run on this machine",
                           "[sandbox] mode = \"container\" runs them in a throwaway container"))
    if not team.project.protect_config or not team.project.gate_sensitive:
        off = [k for k in ("protect_config", "gate_sensitive") if not getattr(team.project, k)]
        out.append(Finding("medium", "[project]", f"guards turned off: {', '.join(off)}", "turn them back on"))
    return out


def _instruction_files(team: Team) -> list[Path]:
    root = team.root
    paths = [root / f for f in AGENT_FILES if (root / f).is_file()]
    for d in AGENT_DIRS:
        if (root / d).is_dir():
            paths += [p for p in (root / d).rglob("*") if p.is_file() and p.suffix in (".md", ".mdc", ".txt", ".toml")]
    for a in team.agents.values():
        if a.prompt:
            paths.append(root / a.prompt)
        for entry in a.skills:
            p = Path(entry).expanduser()
            p = p if p.is_absolute() else root / p
            paths.append(p / "SKILL.md" if p.is_dir() else p)
    for entry in team.project.rules:
        p = Path(entry).expanduser()
        p = p if p.is_absolute() else root / p
        paths += sorted(p.glob("*.md")) if p.is_dir() else [p]
    seen, out = set(), []
    for p in paths:
        r = p.resolve()
        if r not in seen and p.is_file() and p.name != "NOTICE.md":
            seen.add(r)
            out.append(p)
    return out


def _rel(team: Team, p: Path) -> str:
    try:
        return p.resolve().relative_to(team.root.resolve()).as_posix()
    except ValueError:
        return str(p)


def scan_claude(team: Team) -> list[Finding]:
    out = []
    for name in (".claude/settings.json", ".claude/settings.local.json"):
        path = team.root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(_text(path))
        except ValueError:
            out.append(Finding("low", name, "isn't valid JSON"))
            continue
        perms = data.get("permissions") or {}
        if perms.get("defaultMode") in ("bypassPermissions",) or data.get("dangerouslySkipPermissions"):
            out.append(Finding("high", name, "permission checks are bypassed for this project",
                               "remove bypassPermissions; allow the specific commands instead"))
        for rule in perms.get("allow") or []:
            if rule in ("Bash", "Bash(*)", "Bash(*:*)", "*") or re.fullmatch(r"Bash\((sudo|rm|curl|sh|bash)[^)]*\)", rule):
                out.append(Finding("high", name, f"allows {rule!r} without asking", "narrow it to the commands needed"))
        for event, entries in (data.get("hooks") or {}).items():
            for entry in entries or []:
                for h in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
                    cmd = str(h.get("command", ""))
                    if NETWORK_CMD.search(cmd):
                        out.append(Finding("high", f"{name} hooks.{event}", f"a hook reaches the network: {cmd[:100]!r}",
                                           "make sure you know where it sends what"))
    path = team.root / ".mcp.json"
    if path.is_file():
        try:
            servers = (json.loads(_text(path)).get("mcpServers") or {})
        except ValueError:
            servers = {}
        for name, s in servers.items():
            pkg = _npx_unpinned(str(s.get("command", "")), [str(a) for a in s.get("args") or []])
            if pkg:
                out.append(Finding("medium", f".mcp.json {name}", f"started from the unpinned package {pkg!r}",
                                   f"pin a version, e.g. {pkg}@1.2.3"))
            for k, v in (s.get("env") or {}).items():
                if isinstance(v, str) and v and not v.startswith("${") and re.search(r"(KEY|TOKEN|SECRET|PASSWORD)", k, re.I):
                    out.append(Finding("critical", f".mcp.json {name}.env.{k}", "a secret written into a file git may track",
                                       "reference an environment variable: \"${NAME}\""))
    return out


def scan_secrets(team: Team) -> list[Finding]:
    try:
        r = subprocess.run(["git", "-C", str(team.root), "ls-files"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for rel in r.stdout.splitlines()[:20_000]:
        if secret_scan.secret_file(rel):
            out.append(Finding("critical", rel, "a key or secrets file is tracked by git",
                               "remove it from git (and its history), rotate what it held, add it to .gitignore"))
            continue
        p = team.root / rel
        if p.suffix.lower() in (".png", ".jpg", ".gif", ".ico", ".woff", ".woff2", ".lock", ".pdf", ".zip") or not p.is_file():
            continue
        try:
            if p.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        in_tests = bool(re.search(r"(^|/)(tests?|spec|__tests__|fixtures?)/", rel))
        for hit in secret_scan.scan_text(rel, list(enumerate(_text(p).splitlines(), 1)))[:3]:
            out.append(Finding("medium" if in_tests else "critical", hit.split(": ")[0], f"looks like a credential ({hit.split(': ', 1)[-1]})",
                               "remove it, rotate it, and keep it in `agent-team keys` or your secret store"))
    return out


def run(team: Team) -> dict:
    findings = scan_team(team) + scan_claude(team) + scan_secrets(team)
    files = _instruction_files(team)
    for p in files:
        findings += scan_instructions(_rel(team, p), _text(p))
    findings.sort(key=lambda f: (ORDER.index(f.severity), f.where))
    score = max(0, 100 - sum(WEIGHT[f.severity] for f in findings))
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    return {"score": score, "grade": grade, "files_read": len(files),
            "counts": {s: sum(f.severity == s for f in findings) for s in ORDER},
            "findings": [asdict(f) for f in findings]}
