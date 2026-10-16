"""Reviews with tools: the reviewer reads files, searches, sees the diff and runs the tests itself.

A snapshot review shows the reviewer every file up front and asks it to judge from that. A tool
review gives it a short brief (the plan, the builder's message, the changed files, the test
output) and tools to look further, so it can check a suspicion instead of guessing, and large
projects cost less because only what it reads is sent. Every tool is read-only except running
the project's own test command.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from anthropic import beta_tool

from . import files, github, providers, tool_loop
from .config import AgentConfig, Team

MAX_READ = 40_000


def supported(team: Team, cfg: AgentConfig) -> bool:
    """Tool reviews need a provider that can call tools, and the project not opting out."""
    if team.project.review != "tools":
        return False
    pcfg = team.providers[cfg.provider]
    try:
        return providers.build(pcfg, team.secret(pcfg)).supports_tools
    except Exception:
        return False


def make_tools(team: Team, base: str | None = None, touched: set[str] | None = None) -> list:
    root = Path(team.root)
    skip = tuple(team.project.context_skip)
    readable = {rel for rel, _ in files.project_files(root, skip=skip)}

    def allowed(path: str) -> str | None:
        """The path, if it's a file prompts may include (new files count once they exist)."""
        rel = path.strip().removeprefix("./")
        if rel not in readable:
            readable.update(r for r, _ in files.project_files(root, skip=skip))
        return rel if rel in readable else None

    @beta_tool
    def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
        """Read a project file, or part of it, with line numbers.

        Args:
            path: The file's path relative to the project folder.
            start_line: First line to show (1-based).
            end_line: Last line to show; 0 means to the end.
        """
        rel = allowed(path)
        if not rel:
            return f"Not readable: {path!r} isn't a project file (secrets, build output and the team config are never shown)."
        lines = (root / rel).read_text(encoding="utf-8", errors="replace").split("\n")
        start = max(1, start_line)
        end = len(lines) if end_line <= 0 else min(len(lines), end_line)
        out = "\n".join(f"{i:5} {lines[i - 1]}" for i in range(start, end + 1))
        return out[:MAX_READ] + ("\n[cut: ask for a smaller range]" if len(out) > MAX_READ else "")

    @beta_tool
    def list_files(prefix: str = "") -> str:
        """List the project's files with their sizes.

        Args:
            prefix: Only paths starting with this (e.g. "src/"); empty for all.
        """
        rows = [f"{rel}  ({os.path.getsize(full):,} bytes)" for rel, full in files.project_files(root, skip=skip)
                if rel.startswith(prefix)]
        return "\n".join(rows[:1500]) or "(no files)"

    @beta_tool
    def search(pattern: str, prefix: str = "") -> str:
        """Search the project's files for a regular expression; returns matching lines.

        Args:
            pattern: A Python regular expression.
            prefix: Only search paths starting with this; empty for all.
        """
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"Invalid pattern: {e}"
        hits = []
        for rel, full in files.project_files(root, skip=skip):
            if not rel.startswith(prefix):
                continue
            try:
                for n, line in enumerate(open(full, encoding="utf-8"), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{n}: {line.rstrip()[:200]}")
                        if len(hits) >= 80:
                            return "\n".join(hits) + "\n[more matches not shown]"
            except (UnicodeDecodeError, OSError):
                continue
        return "\n".join(hits) or "No matches."

    @beta_tool
    def diff() -> str:
        """Show what changed in this work so far: a unified diff, plus any new files."""
        if base and (root / ".git").exists():
            text = github.git(root, "diff", base, "--", ".", check=False)
            new = github.git(root, "ls-files", "--others", "--exclude-standard", check=False).split()
            for rel in new:
                if allowed(rel):
                    text += f"\n--- new file {rel}\n" + (root / rel).read_text(encoding="utf-8", errors="replace")
            return text[:60_000] or "No changes."
        changed = sorted(touched or ())
        return files.snapshot(root, paths=set(changed), limit=60_000) if changed else "No changes recorded."

    @beta_tool
    def run_tests() -> str:
        """Run the project's test command and return the end of its output."""
        cmd = team.project.test_command
        if not cmd:
            return "No test command is configured."
        from . import sandbox
        try:
            code, out = sandbox.run(team, cmd)
            return f"exit code {code}\n" + out[-8000:]
        except subprocess.TimeoutExpired:
            return "Timed out after 600 seconds."
        except sandbox.SandboxError as e:
            return f"Can't run the tests: {e}"

    return [read_file, list_files, search, diff, run_tests]


TOOL_NOTE = """You have tools to inspect the work yourself: read_file, list_files, search, diff (what
changed) and run_tests. Use them to check anything you're not sure of, rather than assuming.
Read what you need, not everything. When you're done, write your review and end with the
verdict line your instructions ask for."""


def review(team: Team, cfg: AgentConfig, system: str, brief: str, base: str | None = None,
           touched: set[str] | None = None, max_steps: int = 25) -> str:
    """One review with tools; returns the reviewer's final text (with its verdict line)."""
    return tool_loop.run(team, cfg, f"{system}\n\n{TOOL_NOTE}", make_tools(team, base, touched), brief, max_steps)
