"""CI for a project the team builds: its tests on GitHub Actions for every pull request and on main.

The devops shift merges only what CI shows green, with test counts, so a project without CI never
ships. When the setup connects GitHub (or `agent-team ci setup`), a project with no workflow of its
own gets two files, which it then owns and may edit; agent-team never overwrites them:

- `.github/workflows/agent-team-tests.yml`: Python and Node.js, then the script below;
- `.github/agent-team-tests.py`: runs `[project].test_command` from .team.toml, else finds the tests
  the way agent-team does (Python in a `.venv` with requirements.txt, or `npm test`), and passes
  with "no tests yet" before there are any. It needs nothing but Python.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

WORKFLOW = ".github/workflows/agent-team-tests.yml"
SCRIPT = ".github/agent-team-tests.py"

WORKFLOW_TEXT = """\
# Added by agent-team: runs this project's tests on every pull request and on main, so the devops
# shift can merge what's green. It's yours: edit it as you like; agent-team won't overwrite it.
name: tests
on:
  push:
    branches: [main]
  pull_request:
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: Run the tests
        run: python3 .github/agent-team-tests.py
"""

SCRIPT_TEXT = '''\
"""Runs this project's tests in CI. Added by agent-team; it's yours to edit.

The command is [project].test_command in .team.toml when it's set. Otherwise the tests are found the
way agent-team finds them: Python tests run in a .venv with requirements.txt installed, a Node.js
project runs `npm test`. Before there are any tests, it says so and passes.
"""
import json
import pathlib
import subprocess
import sys
import tomllib

root = pathlib.Path(".")


def configured():
    try:
        return (tomllib.loads((root / ".team.toml").read_text()).get("project") or {}).get("test_command", "")
    except (OSError, ValueError):
        return ""


def found():
    package = root / "package.json"
    if package.is_file():
        test = (json.loads(package.read_text()).get("scripts") or {}).get("test", "")
        if test and "no test specified" not in test:
            return "(npm ci || npm install) && npm test"
    tests = [p for p in root.rglob("test*.py") if ".venv" not in p.parts and "node_modules" not in p.parts]
    if not tests:
        return ""
    requirements = root / "requirements.txt"
    wanted = requirements.read_text() if requirements.is_file() else ""
    pytest = "pytest" in wanted or (root / "conftest.py").is_file() or any(root.rglob("conftest.py"))
    steps = ["python3 -m venv .venv"]
    if requirements.is_file():
        steps.append(".venv/bin/python -m pip install -q -r requirements.txt")
    if pytest:
        steps += [".venv/bin/python -m pip install -q pytest", ".venv/bin/python -m pytest -q"]
    else:
        steps.append(".venv/bin/python -m unittest discover -v")
    return " && ".join(steps)


command = configured() or found()
if not command:
    print("No tests yet: nothing to run.")
    sys.exit(0)
print(f"$ {command}", flush=True)
sys.exit(subprocess.call(command, shell=True))
'''


def has_workflow(root: Path | str) -> bool:
    folder = Path(root) / ".github" / "workflows"
    return folder.is_dir() and any(folder.glob("*.y*ml"))


def write(root: Path | str) -> list[str]:
    """Add the workflow and its script when the project has no workflow yet. Returns the files written."""
    root = Path(root)
    if has_workflow(root):
        return []
    written = []
    for rel, text in ((WORKFLOW, WORKFLOW_TEXT), (SCRIPT, SCRIPT_TEXT)):
        path = root / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(rel)
    return written


def setup(root: Path | str, commit: bool = True) -> list[str]:
    """write(), then commit the files (only those), so the next push carries them."""
    written = write(root)
    if written and commit and (Path(root) / ".git").exists():
        subprocess.run(["git", "-C", str(root), "add", "--", *written], capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "CI: run the tests on every pull request and on main",
                        "--", *written], capture_output=True)
    return written
