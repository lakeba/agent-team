"""Team memory: rules the team learned from its own reviews, carried into every later prompt.

When a reviewer blocks for a reason that will matter again ("a release version must exist
before the changelog names it"), it adds a line `LESSON: <rule>`. Those lines are kept in
`.team/memory.md`, newest last, without duplicates, at most MAX_LESSONS, and every member sees
them in its instructions, so the same mistake doesn't cost another review round. People can
add or forget lessons with `agent-team memory`.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import files, usage

FILE = "memory.md"
MAX_LESSONS = 40
LESSON_RE = re.compile(r"^\s*(?:[-*]\s*)?LESSON:\s*(.+?)\s*$", re.M)
LINE_RE = re.compile(r"^- (.+?)(?:  _\((.+?)\)_)?$")


def _path(root) -> Path:
    return Path(root) / files.LOG_DIR / FILE


def lessons(root) -> list[dict]:
    """[{text, source}] oldest first."""
    path = _path(root)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(line.strip())
        if m:
            out.append({"text": m.group(1).strip(), "source": m.group(2) or ""})
    return out


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _save(root, items: list[dict]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"- {i['text']}" + (f"  _({i['source']})_" if i["source"] else "") for i in items)
    path.write_text("# What this team has learned on this project\n\n" + body + ("\n" if body else ""), encoding="utf-8")


def add(root, texts: list[str], source: str = "") -> list[str]:
    """Add new lessons (duplicates ignored); returns the ones added."""
    items = lessons(root)
    seen = {_key(i["text"]) for i in items}
    added = []
    for t in texts:
        t = t.strip().strip("`")[:300]
        if len(t) < 10 or _key(t) in seen:
            continue
        items.append({"text": t, "source": source})
        seen.add(_key(t))
        added.append(t)
    if added:
        _save(root, items[-MAX_LESSONS:])
    return added


def forget(root, number: int) -> str:
    items = lessons(root)
    if not 1 <= number <= len(items):
        raise ValueError(f"there's no lesson {number}; there are {len(items)}")
    gone = items.pop(number - 1)
    _save(root, items)
    return gone["text"]


def learn(team, text: str, who: str) -> list[str]:
    """Keep the LESSON lines of a review."""
    found = LESSON_RE.findall(files.strip_files(text))[:2]
    return add(team.root, found, f"{who}, {usage.now()[:10]}") if found else []


def for_prompt(root) -> str:
    items = lessons(root)
    if not items:
        return ""
    return ("# Lessons this team has learned on this project\n"
            "Follow these; each one cost a review round before.\n" + "\n".join(f"- {i['text']}" for i in items))
