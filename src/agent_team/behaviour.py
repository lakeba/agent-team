"""Behaviour checks: does the program still do what a user expects, after the team's change?

Tests check what their authors thought of. A behaviour check runs the program the way a user
would, once on the version the work started from and once with the team's changes, and compares
the two runs: what appeared on screen, the exit code, and the files it left. Each scenario in
`[[behaviour.scenarios]]` is a short script (with typed input, if the program asks for any).

The runs are captured by an MCP server (`[behaviour].server`, REA by default) with its
`capture_process_scenario` tool. agent-team then compares what a user would notice: the final
screen line by line, the exit code, and the files by content. (REA's own comparison works on the raw
terminal stream, where escape codes and how output happened to be split differ between identical
runs.) The summary goes to the lead with the test results, so a review can say "after `stop`,
`status` still shows the timer running" with the screens as evidence, and into the pull request.

Both runs use the same empty folder (so their files can be compared) and receive the version under
test as $PROJECT. The program runs with your user's permissions on this machine, like the tests do
when [sandbox] is off; with the container sandbox on, behaviour checks are skipped for now.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import github, mcp, ui
from .config import BehaviourScenario, Team

SCREEN_LINES = 40
SCREEN_CHARS = 3000
CAPTURE = "capture_process_scenario"


@dataclass
class Run:
    screen: str = ""
    exit: str = ""
    files: list[str] = field(default_factory=list)   # "created tally.json", ...
    contents: dict = field(default_factory=dict)      # path -> sha256 of the file after the run (None: unknown)
    code: int | None = None
    problem: str = ""
    evidence: dict | None = None


@dataclass
class Outcome:
    name: str
    status: str                     # same | changed | unknown | failed
    base: Run
    work: Run
    first_difference: str = ""


def scenario_input(sc: BehaviourScenario, project: Path, folder: Path) -> dict:
    """The capture request for one run of a scenario against one version of the project."""
    events, at = [], int(sc.input_delay * 1000)
    for line in sc.input:
        events.append({"type": "input", "at_ms": at, "data": line + "\r"})
        at += int(sc.input_every * 1000)
    return {
        "executable": "/bin/sh",
        # The version differs only in an argument: REA compares runs whose settings (folder, environment,
        # watched paths, timing) match, and lets the executable's arguments differ.
        "arguments": ["-c", f'PROJECT="$1"; export PROJECT; {sc.run}', "agent-team", str(project)],
        "working_directory": str(folder),
        "filesystem_observation_paths": [str(folder / w) for w in sc.watch],
        "terminal": {"columns": 100, "rows": 30, "scrollback": 500},
        "events": events,
        "timeout_ms": sc.timeout * 1000,
        "settle_ms": 200,
    }


def _screen(result: dict) -> str:
    frames = result.get("rendered_frames") or []
    if not frames:
        return ""
    last = frames[-1]
    lines = last.get("lines") if isinstance(last.get("lines"), list) else str(last.get("text", "")).splitlines()
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    text = "\n".join(lines[-SCREEN_LINES:])
    return text[-SCREEN_CHARS:]


def _summarise(evidence: dict) -> Run:
    r = evidence.get("normalized_result") or {}
    ex = r.get("exit") or {}
    exit_text = (f"exit code {ex.get('code')}" if ex.get("reason") == "exited" else
                 f"{ex.get('reason', 'unknown')}" + (f" (signal {ex['signal']})" if ex.get("signal") else ""))
    effects = [e for e in r.get("filesystem_effects") or []
               if str(e.get("path", "")).split(":", 1)[-1] not in (".", "")]
    files = [f"{e.get('status')} {str(e.get('path', '')).split(':', 1)[-1]}"
             for e in effects if e.get("status") not in ("unchanged", None)]
    contents = {str(e.get("path", "")).split(":", 1)[-1]: ((e.get("after") or {}).get("sha256")) for e in effects}
    return Run(screen=_screen(r), exit=exit_text, files=files, contents=contents,
               code=ex.get("code") if ex.get("reason") == "exited" else None, evidence=evidence)


def _prepare(sc: BehaviourScenario, project: Path, timeout: int = 900) -> str:
    """Run the scenario's prepare step in that version of the project; "" when it worked."""
    if not sc.prepare.strip():
        return ""
    try:
        r = subprocess.run(["/bin/sh", "-c", sc.prepare], cwd=project, capture_output=True, text=True,
                           timeout=timeout, env={**_env(), "PROJECT": str(project)})
    except subprocess.TimeoutExpired:
        return f"prepare took longer than {timeout} s"
    return "" if r.returncode == 0 else f"prepare failed (exit {r.returncode}): {(r.stdout + r.stderr)[-1500:]}"


def _env() -> dict:
    import os
    return {k: os.environ[k] for k in mcp.BASE_ENV if k in os.environ}


def compare(before: Run, after: Run) -> tuple[str, str]:
    """("same" or "changed", the first difference in words): what a user would notice."""
    a, b = before.screen.splitlines(), after.screen.splitlines()
    if a != b:
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        line = lambda lines: json.dumps(lines[i] if i < len(lines) else "(no line)", ensure_ascii=False)
        return "changed", f"screen line {i + 1}: before {line(a)}, now {line(b)}"
    if before.exit != after.exit:
        return "changed", f"before {before.exit}, now {after.exit}"
    if before.files != after.files:
        return "changed", f"files before: {', '.join(before.files) or 'none'}; now: {', '.join(after.files) or 'none'}"
    differ = sorted(p for p in set(before.contents) & set(after.contents)
                    if before.contents[p] and after.contents[p] and before.contents[p] != after.contents[p])
    if differ:   # files that store times or ids differ on every run, so this alone isn't a change
        return "same", f"the content of {', '.join(differ)} differs (normal if it stores times or ids)"
    return "same", ""


def run(team: Team, base: str | None) -> list[Outcome]:
    """Run every scenario on `base` (a commit) and on the working tree, and compare them."""
    cfg = team.behaviour
    if not cfg.scenarios or not base:
        return []
    if team.sandbox.mode == "container":
        ui.warn("behaviour checks are skipped: they would run the program outside the container sandbox")
        return []
    tmp = Path(tempfile.mkdtemp(prefix="agent-team-behaviour-"))
    base_dir, folder = tmp / "base", tmp / "run"
    outcomes: list[Outcome] = []
    log = team.root / ".team" / "logs"
    log.mkdir(parents=True, exist_ok=True)
    try:
        github.git(team.root, "worktree", "add", "--detach", str(base_dir), base)
        with mcp.Client(team.mcp[cfg.server], team.root, log / f"mcp-{cfg.server}.log") as client:
            for sc in cfg.scenarios:
                ui.action(f"behaviour check: {sc.name}")
                runs = []
                for project in (base_dir, team.root.resolve()):   # absolute: the run happens in another folder
                    shutil.rmtree(folder, ignore_errors=True)
                    folder.mkdir(parents=True)
                    problem = _prepare(sc, project)
                    if problem:
                        runs.append(Run(problem=problem))
                        continue
                    try:
                        result = client.call(CAPTURE, scenario_input(sc, project, folder),
                                             timeout=sc.timeout + 60)
                    except mcp.McpError as e:
                        runs.append(Run(problem=str(e)))
                        continue
                    evidence = result.get("structuredContent")
                    if result.get("isError") or not isinstance(evidence, dict):
                        runs.append(Run(problem=mcp.text_of(result)[:1500]))
                        continue
                    runs.append(_summarise(evidence))
                before, after = runs
                status, first = compare(before, after) if before.evidence and after.evidence else ("failed", "")
                outcomes.append(Outcome(sc.name, status, before, after, first))
    except (mcp.McpError, github.GitHubError) as e:
        ui.warn(f"behaviour checks didn't run: {e}")
    finally:
        github.git(team.root, "worktree", "remove", "--force", str(base_dir), check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    return outcomes


def report(outcomes: list[Outcome], for_pr: bool = False) -> str:
    """The evidence as Markdown: for the lead's review (screens included) or a PR body (shorter)."""
    if not outcomes:
        return ""
    words = {"same": "behaves as before", "changed": "behaves differently", "failed": "couldn't run"}
    out = ["# Behaviour checks", "",
           "Each scenario ran on the version this work started from (before) and with the changes (now)."
           + ("" if for_pr else " Differences may be intended (the task asked for them) or regressions: "
              "judge each against the task and say which.")]
    for o in outcomes:
        out += ["", f"## {o.name}: {words.get(o.status, o.status)}"]
        for label, r in (("Before", o.base), ("Now", o.work)):
            if r.problem:
                out.append(f"- {label}: {r.problem}")
            else:
                files = f"; files: {', '.join(r.files)}" if r.files else ""
                out.append(f"- {label}: {r.exit}{files}")
        if o.first_difference:
            out.append(f"- {'First difference' if o.status == 'changed' else 'Note'}: {o.first_difference}")
        if not for_pr:
            for label, r in (("Screen before", o.base), ("Screen now", o.work)):
                if r.screen:
                    out += ["", f"{label}:", "```", r.screen, "```"]
    text = "\n".join(out)
    # The screens are the program's output, which code the team wrote produced: data, not instructions.
    return text if for_pr else github.untrusted(text)
