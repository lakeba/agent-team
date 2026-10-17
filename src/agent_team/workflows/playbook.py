"""ECC's commands as playbooks: `agent-team ecc run NAME [what]`.

An ECC command is a written procedure (review this code, plan a feature, check test coverage,
refactor dead code, ...). By default one member (the lead unless `--member` says otherwise)
follows it on the project as it is and reports, without changing any file. With `--build`, it
becomes the task of a normal build: the plan, the builders, tests, behaviour checks, review and,
with `--branch --pr`, a pull request.

Commands written for Claude Code mention its tools (Read, Bash, Task, ...): the member works from
the project files it's given instead, and anything a command would run is listed for you.
"""
from __future__ import annotations

from .. import agent, context, ecc, files, ui
from ..config import Team

READ_ONLY = """You're following a playbook from ECC's command library on this project. It was written for
coding agents with tools (reading files, running commands, starting subagents): you have the
project files below instead, so do what the playbook asks with them. Don't change any file: no
<file> or <edit> blocks. Where it says to run a command, say which command and what to look for.
Report in plain Markdown, ending with the actions you recommend, most important first."""


def text(entry: ecc.Entry, what: str) -> str:
    body = entry.body()
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", what or "(nothing given)")
    return body + (f"\n\n# What it's for this time\n\n{what}" if what else "")


def run(team: Team, name: str, what: str = "", member: str = "", build: bool = False, source: str = "",
        **build_args) -> bool:
    home = ecc.fetch(source)
    entry = ecc.find(home, "commands", name)
    procedure = text(entry, what)
    if build:
        from . import build as build_flow
        task = (what or entry.description or name).strip()
        return build_flow.run(team, f"{task}\n\nFollow this playbook (ECC's /{name}):\n\n{procedure}", **build_args)
    cfg = team.get(member) if member else team.by_role("lead")
    reader = agent.make(team, cfg, "member", label_suffix=f" · /{name}")
    reader.system = f"{reader.system.rstrip()}\n\n{READ_ONLY}"
    log = files.Log(team.root, f"playbook-{name}", f"Playbook /{name}: {what or entry.description}")
    ui.heading(f"/{name} ({cfg.name}): {entry.description[:100]}")
    focus = context.choose(team, reader, f"{name}: {what}\n\n{procedure[:2000]}")
    reply = reader.turn(f"# The playbook: /{name}\n\n{procedure}\n\n# Project files\n\n{focus.render()}")
    reply = files.strip_files(reply)
    log.record(f"{cfg.name}: /{name}", reply)
    ui.say(reply)
    ui.say(f"\nLog: {log.path}")
    return True
