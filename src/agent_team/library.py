"""The skill library: skills members read when they need them, instead of on every call.

    [project]
    library = ["ecc", "~/.claude/skills", "team/library"]

"ecc" is ECC's ~300 skills (the pinned release agent-team fetches); any other entry is a folder of
skill folders (each with a SKILL.md) or of Markdown files. On a member's first message of a run,
agent-team lists the library skills that match the task (name and one line each), and the member
may answer with only lines like

    SKILL: api-design

to read up to three of them before it answers. Nothing of the library goes into a prompt unless
it's asked for, so a large library costs little, which matters most for local models.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Team

SKILL_RE = re.compile(r"^\s*SKILL:\s*`?([\w.@/-]+)`?\s*$", re.M)
INDEX_SIZE = 8         # skills listed per first message
LEAST = 6.0            # how well a skill must match the request to be listed
MAX_ASK = 3            # skills read per request
MAX_ROUNDS = 2         # requests per message
MAX_CHARS = 30_000     # one skill's text, at most

INDEX_HEADER = """# Skills you can read first

These skills from the team's library match this request. If one would help, reply with only lines
like `SKILL: name` (at most {most}) and nothing else; you'll get them and then give your real answer.
If none would help, just answer.
"""


@dataclass
class LibSkill:
    name: str
    description: str
    path: Path


def _from_folder(folder: Path) -> list[LibSkill]:
    from .ecc import _describe
    out = []
    for p in sorted(folder.glob("*/SKILL.md")):
        out.append(LibSkill(p.parent.name, _describe(p), p))
    for p in sorted(folder.glob("*.md")):
        if p.name not in ("README.md", "NOTICE.md"):
            out.append(LibSkill(p.stem, _describe(p), p))
    return out


_CACHE: dict[tuple, list[LibSkill]] = {}


def entries(team: Team) -> list[LibSkill]:
    key = (str(team.root), tuple(team.project.library))
    if key in _CACHE:
        return _CACHE[key]
    out: list[LibSkill] = []
    for entry in team.project.library:
        if entry == "ecc":
            from . import ecc
            home = ecc.present() or ecc.fetch()
            out += [LibSkill(e.name, e.description, e.path) for e in ecc.catalog(home, "skills")]
            continue
        p = Path(entry).expanduser()
        p = p if p.is_absolute() else team.root / p
        if p.is_dir():
            out += _from_folder(p)
    seen, unique = set(), []
    for s in out:   # the first entry with a name wins
        if s.name not in seen:
            seen.add(s.name)
            unique.append(s)
    _CACHE[key] = unique
    return unique


def index(team: Team, request: str) -> str:
    """The library skills that match `request`, as a short list for the first message ("" if none)."""
    if not team.project.library:
        return ""
    from .ecc import rank
    # Only the request itself: not the project files that follow it, nor the team's own names.
    ask = re.split(r"\n#+ ", request, maxsplit=1)[0][:1500]
    for name in [*team.agents, "PLAN.md", "ROADMAP.md"]:
        ask = ask.replace(name, " ")
    pool = entries(team)
    found = rank(pool, ask, INDEX_SIZE, LEAST if len(pool) >= 50 else 0.0)   # a small library: any match
    if not found:
        return ""
    lines = "\n".join(f"- {s.name}: {s.description[:160]}" for s in found)
    return INDEX_HEADER.format(most=MAX_ASK) + "\n" + lines


def requested(reply: str) -> list[str]:
    """The skills a reply asks for, if that's all it does (no files, no verdict, nothing else)."""
    names = SKILL_RE.findall(reply)
    if not names:
        return []
    rest = SKILL_RE.sub("", reply).strip()
    if len(rest) > 300 or "<file" in rest or "<edit" in rest:
        return []
    return list(dict.fromkeys(names))[:MAX_ASK]


def read(team: Team, names: list[str]) -> str:
    from .ecc import front
    by_name = {s.name: s for s in entries(team)}
    parts = []
    for n in names:
        s = by_name.get(n)
        if not s:
            parts.append(f"## {n}\n\n(no skill by that name in the library)")
            continue
        body = front(s.path.read_text(encoding="utf-8"))[1].strip()
        parts.append(f"## Skill: {n}\n\n{body[:MAX_CHARS]}")
    return ("# The skills you asked for\n\n" + "\n\n".join(parts) +
            "\n\nNow give your answer to the request above, in the format your instructions ask for.")
