"""ECC's library (https://github.com/affaan-m/ECC, MIT licence), for the team.

ECC is a large, community-maintained library for coding agents: agents (specialist prompts),
skills, commands (playbooks), and rules (always-on standards for a language). agent-team uses a
pinned ECC release, fetched once into ~/.local/share/agent-team/ecc/<tag> (only those four
folders), and maps each piece onto the team:

    agents    a new member (`ecc add-member`) or a skill for an existing one (`ecc add-skill`)
    skills    given to a member (`ecc add-skill`), or read on demand (`[project].library = ["ecc"]`)
    commands  playbooks a member runs (`ecc run`), also offered to coding agents as MCP prompts
    rules     project standards every member follows (`ecc rules LANG`, `[project].rules`)

Pieces copied into a project go under team/skills/ecc/ or team/rules/ecc/ with ECC's licence
(NOTICE.md), so they're reviewed and committed like any other file.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import ui

REPO = "https://github.com/affaan-m/ECC.git"
TAG = "v2.2.3"                      # the release agent-team was checked against
PARTS = ("agents", "skills", "commands", "rules")
KINDS = ("agents", "skills", "commands", "rules")
SKILLS_DIR, RULES_DIR = "team/skills/ecc", "team/rules/ecc"
FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}")
STOP = set("the and for with that this from into your you are use when what how all any can not but out "
           "its has have was were will would should could their them they then than also more most each "
           "other such only over under about after before using used make made code file files task tasks "
           "add adds added run runs running result results object objects print prints flag flags write writes "
           "build builds new change changes update updates need needs like just sure then via one two".split())

NOTICE = """# ECC pieces in this project

These files come from ECC (https://github.com/affaan-m/ECC), release {tag}, under the MIT licence
below. agent-team copied them here; they're project files now: review them, edit them, or remove
them (and their line in .team.toml).

{license}
"""
LICENSE_FALLBACK = "MIT License, Copyright (c) Affaan Mustafa (https://github.com/affaan-m/ECC/blob/main/LICENSE)"


def home() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "agent-team" / "ecc" / TAG


def present() -> Path | None:
    """The fetched release, if it's on this machine with every part."""
    h = home()
    return h if all((h / p).is_dir() for p in PARTS) else None


def fetch(source: str = "") -> Path:
    """A folder with ECC's agents/, skills/, commands/ and rules/: `source` if given (an ECC checkout),
    else the pinned release, cloned once (sparse and shallow)."""
    if source:
        path = Path(source).expanduser().resolve()
        if not (path / "agents").is_dir() or not (path / "skills").is_dir():
            raise SystemExit(f"{path} doesn't look like an ECC checkout (no agents/ and skills/)")
        return path
    h = home()
    if present():
        return h
    if (h / ".git").is_dir():   # an older fetch with fewer parts: widen it
        steps = [["git", "-C", str(h), "sparse-checkout", "set", *PARTS]]
    else:
        h.parent.mkdir(parents=True, exist_ok=True)
        ui.action(f"fetching ECC {TAG} (agents, skills, commands and rules) into {h}")
        steps = [["git", "clone", "-q", "--depth", "1", "--branch", TAG, "--filter=blob:none", "--sparse", REPO, str(h)],
                 ["git", "-C", str(h), "sparse-checkout", "set", *PARTS]]
    for argv in steps:
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            if argv[1] == "clone":
                shutil.rmtree(h, ignore_errors=True)
            raise SystemExit(f"couldn't fetch ECC ({' '.join(argv[:3])}): {r.stderr.strip()[-400:]}\n"
                             f"With ECC already on this machine: --ecc PATH")
    return h


def front(text: str) -> tuple[dict, str]:
    """(name/description from the YAML front matter, the rest)."""
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and k.strip() in ("name", "description") and not line.startswith((" ", "\t")):
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, text[m.end():]


@dataclass
class Entry:
    kind: str           # agents | skills | commands | rules
    name: str
    description: str
    ref: str            # path inside ECC: agents/x.md, skills/x, commands/x.md, rules/lang/x.md
    path: Path          # the file to read

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def body(self) -> str:
        return front(self.text())[1].strip()

    @property
    def chars(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


def _describe(path: Path) -> str:
    try:
        head = path.read_text(encoding="utf-8")[:4000]
    except (OSError, UnicodeDecodeError):
        return ""
    meta, body = front(head)
    if meta.get("description"):
        return meta["description"]
    for line in body.splitlines():   # rules and some commands have no front matter: the first real line
        line = line.strip().lstrip("#").strip()
        if line and not line.startswith(("---", "```", "<!--")):
            return line[:200]
    return ""


def catalog(ecc: Path, kind: str) -> list[Entry]:
    out = []
    if kind in ("agents", "commands"):
        for p in sorted((ecc / kind).glob("*.md")):
            out.append(Entry(kind, p.stem, _describe(p), f"{kind}/{p.name}", p))
    elif kind == "skills":
        for p in sorted((ecc / "skills").glob("*/SKILL.md")):
            out.append(Entry(kind, p.parent.name, _describe(p), f"skills/{p.parent.name}", p))
    elif kind == "rules":
        for p in sorted((ecc / "rules").glob("*/*.md")):
            out.append(Entry(kind, f"{p.parent.name}/{p.stem}", _describe(p), f"rules/{p.parent.name}/{p.name}", p))
    else:
        raise SystemExit(f"ECC has {', '.join(KINDS)}, not {kind!r}")
    return out


def languages(ecc: Path) -> list[str]:
    return sorted(p.name for p in (ecc / "rules").iterdir() if p.is_dir())


def words(text: str) -> set[str]:
    return {w.strip(".-") for w in WORD_RE.findall(text.lower())} - STOP


def rank(entries: list, query: str, limit: int = 0, least: float = 0.0) -> list:
    """Entries ordered by how well their name and description match `query`: words that few entries
    use count most, and a word in the name counts double. No match (or under `least`): left out."""
    import math
    want = words(query)
    docs = [(e, set(re.split(r"[-_/ ]+", e.name.lower())), words(e.description)) for e in entries]
    df: dict[str, int] = {}
    for _, name_words, desc_words in docs:
        for w in name_words | desc_words:
            df[w] = df.get(w, 0) + 1
    n = max(len(docs), 1)
    idf = lambda w: math.log((n + 1) / (df.get(w, 0) + 0.5))
    q = query.lower().strip()
    scored = []
    for e, name_words, desc_words in docs:
        score = sum(2 * idf(w) for w in want & name_words) + sum(idf(w) for w in want & (desc_words - name_words))
        if q and q in e.name.lower():
            score += 5
        if score > least:
            scored.append((score, e))
    scored.sort(key=lambda se: (-se[0], se[1].name))
    found = [e for _, e in scored]
    return found[:limit] if limit else found


def find(ecc: Path, kind: str, name: str) -> Entry:
    entries = catalog(ecc, kind)
    for e in entries:
        if e.name == name or e.ref == name:
            return e
    close = [e.name for e in rank(entries, name, 5)]
    hint = f"; close: {', '.join(close)}" if close else ""
    raise SystemExit(f"ECC {TAG} has no {kind[:-1]} named {name!r}{hint} (agent-team ecc {kind} to list them)")


# ---------------------------------------------------------------------------------------------
# Copying pieces into a project

def project_path(ref: str) -> str:
    """Where a piece lives in a project: team/skills/ecc/agents/x.md, team/skills/ecc/skills/x,
    team/rules/ecc/python/x.md."""
    if ref.startswith("rules/"):
        return f"{RULES_DIR}/{ref[len('rules/'):]}"
    return f"{SKILLS_DIR}/{ref}"


def copy(ecc: Path, ref: str, root: Path) -> str:
    """Copy one piece into the project (with ECC's notice beside it); returns its project path."""
    src, rel = ecc / ref, project_path(ref)
    dest = Path(root) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():   # a skill: its SKILL.md is what members read
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / "SKILL.md", dest / "SKILL.md")
    else:
        shutil.copyfile(src, dest)
    notice(ecc, Path(root) / (RULES_DIR if ref.startswith("rules/") else SKILLS_DIR))
    return rel


def notice(ecc: Path, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lic = ecc / "LICENSE"
    text = lic.read_text(encoding="utf-8") if lic.exists() else LICENSE_FALLBACK
    (folder / "NOTICE.md").write_text(NOTICE.format(tag=TAG, license=text), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Editing .team.toml by text, so comments and layout stay as they are

def _member_block(text: str, member: str) -> tuple[list[str], int]:
    blocks = re.split(r"(?m)^(?=\[\[agents\]\])", text)
    for i, block in enumerate(blocks):
        if re.search(rf'(?m)^name\s*=\s*"{re.escape(member)}"\s*$', block):
            return blocks, i
    raise SystemExit(f"no member named {member!r} in .team.toml")


def _add_to_list(block: str, key: str, entry: str, after: str) -> str:
    """`block` with `entry` added to its `key = [...]` list (created after the last `after` line)."""
    m = re.search(rf"(?m)^{key}\s*=\s*\[(.*?)\]", block, re.S)
    if m:
        if f'"{entry}"' in m.group(1):
            return block
        inner = m.group(1).rstrip().rstrip(",")
        new = f'{key} = [{inner}{", " if inner.strip() else ""}"{entry}"]'
        return block[:m.start()] + new + block[m.end():]
    lines = block.split("\n")
    at = max((n for n, l in enumerate(lines) if re.match(after, l)), default=0)
    lines.insert(at + 1, f'{key} = ["{entry}"]')
    return "\n".join(lines)


def add_skill(text: str, member: str, entry: str) -> str:
    """The team file with `entry` added to `member`'s skills."""
    blocks, i = _member_block(text, member)
    blocks[i] = _add_to_list(blocks[i], "skills", entry, r"^(name|role|provider|model|owns|effort|description)\s*=")
    return "".join(blocks)


def _project(text: str):
    m = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", text)
    if not m:
        raise SystemExit("no [project] table in .team.toml")
    return m


def add_to_project(text: str, key: str, entry: str) -> str:
    """The team file with `entry` added to the [project] list `key`."""
    m = _project(text)
    section = _add_to_list(m.group(1), key, entry, r"^[A-Za-z_]+\s*=")
    return text[:m.start(1)] + section + text[m.end(1):]


def remove_from_project(text: str, key: str, entry: str) -> str:
    """The team file without `entry` in the [project] list `key` (the line goes when it's empty)."""
    m = _project(text)
    section = m.group(1)
    lm = re.search(rf"(?m)^{key}\s*=\s*\[(.*?)\]\n?", section, re.S)
    if not lm:
        return text
    items = [x for x in re.findall(r'"([^"]*)"', lm.group(1)) if x != entry]
    line = (f'{key} = [{", ".join(chr(34) + x + chr(34) for x in items)}]\n') if items else ""
    section = section[:lm.start()] + line + section[lm.end():]
    return text[:m.start(1)] + section + text[m.end(1):]


def add_rule(text: str, entry: str) -> str:
    """The team file with `entry` added to [project].rules."""
    return add_to_project(text, "rules", entry)


def add_member(text: str, name: str, role: str, provider: str, model: str, description: str, skill: str) -> str:
    from .config_io import _str
    block = (f'\n[[agents]]\nname = {_str(name)}\nrole = {_str(role)}\nprovider = {_str(provider)}\n'
             + (f"model = {_str(model)}\n" if model else "")
             + (f"description = {_str(description[:300])}\n" if description else "")
             + f"skills = [{_str(skill)}]\n")
    return text.rstrip("\n") + "\n" + block


def save_team_file(root: Path, new: str) -> None:
    """Write .team.toml, keeping the old text if the new one doesn't load."""
    from .config import CONFIG_NAME, ConfigError, load
    path = Path(root) / CONFIG_NAME
    old = path.read_text(encoding="utf-8")
    path.write_text(new, encoding="utf-8")
    try:
        load(root)
    except ConfigError as e:
        path.write_text(old, encoding="utf-8")
        raise SystemExit(f"that would leave {CONFIG_NAME} invalid ({e}); it wasn't changed")
