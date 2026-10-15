"""Moving files between the project and the models: snapshots in, <file> blocks out."""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import ui, usage

FILE_FORMAT = """To create or replace a file, output it in full like this:
<file path="relative/path.ext">
...entire file contents...
</file>
Paths are relative to the project folder. Unchanged files don't need to be repeated."""

# A missing </file> ends the block at the next <file> tag or the end of the message.
FILE_RE = re.compile(r'<file path="([^"]+)">\n?(.*?)(</file>|(?=\n<file path=")|\Z)', re.S)
VERDICT_RE = re.compile(r"^VERDICT:\s*(APPROVED|CHANGES)\s*$", re.M)
SIGNOFF_RE = re.compile(r"^SIGN-OFF:\s*(YES|NO)\s*$", re.M)
STATUS_RE = re.compile(r"^STATUS:\s*(AGREE|CONTINUE|OK|ISSUES)\s*$", re.M)

# The team's own logs live in the project folder but are never sent back to the models.
LOG_DIR = ".team"
ALWAYS_SKIP_DIRS = {".git", ".team", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                    ".next", ".shots", ".pytest_cache", ".mypy_cache"}


def last_marker(regex: re.Pattern, text: str) -> str:
    found = regex.findall(text)
    return found[-1] if found else ""


def write_files(root: str | Path, text: str, allowed: tuple[str, ...] | None = None) -> list[str]:
    """Write every <file> block in `text` under `root`. Refuses paths that escape `root`, and,
    if `allowed` is given, paths outside those prefixes."""
    written = []
    base = os.path.realpath(root)
    for rel, body, closing in FILE_RE.findall(text):
        if not closing:
            body = VERDICT_RE.split(body)[0].rstrip() + "\n"
            ui.warn(f"{rel}: no closing </file> tag; saved what was there")
        dest = os.path.realpath(os.path.join(base, rel))
        if not dest.startswith(base + os.sep) or Path(rel).parts[:1] == (".git",):
            ui.warn(f"skipped unsafe path {rel!r}")
            continue
        if allowed is not None and not rel.startswith(allowed):
            ui.warn(f"skipped {rel!r}: outside the paths this step may change")
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(body)
        written.append(rel)
    return written


def strip_files(text: str) -> str:
    return FILE_RE.sub("[file omitted]", text)


class SnapshotTooLarge(ValueError):
    pass


def project_files(root: str | Path, *, only: tuple[str, ...] = (), skip: tuple[str, ...] = ()):
    """(relative path, absolute path) of every text file a prompt may include."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ALWAYS_SKIP_DIRS and not
                             (d.startswith(".") and d != ".github"))
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if (only and not rel.startswith(only)) or (skip and rel.startswith(skip)):
                continue
            # Never send secrets files or the team config itself.
            if name.startswith(".env") or name in {".team.toml", ".npmrc", ".pypirc"} or name.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico",
                                                        ".woff", ".woff2", ".lock", ".pyc")):
                continue
            yield rel, os.path.join(dirpath, name)


def snapshot(root: str | Path, *, only: tuple[str, ...] = (), skip: tuple[str, ...] = (),
             limit: int = 200_000, paths: set[str] | None = None) -> str:
    """Text files under `root` as <file> blocks, for a prompt. `paths` keeps exactly those files."""
    parts = []
    for rel, full in project_files(root, only=only, skip=skip):
        if paths is not None and rel not in paths:
            continue
        try:
            with open(full, encoding="utf-8") as f:
                parts.append(f'<file path="{rel}">\n{f.read()}</file>')
        except (UnicodeDecodeError, OSError):
            continue
    text = "\n\n".join(parts) or "(no files yet)"
    if len(text) > limit:
        raise SnapshotTooLarge(f"project snapshot is {len(text):,} characters, over the {limit:,} limit. "
                               "Narrow it with [project].context_skip, raise context_limit, or set "
                               "[project].context = \"focused\".")
    return text


def overview(root: str | Path, *, skip: tuple[str, ...] = (), max_entries: int = 4000) -> str:
    """Every file a prompt could include, one per line with its size: a map of the project."""
    lines = []
    for rel, full in project_files(root, skip=skip):
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        lines.append(f"{rel}  ({size:,} bytes)")
        if len(lines) >= max_entries:
            lines.append(f"... (more files not listed; first {max_entries} shown)")
            break
    return "\n".join(lines) or "(no files yet)"


class Log:
    """Markdown log of a workflow run under <project>/.team/logs/."""

    def __init__(self, root: str | Path, name: str, title: str):
        folder = Path(root) / LOG_DIR / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{name}.md"
        started = usage.now()
        self.run_id = f"{name}@{started}"
        usage.set_run(self.run_id)          # tags the model calls of this run in usage.jsonl
        self.f = open(self.path, "a", encoding="utf-8")
        self.f.write(f"\n# {title}\n<!-- run {self.run_id} -->\n")
        self.f.flush()

    def record(self, who: str, text: str, written: list[str] | tuple = ()) -> None:
        note = f"\n\n_Files written: {', '.join(written)}_" if written else ""
        self.f.write(f"\n\n## {who}\n<!-- at {usage.now()} -->\n\n{text}{note}\n")
        self.f.flush()
