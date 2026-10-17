"""Team templates: a starting set of the built-in library for a project's language.

A template gives each member the library piece that fits its role and the project's language: the
lead the language's reviewer, the builders its patterns skill, QA its testing skill, the security
member the security reviewer and the docs member the docs writer. Everyone gets the common rules
and the language's, and the rest of the library is offered on demand.

    agent-team templates                 # the templates, and the one that fits this project
    agent-team templates apply [NAME]    # copy the pieces into team/ and give them out

The pieces are copied into the project, so they're reviewed and committed like any other file, and
the team file only names them. Skills and rules go with every call, so `apply` says how much each
member's prompt gains first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import kit, ui
from .config import CONFIG_NAME, Team

LOCAL_MODEL_NOTE = 15_000            # characters a local model's prompt gains before we mention it
COMMON = {"security": "agents/security-reviewer.md", "docs": "agents/docs-writer.md"}


@dataclass
class Pack:
    name: str
    about: str
    roles: dict[str, str]                   # role -> library path (agents/x.md or skills/x)
    markers: tuple[str, ...] = ()           # glob patterns that suggest this pack
    needs: tuple[str, ...] = field(default=())   # words that must appear in package.json (for JS packs)
    rules: tuple[str, ...] = ()             # rule folders for the language, besides the common ones

    def pieces(self) -> dict[str, str]:
        return {**COMMON, **self.roles}


def _lang(name: str, title: str, skills: str, markers: tuple, rules: tuple, needs: tuple = ()) -> Pack:
    return Pack(name, f"{title}: a {title} reviewer, patterns and testing skills, {title} rules",
                {"lead": f"agents/{name if name != 'dotnet' else 'csharp'}-reviewer.md",
                 "builder": f"skills/{skills}-patterns", "qa": f"skills/{skills}-testing"},
                markers, needs, rules)


PACKS = [
    _lang("python", "Python", "python", ("pyproject.toml", "setup.py", "requirements.txt"), ("python",)),
    _lang("react", "React", "react", ("package.json",), ("typescript", "react"), ("react",)),
    _lang("typescript", "TypeScript", "typescript", ("package.json", "tsconfig.json"), ("typescript",)),
    _lang("dotnet", ".NET", "dotnet", ("*.sln", "*.slnx", "*.csproj", "*/*.csproj", "src/*/*.csproj"), ("csharp",)),
    _lang("go", "Go", "go", ("go.mod",), ("go",)),
    _lang("rust", "Rust", "rust", ("Cargo.toml",), ("rust",)),
    _lang("kotlin", "Kotlin", "kotlin", ("build.gradle.kts", "settings.gradle.kts"), ("kotlin",)),
    _lang("java", "Java", "java", ("pom.xml", "build.gradle"), ("java",)),
    _lang("swift", "Swift", "swift", ("Package.swift", "*.xcodeproj"), ("swift",)),
    Pack("general", "Any language: the code reviewer, the verification loop and test-first development",
         {"lead": "agents/code-reviewer.md", "builder": "skills/verification-loop", "qa": "skills/tdd-workflow"}),
]
BY_NAME = {p.name: p for p in PACKS}


def detect(root: Path) -> Pack:
    """The template that fits the project best (general when nothing matches)."""
    root = Path(root)
    pkg = (root / "package.json").read_text(encoding="utf-8", errors="replace") if (root / "package.json").is_file() else ""
    for p in PACKS:
        if p.markers and any(next(root.glob(m), None) for m in p.markers) and all(w in pkg for w in p.needs):
            return p
    return BY_NAME["general"]


def text_of(ref: str) -> str:
    path = kit.HOME / ref
    path = path / "SKILL.md" if path.is_dir() else path
    return path.read_text(encoding="utf-8")


def rule_files(pack: Pack) -> list[str]:
    """The rule files (rules/...) the template adds: the common ones, and the language's."""
    out = []
    for folder in ("common", *pack.rules):
        out += sorted(f"rules/{folder}/{p.name}" for p in (kit.HOME / "rules" / folder).glob("*.md"))
    return out


def plan(team: Team, pack: Pack) -> list[tuple[str, str, str, int]]:
    """(member, role, library path, characters) for each member the template gives a piece to."""
    out = []
    for a in team.agents.values():
        ref = pack.pieces().get(a.role)
        if ref and (kit.HOME / ref).exists():
            out.append((a.name, a.role, ref, len(text_of(ref))))
    return out


def apply(team: Team, pack: Pack, yes: bool = False) -> int:
    import sys
    pieces = plan(team, pack)
    rules = rule_files(pack)
    if not pieces:
        ui.say(f"The {pack.name} template has nothing for this team's roles.")
        return 1
    ui.heading(f"Template: {pack.name} ({pack.about})")
    for member, role, ref, chars in pieces:
        provider = team.providers[team.agents[member].provider]
        note = ("  (a local model: this adds to every prompt it reads)" if provider.kind == "ollama"
                and chars >= LOCAL_MODEL_NOTE else "")
        ui.say(f"  {member} ({role}): {ref}, {chars:,} characters{note}")
    size = sum((kit.HOME / r).stat().st_size for r in rules)
    ui.say(f"  everyone: rules for {', '.join(sorted({r.split('/')[1] for r in rules}))}, {size:,} characters")
    ui.say("  everyone: the rest of the library on demand (read only when a task needs it)")
    from . import quality
    found = [] if team.project.checks else quality.suggest(team.root)
    if found:
        ui.say(f"  every round: {', '.join(found)} (the project's own checks)")
    ui.say(f"\nFiles go to {kit.SKILLS_DIR}/ and {kit.RULES_DIR}/; {CONFIG_NAME} names them.")
    if not yes:
        if not sys.stdin.isatty():
            ui.say("Run again with --yes to apply.")
            return 0
        if input("Apply? [Y/n] ").strip().lower() not in ("", "y", "yes"):
            ui.say("Nothing was changed.")
            return 0
    root = Path(team.root)
    text = (root / CONFIG_NAME).read_text(encoding="utf-8")
    for member, _, ref, _ in pieces:
        text = kit.add_skill(text, member, kit.copy(ref, root))
    for folder in sorted({str(Path(kit.copy(r, root)).parent) for r in rules}):
        text = kit.add_rule(text, folder)
    text = kit.add_to_project(text, "library", "builtin")
    from . import quality
    if not team.project.checks:
        for cmd in quality.suggest(root):
            text = kit.add_to_project(text, "checks", cmd)
    kit.save_team_file(root, text)
    ui.action(f"applied the {pack.name} template: {len(pieces)} members got a piece, everyone the rules and the library")
    return 0
