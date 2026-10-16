"""Security from the outside: what the built program would actually ship.

Reviewing source finds most problems, but what users receive is the build output: a bundle, an
assembly, a published folder. After the lead approves a build, this looks at what the behaviour
checks' `prepare` steps built (out/, dist/, publish/, ...) and at the strings REA read from built
.NET assemblies, and reports what shouldn't ship: credentials and tokens, internal addresses
(localhost, private networks, staging hosts), and source maps that publish the original code.
The security member reviews with these findings.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import secret_scan
from .config import Team

BUILD_DIRS = ("out", "dist", "build", "publish", "bin/Release", ".next/static", ".output/public", "public/build")
INTERNAL = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
                      r"172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|[\w.-]*\b(?:staging|internal|intranet)\b[\w.-]*)[^\s\"'<>]*")
STRINGS = re.compile(rb"[\x20-\x7e]{6,}")
MAX_FILES, MAX_BYTES = 3000, 5_000_000


def _lines(path: Path) -> list[str]:
    data = path.read_bytes()[:MAX_BYTES]
    if b"\0" in data[:4096]:   # binary: its printable strings
        return [m.decode("ascii") for m in STRINGS.findall(data)]
    return data.decode("utf-8", errors="replace").splitlines()


def scan_lines(label: str, lines: list[str]) -> list[str]:
    found = secret_scan.scan_text(label, list(enumerate(lines, 1)))
    for n, line in enumerate(lines, 1):
        for url in INTERNAL.findall(line):
            found.append(f"{label}:{n}: internal address {url[:120]}")
    return found


def scan(team: Team, outcomes: list | None = None) -> str:
    """Findings in the build output and in REA's evidence, as Markdown ("" when nothing was built)."""
    root = Path(team.root)
    findings: list[str] = []
    looked: list[str] = []
    for rel in BUILD_DIRS:
        folder = root / rel
        if not folder.is_dir():
            continue
        files = [p for p in sorted(folder.rglob("*")) if p.is_file()][:MAX_FILES]
        looked.append(f"{rel}/ ({len(files)} files)")
        for p in files:
            label = p.relative_to(root).as_posix()
            if p.suffix == ".map":
                findings.append(f"{label}: a source map ships the original source code")
                continue
            try:
                findings += scan_lines(label, _lines(p))
            except OSError:
                continue
    for o in outcomes or []:   # strings compiled into .NET assemblies, as REA read them
        evidence = getattr(o.work, "evidence", None) or {}
        strings = (evidence.get("normalized_result") or {}).get("user_strings") or []
        if isinstance(strings, dict):   # REA: {"state": ..., "literals": [{"value": ...}, ...]}
            strings = strings.get("literals") or []
        texts = [s.get("value", s.get("text", "")) if isinstance(s, dict) else str(s) for s in strings]
        if texts:
            looked.append(f"{len(texts)} strings in the built assembly of {o.name!r}")
            findings += scan_lines(f"{o.name} (assembly strings)", [t for t in texts if t])
    if not looked:
        return ""
    unique = list(dict.fromkeys(findings))
    head = (f"# What the build ships (outside-in)\n\nLooked at: {', '.join(looked)}.\n")
    if not unique:
        return head + "\nNothing that shouldn't ship was found (no credentials, internal addresses or source maps)."
    return head + "\nFound:\n" + "\n".join(f"- {f}" for f in unique[:40]) + (
        f"\n- ... and {len(unique) - 40} more" if len(unique) > 40 else "")
