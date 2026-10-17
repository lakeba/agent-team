"""agent-team's built-in library: specialist agents, skills, playbooks and rules.

The library ships with agent-team (src/agent_team/builtin/) and needs nothing downloaded:

    agents     specialists (architect, security-reviewer, python-reviewer, ...): a new member
               (`library hire`) or extra know-how for one you have (`library give`)
    skills     focused guidance (tdd-workflow, api-design, python-testing, ...): given to a member, or
               read on demand when `[project].library = ["builtin"]`
    playbooks  written procedures (code-review, plan-feature, fix-bug, ...): `agent-team playbook run`
    rules      standards for every member (common, python, typescript, ...): `library add-rules`

A project can add its own on top: folders listed in `[project].library` (skill folders or Markdown
files), rules in `[project].rules`. Pieces copied into a project go under team/skills/ and
team/rules/, so they're reviewed, edited and committed like any other file.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

HOME = Path(__file__).parent / "builtin"
KINDS = ("agents", "skills", "playbooks", "rules")
SKILLS_DIR, RULES_DIR = "team/skills", "team/rules"
FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}")
STOP = set("the and for with that this from into your you are use when what how all any can not but out "
           "its has have was were will would should could their them they then than also more most each "
           "other such only over under about after before using used make made file files task tasks "
           "add adds added run runs running result results object objects print prints flag flags write writes "
           "build builds new change changes update updates need needs like just sure then via one two".split())


def front(text: str) -> tuple[dict, str]:
    """(name/description/role/mode from the YAML front matter, the rest)."""
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and k.strip() in ("name", "description", "role", "mode") and not line.startswith((" ", "\t")):
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, text[m.end():]


@dataclass
class Entry:
    kind: str           # agents | skills | playbooks | rules
    name: str
    description: str
    ref: str            # path inside the kit: agents/x.md, skills/x, playbooks/x.md, rules/lang/x.md
    path: Path          # the file to read
    meta: dict

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


def describe(path: Path) -> tuple[dict, str]:
    """(front matter, a one-line description) of a Markdown file."""
    try:
        head = path.read_text(encoding="utf-8")[:4000]
    except (OSError, UnicodeDecodeError):
        return {}, ""
    meta, body = front(head)
    if meta.get("description"):
        return meta, meta["description"]
    for line in body.splitlines():   # no front matter: the first real line
        line = line.strip().lstrip("#").strip()
        if line and not line.startswith(("---", "```", "<!--")):
            return meta, line[:200]
    return meta, ""


def catalog(kind: str, home: Path = HOME) -> list[Entry]:
    out = []
    if kind in ("agents", "playbooks"):
        paths = [(p, p.stem, f"{kind}/{p.name}") for p in sorted((home / kind).glob("*.md"))]
    elif kind == "skills":
        paths = [(p, p.parent.name, f"skills/{p.parent.name}") for p in sorted((home / "skills").glob("*/SKILL.md"))]
    elif kind == "rules":
        paths = [(p, f"{p.parent.name}/{p.stem}", f"rules/{p.parent.name}/{p.name}")
                 for p in sorted((home / "rules").glob("*/*.md"))]
    else:
        raise SystemExit(f"the library has {', '.join(KINDS)}, not {kind!r}")
    for p, name, ref in paths:
        meta, desc = describe(p)
        out.append(Entry(kind, name, desc, ref, p, meta))
    return out


def languages(home: Path = HOME) -> list[str]:
    return sorted(p.name for p in (home / "rules").iterdir() if p.is_dir() and p.name != "common")


def words(text: str) -> set[str]:
    return {w.strip(".-") for w in WORD_RE.findall(text.lower())} - STOP


def rank(entries: list, query: str, limit: int = 0, least: float = 0.0) -> list:
    """Entries ordered by how well their name and description match `query`: words few entries use
    count most, and a word in the name counts double. No match (or under `least`): left out."""
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


def find(kind: str, name: str, home: Path = HOME) -> Entry:
    entries = catalog(kind, home)
    for e in entries:
        if e.name == name or e.ref == name:
            return e
    close = [e.name for e in rank(entries, name, 5)]
    hint = f"; close: {', '.join(close)}" if close else ""
    raise SystemExit(f"the library has no {kind[:-1]} named {name!r}{hint} (agent-team library {kind} lists them)")


# ---------------------------------------------------------------------------------------------
# Copying pieces into a project

def project_path(ref: str) -> str:
    """Where a piece lives in a project: team/skills/<agent>.md, team/skills/<skill>/,
    team/rules/<lang>/<x>.md."""
    kind, _, rest = ref.partition("/")
    if kind == "rules":
        return f"{RULES_DIR}/{rest}"
    if kind == "skills":
        return f"{SKILLS_DIR}/{rest}"
    return f"{SKILLS_DIR}/{rest}"   # an agent's know-how, as a skill file


def copy(ref: str, root: Path, home: Path = HOME) -> str:
    """Copy one piece into the project; returns its project path. An existing copy is kept (it may
    have been edited)."""
    src, rel = home / ref, project_path(ref)
    dest = Path(root) / rel
    if src.is_dir():   # a skill: its SKILL.md is what members read
        dest.mkdir(parents=True, exist_ok=True)
        if not (dest / "SKILL.md").exists():
            (dest / "SKILL.md").write_text((src / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return rel


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
