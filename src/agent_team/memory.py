"""Team memory: rules the team learned from its own reviews, carried into every later prompt.

When a reviewer blocks for a reason that will matter again ("a release version must exist
before the changelog names it"), it adds a line `LESSON: <rule>`. Those lines are kept in
`.team/memory.md`, newest last, without duplicates, at most MAX_LESSONS, and every member sees
them in its instructions, so the same mistake doesn't cost another review round. People can
add or forget lessons with `agent-team memory`.

Like ECC's instincts, each lesson has a confidence: 0.5 when a reviewer first states it, 0.9 when
a person adds it, and higher each time a review states it again. Members see the most confident
first. A lesson the team keeps relearning can be promoted to a project rule (`memory promote N`,
into team/rules/learned.md), and lessons move between projects with `memory export` / `import`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import files, usage

FILE = "memory.md"
SCORES = "memory-scores.json"
LEARNED_RULES = "team/rules/learned.md"
FIRST, BY_PERSON, STEP, MOST = 0.5, 0.9, 0.15, 0.95
PROMOTE_AT = (3, 0.8)           # seen this often, at least this confident: worth a rule
MAX_LESSONS = 40
LESSON_RE = re.compile(r"^\s*(?:[-*]\s*)?LESSON:\s*(.+?)\s*$", re.M)
LINE_RE = re.compile(r"^- (.+?)(?:  _\((.+?)\)_)?$")


def _path(root) -> Path:
    return Path(root) / files.LOG_DIR / FILE


def _scores_path(root) -> Path:
    return Path(root) / files.LOG_DIR / SCORES


def scores(root) -> dict:
    try:
        return json.loads(_scores_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_scores(root, data: dict) -> None:
    path = _scores_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def score(root, text: str, data: dict | None = None) -> dict:
    """{confidence, seen} of one lesson."""
    data = scores(root) if data is None else data
    return data.get(_key(text), {"confidence": FIRST, "seen": 1})


def lessons(root) -> list[dict]:
    """[{text, source, confidence, seen}] oldest first."""
    path = _path(root)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(line.strip())
        if m:
            out.append({"text": m.group(1).strip(), "source": m.group(2) or ""})
    data = scores(root)
    for i in out:
        i.update(score(root, i["text"], data))
    return out


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _save(root, items: list[dict]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"- {i['text']}" + (f"  _({i['source']})_" if i["source"] else "") for i in items)
    path.write_text("# What this team has learned on this project\n\n" + body + ("\n" if body else ""), encoding="utf-8")


def add(root, texts: list[str], source: str = "", confidence: float = FIRST) -> list[str]:
    """Add new lessons; one already known is seen again and gains confidence. Returns the new ones."""
    items = lessons(root)
    seen = {_key(i["text"]) for i in items}
    data = scores(root)
    added = []
    for t in texts:
        t = t.strip().strip("`")[:300]
        if len(t) < 10:
            continue
        k = _key(t)
        if k in seen:
            old = data.get(k, {"confidence": FIRST, "seen": 1})
            data[k] = {"confidence": round(min(MOST, max(old["confidence"], confidence) + STEP), 2), "seen": old["seen"] + 1}
            continue
        items.append({"text": t, "source": source})
        data[k] = {"confidence": confidence, "seen": 1}
        seen.add(k)
        added.append(t)
    if added:
        _save(root, items[-MAX_LESSONS:])
    _save_scores(root, data)
    return added


def forget(root, number: int) -> str:
    items = lessons(root)
    if not 1 <= number <= len(items):
        raise ValueError(f"there's no lesson {number}; there are {len(items)}")
    gone = items.pop(number - 1)
    _save(root, items)
    return gone["text"]


def promote(root, number: int) -> str:
    """Move lesson `number` into team/rules/learned.md (a project rule); returns its text. The caller
    adds the file to [project].rules."""
    text = forget(root, number)
    path = Path(root) / LEARNED_RULES
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "" if path.exists() else "# Rules this team learned on this project\n\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{head}- {text}\n")
    return text


def promotable(root) -> list[int]:
    """Numbers of the lessons seen often and confidently enough to become rules."""
    times, conf = PROMOTE_AT
    return [n for n, i in enumerate(lessons(root), 1) if i["seen"] >= times and i["confidence"] >= conf]


def export(root) -> list[dict]:
    return [{k: i[k] for k in ("text", "confidence", "seen")} for i in lessons(root)]


def import_(root, items: list) -> list[str]:
    """Lessons from another project (from `memory export`), at a little less confidence than they had."""
    added = []
    for i in items if isinstance(items, list) else []:
        if isinstance(i, dict) and isinstance(i.get("text"), str):
            conf = float(i.get("confidence") or FIRST)
            added += add(root, [i["text"]], "imported", round(max(FIRST, conf - STEP), 2))
    return added


def learn(team, text: str, who: str) -> list[str]:
    """Keep the LESSON lines of a review."""
    found = LESSON_RE.findall(files.strip_files(text))[:2]
    return add(team.root, found, f"{who}, {usage.now()[:10]}") if found else []


def for_prompt(root) -> str:
    items = sorted(lessons(root), key=lambda i: -i["confidence"])
    if not items:
        return ""
    return ("# Lessons this team has learned on this project\n"
            "Follow these; each one cost a review round before. The most confident come first.\n" +
            "\n".join(f"- {i['text']}" + (f" (seen {i['seen']} times)" if i["seen"] > 1 else "") for i in items))
