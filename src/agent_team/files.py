"""Moving files between the project and the models: snapshots in, <file> blocks out."""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import ui

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


def snapshot(root: str | Path, *, only: tuple[str, ...] = (), skip: tuple[str, ...] = (),
             limit: int = 200_000) -> str:
    """Text files under `root` as <file> blocks, for a prompt."""
    root = Path(root)
    parts = []
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
            try:
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    parts.append(f'<file path="{rel}">\n{f.read()}</file>')
            except (UnicodeDecodeError, OSError):
                continue
    text = "\n\n".join(parts) or "(no files yet)"
    if len(text) > limit:
        raise ValueError(f"project snapshot is {len(text):,} characters, over the {limit:,} limit. "
                         "Narrow it with [project].context_skip, or raise context_limit.")
    return text


class Log:
    """Markdown log of a workflow run under <project>/.team/logs/."""

    def __init__(self, root: str | Path, name: str, title: str):
        folder = Path(root) / LOG_DIR / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{name}.md"
        self.f = open(self.path, "a", encoding="utf-8")
        self.f.write(f"\n# {title}\n")
        self.f.flush()

    def record(self, who: str, text: str, written: list[str] | tuple = ()) -> None:
        note = f"\n\n_Files written: {', '.join(written)}_" if written else ""
        self.f.write(f"\n\n## {who}\n\n{text}{note}\n")
        self.f.flush()
