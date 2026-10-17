"""`agent-team try`: see the team work in about a minute, before setting anything up.

A small sample project (tipsplit, a bill splitter) is copied into a temporary folder with git, a
team file and a vision, and the team builds one small feature there: the lead plans, a builder
writes the code and a test, the tests run, the lead reviews. If REA is installed, a behaviour check
runs too. Nothing touches GitHub or your projects.

Models, in order: Claude if your Anthropic key is saved (about a minute and a few cents), else
Ollama on this machine or its host (slower on a laptop), else a replay: a recorded run with no
model called, so the flow can be seen anywhere. `--with` picks one.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from importlib import resources
from pathlib import Path

from .. import ui

SAMPLE = "tipsplit"
JOURNEY = '''
[[scenarios]]
name = "split with rounding"
run = 'export PYTHONPATH="$PROJECT/src"; {py} -m tipsplit.cli 120 --people 4 --tip 15; {py} -m tipsplit.cli 100 --people 3 --round 0.05'
'''


def choose(wanted: str) -> tuple[str, str, str]:
    """(mode, Ollama address, Ollama model) for --with auto|claude|ollama|replay."""
    from .. import keys
    from ..readiness import find_ollama
    keys.load_into_env()
    if wanted in ("auto", "claude") and os.environ.get("ANTHROPIC_API_KEY"):
        return "claude", "", ""
    if wanted == "claude":
        raise SystemExit("No Anthropic key saved: agent-team keys set ANTHROPIC_API_KEY (or --with ollama / replay)")
    if wanted in ("auto", "ollama"):
        found = find_ollama()
        if found:
            from .init import choose_model
            url, models = found[0]
            return "ollama", url, choose_model(models)[0]
        if wanted == "ollama":
            raise SystemExit("No Ollama server answered here or on this machine's host (or use --with replay)")
    return "replay", "", ""


PYTHON = shlex.quote(sys.executable)   # agent-team's own Python: 3.11 or newer, wherever it runs


def team_file(mode: str, url: str, model: str) -> str:
    provider = {"claude": '[providers.claude]\nkind = "anthropic"\n',
                "ollama": f'[providers.local]\nkind = "ollama"\nurl = "{url}"\n',
                "replay": '[providers.replay]\nkind = "replay"\n'}[mode]
    name, lead_model, build_model = {"claude": ("claude", "claude-sonnet-5-5", "claude-sonnet-5-5"),
                                     "ollama": ("local", model, model), "replay": ("replay", "recorded", "recorded")}[mode]
    py = PYTHON.replace('"', '\\"')
    return f'''# agent-team try: a throwaway team for the tipsplit sample
[project]
name = "tipsplit"
test_command = "{py} -m unittest discover -s tests -v"
guarantees = ["All tests pass", "Shares are never rounded down: nobody pays short"]
review = "snapshot"

{provider}
[[agents]]
name = "Atlas"
role = "lead"
provider = "{name}"
model = "{lead_model}"

[[agents]]
name = "Forge"
role = "builder"
provider = "{name}"
model = "{build_model}"
'''


def copy_sample(dest: Path) -> None:
    src = resources.files("agent_team").joinpath("demo", SAMPLE)
    for rel in ("README.md", "VISION.md", "pyproject.toml", "src/tipsplit/__init__.py", "src/tipsplit/cli.py",
                "tests/test_cli.py"):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(src.joinpath(*rel.split("/")).read_text(encoding="utf-8"), encoding="utf-8")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def run(wanted: str = "auto", keep: bool = False, folder: Path | None = None) -> int:
    from .. import config, rea
    from . import build
    mode, url, model = choose(wanted)
    root = Path(folder) if folder else Path(tempfile.mkdtemp(prefix="agent-team-try-"))
    root.mkdir(parents=True, exist_ok=True)
    copy_sample(root)
    (root / ".team.toml").write_text(team_file(mode, url, model), encoding="utf-8")
    (root / ".gitignore").write_text(".team/\n__pycache__/\n", encoding="utf-8")
    command, args, _ = rea.find()
    if command and mode != "replay":   # behaviour checks too, when REA is here
        rea.configure(root, command, args)
        (root / "team").mkdir(exist_ok=True)
        (root / "team" / "behaviour.toml").write_text(JOURNEY.lstrip().replace("{py}", PYTHON), encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "-c", "user.name=agent-team", "-c", "user.email=try@agent-team.local", "commit", "-q", "-m", "tipsplit")
    task = json.loads(resources.files("agent_team").joinpath("demo", "replay.json").read_text(encoding="utf-8"))["task"]

    words = {"claude": "Claude (Sonnet), about a minute and a few cents",
             "ollama": f"{model} on Ollama at {url}: free, but a laptop takes a few minutes",
             "replay": "a replay: a recorded run, no model is called (save a key or start Ollama for a live one)"}
    ui.heading("agent-team try")
    ui.say(f"A sample project, tipsplit, in {root}\nThe team: Atlas plans and reviews, Forge builds. Models: {words[mode]}.\n"
           f"Task: {task}\n")
    started = time.monotonic()
    team = config.load(root)
    approved = build.run(team, task, rounds=2)
    seconds = time.monotonic() - started

    from .. import usage
    changed = git(root, "status", "--short")
    ui.heading("What happened")
    ui.say(f"  {'Approved' if approved else 'Not approved'} in {seconds:.0f} s"
           + (f", estimated cost ${usage.summarize(usage.load(root))['total']['cost']:.2f}" if mode == "claude" else "") + ".")
    ui.say("  Files changed:\n" + "\n".join(f"    {l}" for l in changed.splitlines() if "PLAN.md" not in l))
    ui.say(f"  The full log: {root / '.team' / 'logs' / 'build.md'}")
    ui.say("\nNext, in your own project:\n"
           "  agent-team init                 # a few questions, then your team file\n"
           "  agent-team mcp install          # use the team from Claude Code, Codex or Cursor\n"
           "  agent-team templates            # roles and skills for your language (with ECC's)")
    if keep or folder:
        ui.say(f"\nThe sample stays in {root}.")
    else:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if approved else 2
