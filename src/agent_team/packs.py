"""Team templates that reuse ECC's agents and skills (https://github.com/affaan-m/ECC, MIT licence).

ECC is a large, community-maintained library of agent prompts and skills for coding agents. A
template gives each member of an agent-team the one ECC piece that fits its role and the project's
language: the lead gets ECC's reviewer for that language, the builder its patterns skill, QA its
testing skill, and the security, docs and marketing members ECC's agents for those jobs.

    agent-team templates                 # the templates, and the one that fits this project
    agent-team templates apply [NAME]    # copy the pieces into team/skills/ecc/ and give them out

The files are copied from a pinned ECC release into the project, with ECC's licence beside them,
so they're reviewed and committed like any other project file, and the team file only names them
under each member's `skills`. Every skill goes with each call that member makes, so templates add
one piece per role and say how much they add.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import ecc as ecc_lib, ui
from .config import CONFIG_NAME, Team

ECC_TAG = ecc_lib.TAG
TARGET = ecc_lib.SKILLS_DIR
COMMON_RULES = ("common/coding-style", "common/security", "common/testing")
LOCAL_MODEL_NOTE = 15_000            # characters a local model's prompt gains before we mention it

COMMON = {"security": "agents/security-reviewer.md", "docs": "agents/doc-updater.md",
          "marketing": "agents/marketing-agent.md"}


@dataclass
class Pack:
    name: str
    about: str
    roles: dict[str, str]                   # role -> ECC path (agents/x.md or skills/x)
    markers: tuple[str, ...] = ()           # glob patterns that suggest this pack
    needs: tuple[str, ...] = field(default=())   # words that must appear in package.json (for JS packs)
    rules: tuple[str, ...] = ()             # ECC rule folders for the language (rules/<x>), besides the common ones

    def pieces(self) -> dict[str, str]:
        return {**COMMON, **self.roles}


PACKS = [
    Pack("python", "Python: ECC's Python reviewer, patterns and testing skills",
         {"lead": "agents/python-reviewer.md", "builder": "skills/python-patterns", "qa": "skills/python-testing"},
         ("pyproject.toml", "setup.py", "requirements.txt"), rules=("python",)),
    Pack("react", "React: ECC's React reviewer, patterns and testing skills",
         {"lead": "agents/react-reviewer.md", "builder": "skills/react-patterns", "qa": "skills/react-testing"},
         ("package.json",), ("react",), rules=("typescript", "react")),
    Pack("typescript", "TypeScript and JavaScript: ECC's TypeScript reviewer, frontend patterns and end-to-end testing",
         {"lead": "agents/typescript-reviewer.md", "builder": "skills/frontend-patterns", "qa": "skills/e2e-testing"},
         ("package.json", "tsconfig.json"), rules=("typescript",)),
    Pack("dotnet", ".NET and C#: ECC's C# reviewer, .NET patterns and C# testing",
         {"lead": "agents/csharp-reviewer.md", "builder": "skills/dotnet-patterns", "qa": "skills/csharp-testing"},
         ("*.sln", "*.slnx", "*.csproj", "*/*.csproj", "src/*/*.csproj"), rules=("csharp",)),
    Pack("go", "Go: ECC's Go reviewer, patterns and testing skills",
         {"lead": "agents/go-reviewer.md", "builder": "skills/golang-patterns", "qa": "skills/golang-testing"},
         ("go.mod",), rules=("golang",)),
    Pack("rust", "Rust: ECC's Rust reviewer, patterns and testing skills",
         {"lead": "agents/rust-reviewer.md", "builder": "skills/rust-patterns", "qa": "skills/rust-testing"},
         ("Cargo.toml",), rules=("rust",)),
    Pack("kotlin", "Kotlin: ECC's Kotlin reviewer, patterns and testing skills",
         {"lead": "agents/kotlin-reviewer.md", "builder": "skills/kotlin-patterns", "qa": "skills/kotlin-testing"},
         ("build.gradle.kts", "settings.gradle.kts"), rules=("kotlin",)),
    Pack("java", "Java: ECC's Java reviewer, coding standards and test-first guide",
         {"lead": "agents/java-reviewer.md", "builder": "skills/java-coding-standards", "qa": "agents/tdd-guide.md"},
         ("pom.xml", "build.gradle"), rules=("java",)),
    Pack("swift", "Swift: ECC's Swift reviewer, SwiftUI patterns and test-first guide",
         {"lead": "agents/swift-reviewer.md", "builder": "skills/swiftui-patterns", "qa": "agents/tdd-guide.md"},
         ("Package.swift", "*.xcodeproj"), rules=("swift",)),
    Pack("general", "Any language: ECC's code reviewer, verification loop and test-first guide",
         {"lead": "agents/code-reviewer.md", "builder": "skills/verification-loop", "qa": "agents/tdd-guide.md"}),
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


# ---------------------------------------------------------------------------------------------
# Applying a template

def text_of(ecc: Path, ref: str) -> str:
    path = ecc / ref
    path = path / "SKILL.md" if path.is_dir() else path
    return path.read_text(encoding="utf-8")


def rule_files(pack: Pack, ecc: Path) -> list[str]:
    """The ECC rule files (rules/...) the template adds: a few common ones, and the language's."""
    out = [f"rules/{r}.md" for r in COMMON_RULES if (ecc / f"rules/{r}.md").exists()]
    for lang in pack.rules:
        out += sorted(f"rules/{lang}/{p.name}" for p in (ecc / "rules" / lang).glob("*.md"))
    return out


def plan(team: Team, pack: Pack, ecc: Path) -> list[tuple[str, str, str, int]]:
    """(member, role, ECC path, characters) for each member the template gives a piece to."""
    out = []
    for a in team.agents.values():
        ref = pack.pieces().get(a.role)
        if ref and (ecc / ref).exists():
            out.append((a.name, a.role, ref, len(text_of(ecc, ref))))
    return out


project_path = ecc_lib.project_path
add_skill = ecc_lib.add_skill


def apply(team: Team, pack: Pack, source: str = "", yes: bool = False) -> int:
    import sys
    ecc = ecc_lib.fetch(source)
    pieces = plan(team, pack, ecc)
    rules = rule_files(pack, ecc)
    if not pieces:
        ui.say(f"The {pack.name} template has nothing for this team's roles.")
        return 1
    ui.heading(f"Template: {pack.name} ({pack.about})")
    for member, role, ref, chars in pieces:
        provider = team.providers[team.agents[member].provider]
        note = ("  (a local model: this adds to every prompt it reads)" if provider.kind == "ollama"
                and chars >= LOCAL_MODEL_NOTE else "")
        ui.say(f"  {member} ({role}): ECC {ref}, {chars:,} characters{note}")
    if rules:
        size = sum((ecc / r).stat().st_size for r in rules)
        ui.say(f"  everyone: ECC's rules ({', '.join(sorted({r.split('/')[1] for r in rules}))}), {size:,} characters")
    ui.say(f"\nFiles go to {TARGET}/ and {ecc_lib.RULES_DIR}/ with ECC's licence; {CONFIG_NAME} names them "
           f"(members' skills, [project].rules).")
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
        text = ecc_lib.add_skill(text, member, ecc_lib.copy(ecc, ref, root))
    for folder in sorted({str(Path(ecc_lib.copy(ecc, r, root)).parent) for r in rules}):
        text = ecc_lib.add_rule(text, folder)
    ecc_lib.save_team_file(root, text)
    ui.action(f"applied the {pack.name} template: {len(pieces)} members got an ECC piece")
    return 0
