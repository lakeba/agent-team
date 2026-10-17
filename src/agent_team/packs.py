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

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import ui
from .config import CONFIG_NAME, Team

ECC_REPO = "https://github.com/affaan-m/ECC.git"
ECC_TAG = "v2.2.3"                  # the release these templates were chosen from
TARGET = "team/skills/ecc"
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

    def pieces(self) -> dict[str, str]:
        return {**COMMON, **self.roles}


PACKS = [
    Pack("python", "Python: ECC's Python reviewer, patterns and testing skills",
         {"lead": "agents/python-reviewer.md", "builder": "skills/python-patterns", "qa": "skills/python-testing"},
         ("pyproject.toml", "setup.py", "requirements.txt")),
    Pack("react", "React: ECC's React reviewer, patterns and testing skills",
         {"lead": "agents/react-reviewer.md", "builder": "skills/react-patterns", "qa": "skills/react-testing"},
         ("package.json",), ("react",)),
    Pack("typescript", "TypeScript and JavaScript: ECC's TypeScript reviewer, frontend patterns and end-to-end testing",
         {"lead": "agents/typescript-reviewer.md", "builder": "skills/frontend-patterns", "qa": "skills/e2e-testing"},
         ("package.json", "tsconfig.json")),
    Pack("dotnet", ".NET and C#: ECC's C# reviewer, .NET patterns and C# testing",
         {"lead": "agents/csharp-reviewer.md", "builder": "skills/dotnet-patterns", "qa": "skills/csharp-testing"},
         ("*.sln", "*.slnx", "*.csproj", "*/*.csproj", "src/*/*.csproj")),
    Pack("go", "Go: ECC's Go reviewer, patterns and testing skills",
         {"lead": "agents/go-reviewer.md", "builder": "skills/golang-patterns", "qa": "skills/golang-testing"},
         ("go.mod",)),
    Pack("rust", "Rust: ECC's Rust reviewer, patterns and testing skills",
         {"lead": "agents/rust-reviewer.md", "builder": "skills/rust-patterns", "qa": "skills/rust-testing"},
         ("Cargo.toml",)),
    Pack("kotlin", "Kotlin: ECC's Kotlin reviewer, patterns and testing skills",
         {"lead": "agents/kotlin-reviewer.md", "builder": "skills/kotlin-patterns", "qa": "skills/kotlin-testing"},
         ("build.gradle.kts", "settings.gradle.kts")),
    Pack("java", "Java: ECC's Java reviewer, coding standards and test-first guide",
         {"lead": "agents/java-reviewer.md", "builder": "skills/java-coding-standards", "qa": "agents/tdd-guide.md"},
         ("pom.xml", "build.gradle")),
    Pack("swift", "Swift: ECC's Swift reviewer, SwiftUI patterns and test-first guide",
         {"lead": "agents/swift-reviewer.md", "builder": "skills/swiftui-patterns", "qa": "agents/tdd-guide.md"},
         ("Package.swift", "*.xcodeproj")),
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
# ECC's files: a pinned release, fetched once (only its agents and skills)

def ecc_home() -> Path:
    import os
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "agent-team" / "ecc" / ECC_TAG


def fetch(source: str = "") -> Path:
    """A folder with ECC's agents/ and skills/: `source` if given (an ECC checkout), else the pinned
    release, cloned once (sparse: agents, skills and the licence)."""
    if source:
        path = Path(source).expanduser().resolve()
        if not (path / "agents").is_dir() or not (path / "skills").is_dir():
            raise SystemExit(f"{path} doesn't look like an ECC checkout (no agents/ and skills/)")
        return path
    home = ecc_home()
    if (home / "agents").is_dir() and (home / "skills").is_dir():
        return home
    home.parent.mkdir(parents=True, exist_ok=True)
    ui.action(f"fetching ECC {ECC_TAG} (agents and skills only) into {home}")
    steps = [["git", "clone", "-q", "--depth", "1", "--branch", ECC_TAG, "--filter=blob:none", "--sparse", ECC_REPO, str(home)],
             ["git", "-C", str(home), "sparse-checkout", "set", "agents", "skills"]]
    for argv in steps:
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            shutil.rmtree(home, ignore_errors=True)
            raise SystemExit(f"couldn't fetch ECC ({' '.join(argv[:3])}): {r.stderr.strip()[-400:]}\n"
                             f"With ECC already on this machine: --ecc PATH")
    return home


def text_of(ecc: Path, ref: str) -> str:
    path = ecc / ref
    path = path / "SKILL.md" if path.is_dir() else path
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Applying a template

def plan(team: Team, pack: Pack, ecc: Path) -> list[tuple[str, str, str, int]]:
    """(member, role, ECC path, characters) for each member the template gives a piece to."""
    out = []
    for a in team.agents.values():
        ref = pack.pieces().get(a.role)
        if ref and (ecc / ref).exists():
            out.append((a.name, a.role, ref, len(text_of(ecc, ref))))
    return out


def project_path(ref: str) -> str:
    """Where a piece lives in the project: team/skills/ecc/agents/x.md or team/skills/ecc/skills/x."""
    return f"{TARGET}/{ref}"


NOTICE = """# ECC pieces in this project

These files come from ECC (https://github.com/affaan-m/ECC), release {tag}, under the MIT licence
below. agent-team copied them here with `agent-team templates apply`; they're project files now:
review them, edit them, or remove them (and their line under `skills` in .team.toml).

{license}
"""


def copy_piece(ecc: Path, ref: str, root: Path) -> None:
    src, dest = ecc / ref, root / project_path(ref)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():   # a skill: its SKILL.md is what members read
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / "SKILL.md", dest / "SKILL.md")
    else:
        shutil.copyfile(src, dest)


def add_skill(text: str, member: str, entry: str) -> str:
    """The team file with `entry` added to `member`'s skills, editing only that member's block so the
    rest of the file (comments included) stays as it is."""
    blocks = re.split(r"(?m)^(?=\[\[agents\]\])", text)
    for i, block in enumerate(blocks):
        if not re.search(rf'(?m)^name\s*=\s*"{re.escape(member)}"\s*$', block):
            continue
        if entry in block:
            return text
        m = re.search(r"(?m)^skills\s*=\s*\[(.*?)\]", block, re.S)
        if m:
            inner = m.group(1).rstrip().rstrip(",")
            new = f'skills = [{inner}{", " if inner.strip() else ""}"{entry}"]'
            blocks[i] = block[:m.start()] + new + block[m.end():]
        else:
            lines = block.split("\n")
            at = max((n for n, l in enumerate(lines) if re.match(r"^(name|role|provider|model|owns|effort)\s*=", l)), default=0)
            lines.insert(at + 1, f'skills = ["{entry}"]')
            blocks[i] = "\n".join(lines)
        return "".join(blocks)
    return text


def apply(team: Team, pack: Pack, source: str = "", yes: bool = False) -> int:
    import sys
    from .config import ConfigError, load
    ecc = fetch(source)
    pieces = plan(team, pack, ecc)
    if not pieces:
        ui.say(f"The {pack.name} template has nothing for this team's roles.")
        return 1
    ui.heading(f"Template: {pack.name} ({pack.about})")
    for member, role, ref, chars in pieces:
        provider = team.providers[team.agents[member].provider]
        note = ("  (a local model: this adds to every prompt it reads)" if provider.kind == "ollama"
                and chars >= LOCAL_MODEL_NOTE else "")
        ui.say(f"  {member} ({role}): ECC {ref}, {chars:,} characters{note}")
    ui.say(f"\nFiles go to {TARGET}/ with ECC's licence; each member's skills list in {CONFIG_NAME} names them.")
    if not yes:
        if not sys.stdin.isatty():
            ui.say("Run again with --yes to apply.")
            return 0
        if input("Apply? [Y/n] ").strip().lower() not in ("", "y", "yes"):
            ui.say("Nothing was changed.")
            return 0
    root = Path(team.root)
    path = root / CONFIG_NAME
    old = path.read_text(encoding="utf-8")
    text = old
    for member, _, ref, _ in pieces:
        copy_piece(ecc, ref, root)
        text = add_skill(text, member, project_path(ref))
    license_text = (ecc / "LICENSE").read_text(encoding="utf-8") if (ecc / "LICENSE").exists() else \
        "MIT License, Copyright (c) Affaan Mustafa (see https://github.com/affaan-m/ECC/blob/main/LICENSE)"
    (root / TARGET / "NOTICE.md").write_text(NOTICE.format(tag=ECC_TAG, license=license_text), encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    try:
        load(root)
    except ConfigError as e:
        path.write_text(old, encoding="utf-8")
        raise SystemExit(f"the template would leave {CONFIG_NAME} invalid ({e}); nothing was changed there")
    ui.action(f"applied the {pack.name} template: {len(pieces)} members got an ECC piece")
    return 0
