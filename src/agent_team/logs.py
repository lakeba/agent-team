"""Read the team's run logs (.team/logs/*.md) back into structured runs for the dashboard.

A log is a sequence of runs ("# title"), each a sequence of entries ("## who: what"). Newer logs
carry `<!-- run ... -->` and `<!-- at ... -->` timestamps; older ones don't, and still parse.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import files

# Logs written by this version mark every run and entry heading with a timestamp comment on the next
# line, so headings inside the agents' own replies are never mistaken for structure.
RUN_MARKED = re.compile(r"^# (?!#)(.+)\n<!-- run \S+ -->$", re.M)
ENTRY_MARKED = re.compile(r"^## (?!#)(.+)\n<!-- at \S+ -->$", re.M)
# Older logs have no markers: accept only the shapes the workflows wrote.
LEGACY_RUN = re.compile(r"^# ((?:Task|Ops shift on|Marketing|Repository setup for|Roadmap discussion|Build:|Discussion:)[^\n]*)$", re.M)
LEGACY_ENTRY = re.compile(r"^## ((\w+): (?:plan|review|round|build|fact-check|sign-off|action|shift summary|brief|brief review|draft)\b[^\n]*|Final roadmap|Tests: round \d+|[A-Z]\w+)$", re.M)
RUN_ID_RE = re.compile(r"<!-- run (\S+) -->")
AT_RE = re.compile(r"<!-- at (\S+) -->")
ACTION_RE = re.compile(r"(merged PR #\d+[^\n]*|released v[\d.]+[^\n]*|opened release PR #\d+|closed #\d+[^\n]*)")
FILES_RE = re.compile(r"^_Files written: (.+)_$", re.M)
EXCERPT = 2000


def _split(text: str, rx: re.Pattern, names: set[str] | None = None) -> list[tuple[str, str]]:
    """[(heading, body)] for each heading rx matches. A bare one-word legacy heading counts only if
    the word is a known team member (to skip headings inside the agents' replies)."""
    matches = []
    for m in rx.finditer(text):
        head = m.group(1).strip()
        if names is not None and re.fullmatch(r"[A-Z]\w+", head) and head not in names:
            continue
        matches.append(m)
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start():end].partition("\n")[2]   # keep the timestamp marker in the body
        out.append((m.group(1).strip(), body))
    return out


def _entry(heading: str, body: str) -> dict:
    who, _, what = heading.partition(": ")
    at = AT_RE.search(body)
    clean = AT_RE.sub("", body)
    noted = FILES_RE.findall(clean)
    written = noted[0].split(",") if noted else [m[0] for m in files.FILE_RE.findall(clean)]
    marker = (files.last_marker(files.VERDICT_RE, clean) or files.last_marker(files.SIGNOFF_RE, clean)
              or files.last_marker(files.STATUS_RE, clean))
    text = files.strip_files(FILES_RE.sub("", clean)).strip()
    return {
        "who": who.strip(), "what": what.strip(), "at": at.group(1) if at else None,
        "marker": marker or None,
        "files": [f.strip() for f in written],
        "actions": ACTION_RE.findall(text) if what.strip() in ("action", "") else [],
        "text": text[:EXCERPT] + ("…" if len(text) > EXCERPT else ""),
    }


def _outcome(workflow: str, entries: list[dict]) -> str:
    markers = [e["marker"] for e in entries if e["marker"]]
    if workflow in ("build", "market", "setup"):
        reviews = [e for e in entries if e["what"].startswith("review") or e["what"].startswith("brief review")]
        if reviews and reviews[-1]["marker"] == "APPROVED":
            rounds = sum(1 for e in reviews if not e["what"].startswith("brief"))
            return f"approved after {rounds} round(s)" if rounds else "brief approved"
        return "not approved" if reviews else "incomplete"
    if workflow == "discuss":
        final = [e for e in entries if e["who"] == "Final roadmap"]
        return "roadmap written" if final and final[-1]["files"] else ("no roadmap written" if final else "incomplete")
    if workflow == "ship":
        acts = [a for e in entries for a in e["actions"]]
        return "; ".join(acts) if acts else "no merges or releases"
    return ""


def parse(root: str | Path) -> list[dict]:
    """All runs in all logs, newest first where timestamps allow (else file order)."""
    folder = Path(root) / files.LOG_DIR / "logs"
    runs = []
    for path in sorted(folder.glob("*.md")) if folder.exists() else []:
        workflow = path.stem
        text = path.read_text(encoding="utf-8", errors="replace")
        # Logs only grow at the end, so a file may hold older unmarked runs followed by marked ones.
        first = RUN_MARKED.search(text)
        cut = first.start() if first else len(text)
        names = set(re.findall(r"^## (\w+): ", text, re.M)) | {"Atlas", "Forge", "Spark", "Harbor"}
        sections = ([(t, b, False) for t, b in _split(text[:cut], LEGACY_RUN)] +
                    [(t, b, True) for t, b in _split(text[cut:], RUN_MARKED)])
        for i, (title, body, marked) in enumerate(sections):
            rid = RUN_ID_RE.search(body) if marked else None
            entries = [_entry(h, b) for h, b in (_split(body, ENTRY_MARKED) if marked
                                                 else _split(body, LEGACY_ENTRY, names))]
            if not marked and title == "Task":   # older build logs put the task on the next line
                first_line = next((l.strip() for l in body.splitlines() if l.strip() and not l.startswith("<!--")), "")
                title = first_line[:200] or title
            started = rid.group(1).split("@", 1)[1] if rid else None
            ended = next((e["at"] for e in reversed(entries) if e["at"]), None)
            runs.append({"id": rid.group(1) if rid else f"{workflow}#{i + 1}", "workflow": workflow,
                         "title": title, "started": started, "ended": ended, "order": i,
                         "entries": entries, "outcome": _outcome(workflow, entries),
                         "rounds": sum(1 for e in entries if re.match(r"(review|round|build|draft) \d+", e["what"]))})
    runs.sort(key=lambda r: (r["started"] or "", r["workflow"], r["order"]), reverse=True)
    return runs
