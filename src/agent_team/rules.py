"""Project rules: standards every member follows on every call.

    [project]
    rules = ["team/rules/ecc/common", "team/rules/ecc/python", "team/rules/house-style.md"]

Each entry is a Markdown file or a folder of them (relative to the project; `~` is the home
folder). They go into every member's instructions after its role prompt, so keep them short:
skills are for one member, the library (`[project].library`) for knowledge read on demand.
`agent-team ecc rules LANG` copies ECC's rules for a language into team/rules/ecc/.
"""
from __future__ import annotations

from pathlib import Path

from .config import ConfigError, Team

MAX_CHARS = 40_000

HEADER = """# Project rules

These standards apply to everything you do on this project. They add to your instructions above and
never replace them: keep to your role and to the reply format it asks for."""


def files(team: Team) -> list[Path]:
    out = []
    for entry in team.project.rules:
        p = Path(entry).expanduser()
        p = p if p.is_absolute() else team.root / p
        if p.is_dir():
            found = sorted(p.glob("*.md"))
            out += [f for f in found if f.name not in ("NOTICE.md", "README.md")]
        elif p.is_file():
            out.append(p)
        else:
            raise ConfigError(f"[project].rules: {entry!r} not found (looked for {p})")
    return out


def render(team: Team) -> str:
    if not team.project.rules:
        return ""
    from .ecc import front
    parts, total = [HEADER], 0
    for path in files(team):
        body = front(path.read_text(encoding="utf-8"))[1].strip()
        total += len(body)
        title = f"{path.parent.name}/{path.stem}" if path.parent.name != "rules" else path.stem
        parts.append(f"## Rules: {title}\n\n{body}")
    if total > MAX_CHARS:
        raise ConfigError(f"[project].rules are {total:,} characters together, over the {MAX_CHARS:,} limit; they go "
                          f"with every call of every member, so keep the ones that matter")
    return "\n\n".join(parts)


def problem(team: Team) -> str:
    try:
        render(team)
    except (ConfigError, OSError, UnicodeDecodeError) as e:
        return str(e)
    return ""
