"""Moving files between the project and the models: snapshots in, <file> blocks out."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import ui, usage

FILE_FORMAT = """To change an existing file, send only the changes, as search/replace edits:
<edit path="relative/path.ext">
<<<<<<< SEARCH
the exact lines currently in the file (enough to be unique)
=======
the lines that replace them
>>>>>>> REPLACE
</edit>
One <edit> block may hold several SEARCH/REPLACE pairs. Each SEARCH must match the file exactly
once, including indentation; to delete lines, leave the replacement empty. If an edit doesn't
apply, the file is left unchanged and you'll be told why.

To create a new file, or to rewrite one completely, send it in full:
<file path="relative/path.ext">
...entire file contents...
</file>
Paths are relative to the project folder. Don't repeat unchanged files.

Fix code rather than weakening linter or formatter configs. Before changing a sensitive file (CI
workflows, migrations, authentication, payment, secrets, deployment), add a line to your message:
WHY path/of/file: what uses it, what the change could break, and how it's checked."""

# A missing </file> ends the block at the next <file> tag or the end of the message.
FILE_RE = re.compile(r'<file path="([^"]+)">\n?(.*?)(</file>|(?=\n<file path=")|\Z)', re.S)
EDIT_RE = re.compile(r'<edit path="([^"]+)">\n?(.*?)</edit>', re.S)
HUNK_RE = re.compile(r"<<<<<<< SEARCH\n(.*?)\n?=======\n(.*?)\n?>>>>>>> REPLACE", re.S)


class Written(list):
    """The paths written, plus `.problems`: edits that couldn't be applied, to tell the model."""

    def __init__(self, *a):
        super().__init__(*a)
        self.problems: list[str] = []
        self.held: list[str] = []       # changes a guard held back (also in problems)


def _safe_dest(base: str, rel: str) -> str | None:
    dest = os.path.realpath(os.path.join(base, rel))
    if not dest.startswith(base + os.sep) or Path(rel).parts[:1] == (".git",):
        return None
    return dest


def apply_hunks(text: str, hunks: list[tuple[str, str]]) -> tuple[str, str]:
    """Apply SEARCH/REPLACE hunks in order. Returns (new text, problem); on a problem the text is
    returned unchanged. A search that isn't found exactly is retried ignoring trailing spaces."""
    out = text
    for i, (search, replace) in enumerate(hunks, 1):
        if not search.strip():
            return text, f"edit {i} has an empty SEARCH; use <file> to create or rewrite a file"
        count = out.count(search)
        if count == 1:
            out = out.replace(search, replace, 1)
            continue
        if count > 1:
            return text, f"edit {i}: the SEARCH text matches {count} places; include more lines so it's unique"
        # Tolerate trailing whitespace differences, line by line.
        lines, want = out.split("\n"), [l.rstrip() for l in search.split("\n")]
        hits = [j for j in range(len(lines) - len(want) + 1)
                if [l.rstrip() for l in lines[j:j + len(want)]] == want]
        if len(hits) == 1:
            j = hits[0]
            out = "\n".join(lines[:j] + replace.split("\n") + lines[j + len(want):])
            continue
        first = next((l for l in want if l.strip()), "")
        near = next((l.strip() for l in lines if first.strip() and first.strip()[:30] in l), "")
        hint = f" (a similar line in the file: {near[:100]!r})" if near else ""
        return text, f"edit {i}: the SEARCH text isn't in the file{hint}; copy it exactly from the current file"
    return out, ""
VERDICT_RE = re.compile(r"^VERDICT:\s*(APPROVED|CHANGES)\s*$", re.M)
SIGNOFF_RE = re.compile(r"^SIGN-OFF:\s*(YES|NO)\s*$", re.M)
STATUS_RE = re.compile(r"^STATUS:\s*(AGREE|CONTINUE|OK|ISSUES)\s*$", re.M)

# The team's own logs live in the project folder but are never sent back to the models.
LOG_DIR = ".team"
ALWAYS_SKIP_DIRS = {".git", ".team", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                    ".next", ".shots", ".pytest_cache", ".mypy_cache"}
# Build output that only counts as noise next to a project file (Node packages keep source in bin/).
DOTNET_OUTPUT_DIRS = {"bin", "obj"}
DOTNET_PROJECTS = (".csproj", ".fsproj", ".vbproj")


def last_marker(regex: re.Pattern, text: str) -> str:
    found = regex.findall(text)
    return found[-1] if found else ""


def write_files(root: str | Path, text: str, allowed: tuple[str, ...] | None = None, guard=None) -> Written:
    """Apply every <edit> block and write every <file> block in `text` under `root`. Refuses paths
    that escape `root`, and, if `allowed` is given, paths outside those prefixes. Edits that can't
    be applied leave their file unchanged and are listed in the result's `.problems`. `guard`
    (guards.make) may hold a change back: (path, exists, text) -> the reason, or ""."""
    written = Written()
    base = os.path.realpath(root)
    reply = text

    def held(rel: str, dest: str) -> bool:
        why = guard(rel, os.path.exists(dest), reply) if guard else ""
        if why:
            ui.warn(f"held back {rel}: {why.split(', so')[0].split(': fix')[0]}")
            written.problems.append(f"{rel}: {why}")
            written.held.append(rel)
        return bool(why)
    for rel, body in EDIT_RE.findall(text):
        dest = _safe_dest(base, rel)
        if dest is None:
            ui.warn(f"skipped unsafe path {rel!r}")
            continue
        if allowed is not None and not rel.startswith(allowed):
            ui.warn(f"skipped {rel!r}: outside the paths this step may change")
            written.problems.append(f"{rel}: outside the paths this step may change")
            continue
        if held(rel, dest):
            continue
        try:
            with open(dest, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            written.problems.append(f"{rel}: no such file to edit; send it whole in a <file> block")
            continue
        hunks = HUNK_RE.findall(body)
        if not hunks:
            written.problems.append(f"{rel}: the <edit> block has no SEARCH/REPLACE pairs")
            continue
        new, problem = apply_hunks(current, hunks)
        if problem:
            ui.warn(f"{rel}: {problem}")
            written.problems.append(f"{rel}: {problem}")
            continue
        with open(dest, "w", encoding="utf-8") as f:
            f.write(new)
        if rel not in written:
            written.append(rel)
    text = EDIT_RE.sub("", text)
    for rel, body, closing in FILE_RE.findall(text):
        if not closing:
            body = VERDICT_RE.split(body)[0].rstrip() + "\n"
            ui.warn(f"{rel}: no closing </file> tag; saved what was there")
        dest = _safe_dest(base, rel)
        if dest is None:
            ui.warn(f"skipped unsafe path {rel!r}")
            continue
        if allowed is not None and not rel.startswith(allowed):
            ui.warn(f"skipped {rel!r}: outside the paths this step may change")
            continue
        if held(rel, dest):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(body)
        written.append(rel)
    return written


def strip_files(text: str) -> str:
    return FILE_RE.sub("[file omitted]", EDIT_RE.sub("[edit omitted]", text))


def problems_note(written) -> str:
    """Tell the model which of its edits didn't apply, so it can resend them."""
    problems = getattr(written, "problems", [])
    return ("\n\n# Edits that were NOT applied (those files are unchanged; resend them corrected)\n" +
            "\n".join(f"- {p}" for p in problems)) if problems else ""


class SnapshotTooLarge(ValueError):
    pass


def git_ignored(root: Path) -> tuple[str, ...]:
    """Paths under `root` that git ignores (folders end in /), so build output such as target/ never
    reaches a prompt. Empty when `root` isn't in a git repository."""
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--others", "--ignored",
                            "--exclude-standard", "--directory"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return tuple(p for p in r.stdout.split("\0") if p) if r.returncode == 0 else ()


def project_files(root: str | Path, *, only: tuple[str, ...] = (), skip: tuple[str, ...] = ()):
    """(relative path, absolute path) of every text file a prompt may include."""
    root = Path(root)
    ignored = git_ignored(root)
    ignored_files, ignored_dirs = {p for p in ignored if not p.endswith("/")}, tuple(p for p in ignored if p.endswith("/"))
    for dirpath, dirnames, filenames in os.walk(root):
        dotnet = any(n.endswith(DOTNET_PROJECTS) for n in filenames)
        dirnames[:] = sorted(d for d in dirnames if d not in ALWAYS_SKIP_DIRS and not
                             (d.startswith(".") and d != ".github") and not (dotnet and d in DOTNET_OUTPUT_DIRS))
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if (only and not rel.startswith(only)) or (skip and rel.startswith(skip)):
                continue
            if rel in ignored_files or (ignored_dirs and rel.startswith(ignored_dirs)):
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
