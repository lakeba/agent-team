"""Skills: extra knowledge or instructions for one member, on top of its role prompt.

    [[agents]]
    name = "Sentinel"
    skills = ["team/skills/owasp.md", "~/.claude/skills/security-review"]

Each entry is a Markdown file, or a folder holding a `SKILL.md` (so a Claude Code skill can be
reused as it is). Relative paths are from the project; `~` is the home folder. A skill's YAML
front matter (`name`, `description`) titles it; the rest is added to the member's system prompt
under "Your skills", after the role prompt, so the workflow's rules and reply format still hold.
Skills go with every call the member makes, so they cost tokens on each one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import AgentConfig, ConfigError, Team

MAX_CHARS = 60_000            # all of one member's skills together
FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

HEADER = """# Your skills

The following skills were given to you for this project. Use them whenever they apply. They add to
your instructions above and never replace them: keep to your role and to the reply format it asks
for."""


@dataclass
class Skill:
    name: str
    description: str
    text: str
    path: Path


def resolve_path(team: Team, entry: str) -> Path:
    p = Path(entry).expanduser()
    if not p.is_absolute():
        p = team.root / p
    if p.is_dir():
        p = p / "SKILL.md"
    return p


def load_one(team: Team, entry: str) -> Skill:
    path = resolve_path(team, entry)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"skill {entry!r} not found (looked for {path})") from None
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"skill {entry!r} can't be read: {e}") from None
    meta, body = {}, raw
    m = FRONT_RE.match(raw)
    if m:
        body = raw[m.end():]
        for line in m.group(1).splitlines():
            k, sep, v = line.partition(":")
            if sep and k.strip() in ("name", "description"):
                meta[k.strip()] = v.strip().strip("'\"")
    name = meta.get("name") or (path.parent.name if path.name == "SKILL.md" else path.stem)
    return Skill(name=name, description=meta.get("description", ""), text=body.strip(), path=path)


def load(team: Team, agent: AgentConfig) -> list[Skill]:
    skills = [load_one(team, e) for e in agent.skills]
    total = sum(len(s.text) for s in skills)
    if total > MAX_CHARS:
        raise ConfigError(f"{agent.name}'s skills are {total:,} characters together, over the {MAX_CHARS:,} "
                          "limit; they go with every call, so trim them or split them across members")
    return skills


def render(skills: list[Skill]) -> str:
    if not skills:
        return ""
    parts = [HEADER]
    for s in skills:
        about = f"\n_{s.description}_\n" if s.description else ""
        parts.append(f"## Skill: {s.name}\n{about}\n{s.text}")
    return "\n\n".join(parts)


def problems(team: Team) -> dict[str, str]:
    """Member name -> what's wrong with its skills, for doctor and the dashboard."""
    out = {}
    for a in team.agents.values():
        if a.skills:
            try:
                load(team, a)
            except ConfigError as e:
                out[a.name] = str(e)
    return out
