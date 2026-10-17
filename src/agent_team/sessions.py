"""Session summaries, after ECC's save-session and resume-session: what each run did, kept short.

At the end of every build and fix, agent-team writes .team/sessions/<when>-<workflow>.md: the task,
how it ended, the rounds, the files changed, what it cost and the lessons it added. No model is
called to write it. The lead's next plan starts from the latest few ("# Recent work"), so the team
remembers what it did yesterday without rereading every log. `agent-team sessions` lists them.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import files, usage

FOLDER = "sessions"
RECENT = 3


def folder(root) -> Path:
    return Path(root) / files.LOG_DIR / FOLDER


def save(team, workflow: str, task: str, outcome: str, rounds: int, changed, lessons: list[str] | None = None,
         notes: str = "") -> Path:
    root = Path(team.root)
    run = usage.current_run()
    cost = 0.0
    if run:
        by_run = usage.summarize([e for e in usage.load(root) if e.get("run") == run], team.pricing)["by_run"]
        cost = sum(v.get("cost", 0) for v in by_run.values())
    stamp = datetime.now(timezone.utc)
    path = folder(root) / f"{stamp.strftime('%Y-%m-%d-%H%M%S')}-{workflow}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    changed = sorted(changed or [])
    body = [f"# {workflow}: {task.splitlines()[0][:200]}", "",
            f"- When: {stamp.strftime('%Y-%m-%d %H:%M')} UTC",
            f"- Outcome: {outcome}", f"- Rounds: {rounds}",
            f"- Cost: ${cost:.2f}" if cost else "- Cost: $0 (local models or none recorded)",
            f"- Files changed: {', '.join(changed) if changed else 'none'}"]
    if lessons:
        body += ["", "Lessons learned:", *[f"- {l}" for l in lessons]]
    if notes.strip():
        body += ["", "Notes:", notes.strip()[:1500]]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def listing(root) -> list[Path]:
    f = folder(root)
    return sorted(f.glob("*.md"), reverse=True) if f.is_dir() else []


def summary_line(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
    get = lambda key: (re.search(rf"^- {key}: (.+)$", text, re.M) or [None, ""])[1]
    files_changed = get("Files changed")
    if len(files_changed) > 160:
        files_changed = files_changed[:160] + "…"
    return f"{get('When')[:10]} {title} ({get('Outcome')}; files: {files_changed})"


def for_prompt(root) -> str:
    recent = listing(root)[:RECENT]
    if not recent:
        return ""
    return ("# Recent work on this project (newest first)\n" +
            "\n".join(f"- {summary_line(p)}" for p in recent))
