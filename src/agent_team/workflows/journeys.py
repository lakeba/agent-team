"""The team writes its own behaviour checks: user journeys in team/behaviour.toml.

`agent-team behaviour suggest` has the lead write the first ones from VISION.md, the README and the
project. During `build`, the QA member (or the lead, without one) adds or updates the journeys the
task needs, before anyone builds it, the way QA writes tests first. The file is checked before it's
kept: a journey that doesn't parse is reported and the previous file stays.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .. import agent, context, files, ui
from ..config import SCENARIOS_FILE, AgentConfig, ConfigError, Team, scenario

GUIDE = '''# Behaviour journeys (team/behaviour.toml)

A journey uses the program the way a user would. agent-team runs each one on the version a build
starts from and with the team's changes, and shows the lead what a user would notice: the final
screen or page, errors, files, or (for a .NET library) the public API. Write a few journeys for what
matters most to users; each runs in seconds. The file holds only [[scenarios]] tables:

[[scenarios]]                 # a command-line program
name = "start and stop a timer"
kind = "terminal"
prepare = "dotnet build -c Release -o out"           # runs first in $PROJECT, not captured
run = 'dotnet "$PROJECT/out/Tally.dll" start client-a; dotnet "$PROJECT/out/Tally.dll" status'
input = []                    # lines typed into the program, if it asks for any
watch = ["."]                 # files the run leaves in its (empty) folder are compared

[[scenarios]]                 # a web app
name = "add a todo"
kind = "browser"
prepare = "npm ci && npm run build"
serve = "npm run preview -- --port 5173 --strictPort"   # started in $PROJECT, stopped after
url = "http://127.0.0.1:5173/"                          # only this machine
steps = ['fill textbox "New todo" with "buy milk"', 'press textbox "New todo" Enter',
         'wait for text "buy milk"']
# steps: goto /path, click ROLE "Name", fill ROLE "Name" with "text", press ROLE "Name" Enter,
#        check/uncheck ROLE "Name", select combobox "Name" option "Value", wait for text "...",
#        wait 500. ROLE is how a screen reader sees it: button, link, textbox, checkbox, combobox,
#        heading, ...; css "#id" and testid "x" work too.

[[scenarios]]                 # a .NET library's public API
name = "public API"
kind = "api"
prepare = "dotnet build -c Release -o out"
assembly = "out/MyLib.dll"

Rules:
- Runs start in an empty folder; $PROJECT is the version under test. Build in prepare.
- Make runs repeatable: no clocks, random values or network in what's compared, where you can.
- Keep journeys that still apply; change one only when the task changes what users should see.
- Names are unique and say what the user does.'''


def project_hints(team: Team) -> str:
    """What the project looks like, so the journeys use the right kind and commands."""
    root = Path(team.root)
    hints = []
    csproj = sorted(p.relative_to(root).as_posix() for p in root.glob("**/*.csproj")
                    if "/obj/" not in p.as_posix() and "/bin/" not in p.as_posix())[:5]
    if csproj:
        hints.append(f".NET projects: {', '.join(csproj)} (OutputType Exe is a program; otherwise a library: "
                     f"use kind = \"api\")")
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except ValueError:
            scripts = {}
        hints.append(f"package.json scripts: {', '.join(f'{k}: {v}' for k, v in list(scripts.items())[:8]) or 'none'}")
    if (root / "index.html").is_file() or (root / "public" / "index.html").is_file():
        hints.append("there's an index.html: a web app (kind = \"browser\")")
    if any((root / m).exists() for m in ("pyproject.toml", "setup.py")):
        hints.append("a Python project")
    if team.project.test_command:
        hints.append(f"the test command is: {team.project.test_command}")
    return "\n".join(f"- {h}" for h in hints) or "- (nothing recognised; read the project files)"


def current(team: Team) -> str:
    path = Path(team.root) / SCENARIOS_FILE
    return path.read_text(encoding="utf-8") if path.is_file() else "(none yet)"


def check(text: str) -> str:
    """"" if the file is a valid set of journeys, else what's wrong."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return f"not valid TOML: {e}"
    if set(data) - {"scenarios"}:
        return f"only [[scenarios]] tables go in {SCENARIOS_FILE}"
    names = []
    try:
        for i, t in enumerate(data.get("scenarios") or []):
            names.append(scenario(dict(t), f"[[scenarios]] #{i + 1}").name)
    except ConfigError as e:
        return str(e)
    if len(names) != len(set(names)):
        return "two journeys share a name"
    return ""


def write(team: Team, cfg: AgentConfig, request: str, log=None) -> list[str]:
    """Ask `cfg` for team/behaviour.toml; keep it only if it's valid. Returns the files written."""
    writer = agent.make(team, cfg, "qa" if cfg.role == "qa" else "lead", file_format=files.FILE_FORMAT,
                        test_paths=SCENARIOS_FILE)
    prompt = (f"{request}\n\n{GUIDE}\n\n# What this project looks like\n\n{project_hints(team)}\n\n"
              f"# The current {SCENARIOS_FILE}\n\n{current(team)}\n\n"
              f"Reply with the whole new {SCENARIOS_FILE} in a <file path=\"{SCENARIOS_FILE}\"> block, or with "
              f"NO CHANGE if the journeys already cover it.")
    for _ in range(2):
        reply = writer.turn(prompt)
        text = _block(reply)
        if text is None:
            if log:
                log.record(f"{cfg.name}: journeys", reply)
            return []
        problem = check(text)
        if not problem:
            path = Path(team.root) / SCENARIOS_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text.rstrip() + "\n", encoding="utf-8")
            if log:
                log.record(f"{cfg.name}: journeys", reply, [SCENARIOS_FILE])
            ui.action(f"{cfg.name} wrote {SCENARIOS_FILE}")
            return [SCENARIOS_FILE]
        prompt = f"That {SCENARIOS_FILE} can't be used: {problem}. Fix it and send the whole file again."
    ui.warn(f"{cfg.name}'s journeys weren't valid, so {SCENARIOS_FILE} stays as it was")
    return []


def _block(reply: str) -> str | None:
    import re
    m = re.search(r'<file path="' + re.escape(SCENARIOS_FILE) + r'">\n?(.*?)</file>', reply, re.S)
    return m.group(1) if m else None


def suggest(team: Team) -> list[str]:
    """The lead writes the first journeys from the vision, the README and the project."""
    lead = team.by_role("lead")
    vision = context.vision(team) or "(no VISION.md: use the README)"
    files_text = context.for_topic(team, query="what users do with this program")
    return write(team, lead, f"Write the behaviour journeys for this project: what its users do most and what "
                             f"must keep working.\n\n# The product vision\n\n{vision}\n\n# Project files\n\n{files_text}")


def for_task(team: Team, cfg: AgentConfig, task: str, plan: str, log=None) -> list[str]:
    """Before the builders start: add or update the journeys this task needs (like tests first)."""
    return write(team, cfg, f"Task about to be built: {task}\n\n# The plan\n\n{plan}\n\nAdd or update the "
                            f"journeys that show this task working for a user (and keep the others).", log)
