"""Quality gates: the project's own checks every round, and debug leftovers in what changed.

    [project]
    checks = ["ruff check .", "mypy src"]      # linters, type checkers, formatters in check mode

Each build and fix round runs the tests and then every command in `checks` (in the sandbox when
there is one), and the lead reviews with their results: a failing check is reported like a failing
test. agent-team also reads the lines the round added and lists debug leftovers (print and
console.log calls, debugger statements, breakpoints, focused or skipped tests) for the lead to
judge, since a test suite rarely notices them.
"""
from __future__ import annotations

import re
import subprocess

from . import github
from .config import Team

LEFTOVERS = [
    (re.compile(r"\bconsole\.(log|debug|trace)\("), (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"), "console.log"),
    (re.compile(r"^\s*debugger;?\s*$"), (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"), "debugger statement"),
    (re.compile(r"\b(it|describe|test)\.only\("), (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"), "a focused test (.only)"),
    (re.compile(r"\b(breakpoint\(\)|pdb\.set_trace\(\)|import pdb|ipdb)"), (".py",), "a breakpoint"),
    (re.compile(r"^\s*print\("), (".py",), "print()"),
    (re.compile(r"@pytest\.mark\.skip\b|@unittest\.skip\b"), (".py",), "a skipped test"),
    (re.compile(r"\bdbg!\("), (".rs",), "dbg!"),
    (re.compile(r"\bfmt\.Print(ln|f)?\("), (".go",), "fmt.Print"),
    (re.compile(r"\bSystem\.out\.print(ln)?\("), (".java", ".kt"), "System.out.print"),
    (re.compile(r"\bConsole\.Write(Line)?\("), (".cs",), "Console.Write"),
    (re.compile(r"\bvar_dump\(|\bdd\("), (".php",), "var_dump/dd"),
    (re.compile(r"\bbinding\.pry\b|\bbyebug\b"), (".rb",), "a debugger call"),
]
TEST_PATH = re.compile(r"(^|/)(tests?|spec|__tests__)/|(_test|\.test|\.spec|Tests?)\.\w+$|(^|/)test_[^/]+$")
SCRIPT_PATH = re.compile(r"(^|/)(scripts?|bin|cli|tools|examples?)/|(^|/)(cli|__main__|main)\.\w+$")


def suggest(root) -> list[str]:
    """Checks this project already has tools for (from its config files), for templates to offer."""
    import json
    import shutil
    from pathlib import Path
    root = Path(root)
    out = []
    py = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace") if (root / "pyproject.toml").exists() else ""
    if ("[tool.ruff" in py or (root / "ruff.toml").exists()) and shutil.which("ruff"):
        out.append("ruff check .")
    if ("[tool.mypy" in py or (root / "mypy.ini").exists()) and shutil.which("mypy"):
        out.append("mypy .")
    if (root / "package.json").exists():
        try:
            scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
        except ValueError:
            scripts = {}
        out += [f"npm run {name}" for name in ("lint", "typecheck", "type-check") if name in scripts]
    if (root / "go.mod").exists() and shutil.which("go"):
        out.append("go vet ./...")
    if (root / "Cargo.toml").exists() and shutil.which("cargo"):
        out.append("cargo clippy --quiet -- -D warnings")
    return out


def run_checks(team: Team) -> str:
    """The results of [project].checks, as Markdown for the lead ("" with none configured)."""
    if not team.project.checks:
        return ""
    from . import sandbox
    parts = []
    for cmd in team.project.checks:
        try:
            code, out = sandbox.run(team, cmd, timeout=300)
            verdict = "passed" if code == 0 else "FAILED"
            parts.append(f"## Check `{cmd}`: {verdict} (exit code {code})\n```\n{out[-4000:]}\n```")
        except subprocess.TimeoutExpired:
            parts.append(f"## Check `{cmd}`: timed out after 300 seconds")
        except sandbox.SandboxError as e:
            parts.append(f"## Check `{cmd}`: couldn't run ({e})")
    return "\n\n" + "\n\n".join(parts)


def added_lines(team: Team, base: str | None) -> dict[str, list[tuple[int, str]]]:
    """{path: [(line, text)]} added since `base` in the working tree (tracked and new files)."""
    if not base:
        return {}
    diff = github.git(team.root, "diff", "--unified=0", "--no-color", base, "--", ".", check=False)
    out: dict[str, list[tuple[int, str]]] = {}
    path, line = "", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line = int(m.group(1)) if m else 0
        elif raw.startswith("+") and path:
            out.setdefault(path, []).append((line, raw[1:]))
            line += 1
    untracked = github.git(team.root, "ls-files", "--others", "--exclude-standard", check=False).splitlines()
    for rel in untracked:
        try:
            text = (team.root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out[rel] = list(enumerate(text.splitlines(), 1))
    return out


def leftovers(team: Team, base: str | None) -> list[str]:
    found = []
    for path, lines in added_lines(team, base).items():
        if path.startswith((".team/", "team/")):
            continue
        in_test = bool(TEST_PATH.search(path))
        for pattern, exts, what in LEFTOVERS:
            if not path.endswith(exts):
                continue
            if what in ("print()", "fmt.Print", "System.out.print", "Console.Write", "console.log") and (
                    in_test or SCRIPT_PATH.search(path)):
                continue   # output is the job of command-line entry points, and tests may print
            for n, text in lines:
                if pattern.search(text):
                    found.append(f"{path}:{n}: {what}: {text.strip()[:100]}")
    return found[:30]


def report(team: Team, base: str | None) -> str:
    """Checks and leftovers together, as one section for the lead ("" when there's nothing)."""
    out = run_checks(team)
    left = leftovers(team, base)
    if left:
        out += ("\n\n## Possible debug leftovers in this round's changes\n"
                "Remove them unless they're meant (a command-line tool's output is fine):\n" +
                "\n".join(f"- {x}" for x in left))
    return out
