"""Focused context: send the models the files a task needs instead of the whole project.

`[project].context` chooses: "full" sends every file (and fails when that's over context_limit),
"focused" lets the lead pick files from a map of the project, and "auto" (the default) sends
everything when it fits and focuses when it doesn't. Files the team writes during a run are
always added, and the lead can widen the set in any reply with lines like `FILE: src/app.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import files
from .config import Team

FILE_LINE_RE = re.compile(r"^(?:FILE|NEED):\s*`?([^\s`]+)`?\s*$", re.M)
ALWAYS = ("VISION.md", "README.md", "README", "PLAN.md", "ROADMAP.md", "CHANGELOG.md", "pyproject.toml", "package.json")
VISION = "VISION.md"     # the owner's description of the product: what it's for and who it's for


def vision(team: Team) -> str:
    """The project's VISION.md, or "" if it has none."""
    path = team.root / VISION
    try:
        return path.read_text(encoding="utf-8").strip()[:20_000] if path.is_file() else ""
    except OSError:
        return ""

SELECT_PROMPT = """The project is too large to send whole, so choose the files you need.

Task: {task}

Below is every file with its size. Reply with the files you need to plan this task (and that the
builder will need to change or read), one per line as `FILE: path/to/file`. Choose what matters:
the files to change, their tests, and the interfaces they depend on. Together they must stay under
{limit:,} characters. The README and PLAN.md are added for you.

# Most likely relevant (ranked by a search for the task's words; a starting point, not the answer)
{ranked}

# Project map
{overview}"""


class Focus:
    """The set of files one run sends, and how to render it into a prompt."""

    def __init__(self, team: Team, paths: set[str] | None):
        self.team, self.paths = team, paths   # None: the whole project

    @property
    def focused(self) -> bool:
        return self.paths is not None

    def add(self, more) -> None:
        if self.paths is not None:
            self.paths.update(p for p in more if (self.team.root / p).is_file())

    def add_from_reply(self, text: str) -> list[str]:
        if self.paths is None:
            return []
        asked = FILE_LINE_RE.findall(files.strip_files(text))
        before = set(self.paths)
        self.add(asked)
        return sorted(self.paths - before)

    def render(self) -> str:
        skip, limit = tuple(self.team.project.context_skip), self.team.project.context_limit
        if self.paths is None:
            return files.snapshot(self.team.root, skip=skip, limit=limit)
        body = _fit(self.team.root, self.paths, skip, limit)
        return (f"(Focused context: {len(self.paths)} of the project's files. Ask for others with "
                f"`FILE: path` lines.)\n\n{body}")


def _fit(root: Path, paths: set[str], skip: tuple, limit: int) -> str:
    """The chosen files, dropping the largest ones (with a note) until they fit the limit."""
    keep = set(paths)
    while True:
        try:
            return files.snapshot(root, skip=skip, limit=limit, paths=keep)
        except files.SnapshotTooLarge:
            sizes = {p: (root / p).stat().st_size for p in keep if (root / p).is_file()}
            if not sizes:
                raise
            biggest = max(sizes, key=sizes.get)
            keep.discard(biggest)
            paths.discard(biggest)


def needs_focus(team: Team) -> bool:
    mode = team.project.context
    if mode != "auto":
        return mode == "focused"
    try:
        files.snapshot(team.root, skip=tuple(team.project.context_skip), limit=team.project.context_limit)
        return False
    except files.SnapshotTooLarge:
        return True


def default_paths(team: Team) -> set[str]:
    return {p for p in ALWAYS if (team.root / p).is_file()}


def choose(team: Team, chooser, task: str) -> Focus:
    """Ask `chooser` (normally the lead) which files a task needs, when the project needs focusing."""
    if not needs_focus(team):
        return Focus(team, None)
    skip = tuple(team.project.context_skip)
    from . import rank
    reply = chooser.turn(SELECT_PROMPT.format(task=task, limit=team.project.context_limit,
                                              ranked=rank.shortlist(team.root, task, skip),
                                              overview=files.overview(team.root, skip=skip)))
    focus = Focus(team, default_paths(team))
    focus.add_from_reply(reply)
    return focus


def for_topic(team: Team, paths: set[str] | None = None, skip_extra: tuple[str, ...] = (), query: str = "") -> str:
    """Project files for a workflow without a lead's choice (discuss, setup, market, reviews):
    everything when it fits, else the key files and the given paths plus a map of the rest."""
    skip, limit = tuple(team.project.context_skip) + skip_extra, team.project.context_limit
    if not needs_focus(team):
        try:
            return files.snapshot(team.root, skip=skip, limit=limit)
        except files.SnapshotTooLarge:
            if team.project.context == "full":
                raise
    chosen = default_paths(team) | {p for p in (paths or ()) if (team.root / p).is_file()}
    if query:   # add the files that best match the topic, as far as they fit
        from . import rank
        chosen |= {rel for rel, _ in rank.rank(team.root, query, skip, top=15)}
    budget = max(limit - 20_000, limit // 2)
    return (f"(The project is too large to send whole: the key files follow, then a map of all files.)\n\n"
            f"{_fit(team.root, chosen, skip, budget)}\n\n# Project map\n{files.overview(team.root, skip=skip)[:18_000]}")
