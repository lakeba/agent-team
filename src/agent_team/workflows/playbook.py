"""Playbooks: written procedures a member follows, `agent-team playbook run NAME [what]`.

A playbook (code-review, plan-feature, fix-bug, security-review, ...) is a Markdown file with a
procedure; `$ARGUMENTS` in it becomes what you said it's for. The built-in ones live in
builtin/playbooks/, and a project adds its own in team/playbooks/ (a project playbook with the
same name wins).

Each playbook has a mode. A `report` playbook has one member (the lead unless `--member` says
otherwise) follow it on the project as it is and report, without changing any file. A `build`
playbook becomes the task of a normal build: the plan, the builders, tests, behaviour checks,
review and, with `--branch --pr`, a pull request. `--report` and `--build` override the mode.
"""
from __future__ import annotations

from pathlib import Path

from .. import agent, context, files, kit, ui
from ..config import Team

PROJECT_DIR = "team/playbooks"

READ_ONLY = """You're following a playbook on this project. You have the project files below; do what the
playbook asks with them. Don't change any file: no <file> or <edit> blocks. Where it says to run a
command, say which command and what to look for in its output. Report in plain Markdown, ending with
the actions you recommend, most important first."""


def catalog(root: Path | None = None) -> list[kit.Entry]:
    """The built-in playbooks, with the project's own (team/playbooks/*.md) in their place or added."""
    found = {e.name: e for e in kit.catalog("playbooks")}
    folder = Path(root) / PROJECT_DIR if root else None
    if folder and folder.is_dir():
        for p in sorted(folder.glob("*.md")):
            meta, desc = kit.describe(p)
            found[p.stem] = kit.Entry("playbooks", p.stem, desc, f"{PROJECT_DIR}/{p.name}", p, meta)
    return sorted(found.values(), key=lambda e: e.name)


def find(name: str, root: Path | None = None) -> kit.Entry:
    entries = catalog(root)
    for e in entries:
        if e.name == name:
            return e
    close = [e.name for e in kit.rank(entries, name, 5)]
    raise SystemExit(f"no playbook named {name!r}" + (f"; close: {', '.join(close)}" if close else "") +
                     " (agent-team playbook list)")


def text(entry: kit.Entry, what: str) -> str:
    body = entry.body()
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", what or "the whole project")
    return body + (f"\n\n# What it's for this time\n\n{what}" if what else "")


def run(team: Team, name: str, what: str = "", member: str = "", mode: str = "", **build_args) -> bool:
    entry = find(name, team.root)
    procedure = text(entry, what)
    mode = mode or entry.meta.get("mode", "report")
    if mode == "build":
        from . import build as build_flow
        task = (what or entry.description or name).strip()
        return build_flow.run(team, f"{task}\n\nFollow this playbook ({name}):\n\n{procedure}", **build_args)
    cfg = team.get(member) if member else team.by_role("lead")
    reader = agent.make(team, cfg, "member", label_suffix=f" · {name}")
    reader.system = f"{reader.system.rstrip()}\n\n{READ_ONLY}"
    log = files.Log(team.root, f"playbook-{name}", f"Playbook {name}: {what or entry.description}")
    ui.heading(f"{name} ({cfg.name}): {entry.description[:100]}")
    focus = context.choose(team, reader, f"{name}: {what}\n\n{procedure[:2000]}")
    reply = reader.turn(f"# The playbook: {name}\n\n{procedure}\n\n# Project files\n\n{focus.render()}")
    reply = files.strip_files(reply)
    log.record(f"{cfg.name}: {name}", reply)
    ui.say(reply)
    ui.say(f"\nLog: {log.path}")
    return True
