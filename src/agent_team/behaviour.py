"""Behaviour checks: does the program still do what a user expects, after the team's change?

Tests check what their authors thought of. A behaviour check uses the program the way a user would,
once on the version the work started from and once with the team's changes, and compares what a
user would notice. Each scenario has a kind:

- terminal: a short script run in a terminal (with typed input, if the program asks for any). The
  final screen is compared line by line, then the exit code and the files it left.
- browser: the app is started (`serve`), a browser follows the steps (`click button "Start"`, ...),
  and the page as a user perceives it (its accessibility text) is compared, then the URL, console
  and page errors, and a screenshot.
- electron: a desktop app is started with Electron and the steps click through it (`click css
  "#save"`, ...). REA's Electron capture records the app's windows (title, page, visible), what it
  asked of the main process (IPC channels, not their values), the external effects it attempted
  (opening links, downloads; these are blocked) and errors, not the window's text or pixels, so
  that's what is compared.
- api: a .NET assembly is built (`prepare`) and its public API is compared: added, removed and
  changed types and members. Removing or changing a public member breaks callers.

The runs are captured by an MCP server (`[behaviour].server`, REA by default): its terminal capture,
its Playwright browser and Electron scenarios and its .NET metadata inspection. agent-team compares the results.
Every check's evidence is kept under .team/evidence/ (summary, screens, screenshots), the dashboard
shows it, the lead reviews with it, and the pull request lists the outcome.

The program runs with your user's permissions on this machine, as the tests do when [sandbox] is
off. With [sandbox] mode = "container", the scenario's prepare, run and serve commands run inside
the container instead (the browser and the inspection stay on this machine: they don't run the
team's code). Electron checks start the app on this machine, so they don't run in container mode.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import github, mcp, sandbox, ui
from .config import BehaviourScenario, Team

SCREEN_LINES = 40
VIEW_CHARS = 4000
KEEP_EVIDENCE = 30              # folders under .team/evidence kept; older ones are removed
PIXEL_NOTE = 0.001              # a changed-pixel ratio worth mentioning
PIXEL_CHANGE = 0.02             # ... and one that counts as looking different
BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge")
MAC_BROWSERS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
TOOLS = {"terminal": ["capture_process_scenario"], "browser": ["capture_browser_scenario", "compare_web_screenshots"],
         "electron": ["capture_electron_scenario"],
         "api": ["inspect_managed_members", "analyze_javascript_application"]}


@dataclass
class Observation:
    """One run of one scenario on one version, as a user (or a caller of the API) would see it."""
    view: str = ""              # the final screen, the page's text, or the public API (one member per line)
    exit: str = ""
    files: list[str] = field(default_factory=list)      # "created tally.json", ...
    contents: dict = field(default_factory=dict)        # path -> sha256 after the run (None: unknown)
    errors: list[str] = field(default_factory=list)     # console and page errors (browser)
    url: str = ""
    screenshot: str = ""        # file name of the saved PNG, in the evidence folder
    problem: str = ""
    evidence: dict | None = field(default=None, repr=False)
    png: dict | None = field(default=None, repr=False)  # REA's screenshot artifact, for the comparison


@dataclass
class Outcome:
    name: str
    status: str                 # same | changed | failed
    base: Observation
    work: Observation
    first_difference: str = ""
    kind: str = "terminal"
    notes: list[str] = field(default_factory=list)
    breaking: list[str] = field(default_factory=list)   # api: public members removed or changed
    added: list[str] = field(default_factory=list)      # api: public members added


# ---------------------------------------------------------------------------------------------
# Running commands for a scenario: here, or in the sandbox's container

def _env(project: Path) -> dict:
    return {**{k: os.environ[k] for k in mcp.BASE_ENV if k in os.environ}, "PROJECT": str(project)}


def _boxed(team: Team) -> bool:
    return team.sandbox.mode == "container"


def prepare(team: Team, sc: BehaviourScenario, project: Path, timeout: int = 900) -> str:
    """Run the scenario's prepare step in that version of the project; "" when it worked."""
    if not sc.prepare.strip():
        return ""
    try:
        if _boxed(team):
            argv = sandbox.container(team, f"agent-team-{uuid.uuid4().hex[:10]}", {str(project): "/project"},
                                     "/project", {"PROJECT": "/project"}) + ["sh", "-c", sc.prepare]
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        else:
            r = subprocess.run(["/bin/sh", "-c", sc.prepare], cwd=project, env=_env(project), capture_output=True,
                               text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"prepare took longer than {timeout} s"
    except (OSError, sandbox.SandboxError) as e:
        return f"prepare couldn't start: {e}"
    return "" if r.returncode == 0 else f"prepare failed (exit {r.returncode}): {(r.stdout + r.stderr)[-1500:]}"


# ---------------------------------------------------------------------------------------------
# terminal

def scenario_input(sc: BehaviourScenario, project: Path, folder: Path, team: Team | None = None) -> dict:
    """The capture request for one terminal run of a scenario against one version of the project."""
    events, at = [], int(sc.input_delay * 1000)
    for line in sc.input:
        events.append({"type": "input", "at_ms": at, "data": line + "\r"})
        at += int(sc.input_every * 1000)
    script = f'PROJECT="$1"; export PROJECT; {sc.run}'
    if team is not None and _boxed(team):
        argv = sandbox.container(team, f"agent-team-{uuid.uuid4().hex[:10]}",
                                 {str(project): "/project", str(folder): "/work"}, "/work", {"PROJECT": "/project"},
                                 tty=True) + ["sh", "-c", script, "agent-team", "/project"]
        executable, arguments = shutil.which(argv[0]) or argv[0], argv[1:]
    else:
        executable, arguments = "/bin/sh", ["-c", script, "agent-team", str(project)]
    return {
        "executable": executable,
        "arguments": arguments,
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
    return "\n".join(lines[-SCREEN_LINES:])[-VIEW_CHARS:]


def _terminal(evidence: dict) -> Observation:
    r = evidence.get("normalized_result") or {}
    ex = r.get("exit") or {}
    exit_text = (f"exit code {ex.get('code')}" if ex.get("reason") == "exited" else
                 f"{ex.get('reason', 'unknown')}" + (f" (signal {ex['signal']})" if ex.get("signal") else ""))
    effects = [e for e in r.get("filesystem_effects") or []
               if str(e.get("path", "")).split(":", 1)[-1] not in (".", "")]
    files = [f"{e.get('status')} {str(e.get('path', '')).split(':', 1)[-1]}"
             for e in effects if e.get("status") not in ("unchanged", None)]
    contents = {str(e.get("path", "")).split(":", 1)[-1]: ((e.get("after") or {}).get("sha256")) for e in effects}
    return Observation(view=_screen(r), exit=exit_text, files=files, contents=contents, evidence=evidence)


def run_terminal(team: Team, client: mcp.Client, sc: BehaviourScenario, project: Path, folder: Path) -> Observation:
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    problem = prepare(team, sc, project)
    if problem:
        return Observation(problem=problem)
    try:
        result = client.call("capture_process_scenario", scenario_input(sc, project, folder, team), timeout=sc.timeout + 60)
    except (mcp.McpError, sandbox.SandboxError) as e:
        return Observation(problem=str(e))
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return Observation(problem=mcp.text_of(result)[:1500])
    return _terminal(evidence)


# ---------------------------------------------------------------------------------------------
# browser

def browser_path(team: Team) -> str:
    if team.behaviour.browser:
        return team.behaviour.browser
    found = next((shutil.which(b) for b in BROWSERS if shutil.which(b)), None)
    return found or next((p for p in MAC_BROWSERS if Path(p).exists()), "")


def _port(url: str) -> int:
    parts = urllib.parse.urlsplit(url)
    return parts.port or (443 if parts.scheme == "https" else 80)


def _wait_for(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except urllib.error.HTTPError:
            return True     # it answers, even if not with 200
        except Exception:
            time.sleep(0.5)
    return False


class Server:
    """The app, started for one browser run and stopped after it."""

    def __init__(self, team: Team, sc: BehaviourScenario, project: Path):
        self.team, self.name, self.proc = team, f"agent-team-{uuid.uuid4().hex[:10]}", None
        if not sc.serve.strip():
            return
        if _boxed(team):
            argv = sandbox.container(team, self.name, {str(project): "/project"}, "/project", {"PROJECT": "/project"},
                                     ports=[_port(sc.url)]) + ["sh", "-c", sc.serve]
            self.proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.proc = subprocess.Popen(["/bin/sh", "-c", sc.serve], cwd=project, env=_env(project),
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def stop(self) -> None:
        if not self.proc or self.proc.poll() is not None:
            return
        if _boxed(self.team):
            subprocess.run([sandbox.engine(self.team) or "docker", "kill", self.name], capture_output=True)
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if not _boxed(self.team):
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()


def browser_input(team: Team, sc: BehaviourScenario) -> dict:
    from .steps import parse_steps
    actions = parse_steps(sc.steps)
    for a in actions:   # relative goto paths are on the app's own address
        if a["action"] == "goto":
            a["destination"]["url"] = urllib.parse.urljoin(sc.url, a["destination"]["url"])
        if a["action"] != "wait_for_timeout":   # without one, REA waits forever for a missing element
            a["timeout_ms"] = min(sc.step_timeout, sc.timeout) * 1000
    return {"browser": {"mode": "launch", "executable_path": browser_path(team), "headless": True},
            "start_url": {"url": sc.url}, "actions": actions,
            "capture": {"at_end": ["screenshot", "accessibility", "url"], "events": ["console", "page-errors"]}}


def _captured(evidence: dict, key: str):
    """One artifact REA captured at the end of a browser scenario, if it was."""
    steps = (evidence.get("normalized_result") or {}).get("steps") or []
    a = ((steps[-1].get("artifacts") or {}) if steps else {}).get(key) or {}
    return a.get("value") if a.get("state") == "captured" else None


def page_text(evidence: dict) -> str:
    """The whole page as a user (or a screen reader) perceives it, at the end of a browser scenario."""
    return (_captured(evidence, "accessibility") or {}).get("text", "")


def _browser(evidence: dict, lines: list[str] | None = None) -> Observation:
    """What the user saw; `lines` are the scenario's steps, to name the one that failed."""
    r = evidence.get("normalized_result") or {}
    steps = r.get("steps") or []
    failed = next((s for s in steps if s.get("status") not in ("completed", None)), None)

    def value(k):
        return _captured(evidence, k)

    page = page_text(evidence)
    errors = [f"{e.get('kind')}: {e.get('text', '')[:200]}" for e in (r.get("events") or {}).get("items") or []
              if e.get("kind") == "page-error" or (e.get("kind") == "console" and e.get("level") == "error")]
    ended = "all steps completed"
    if failed:
        sid = str(failed.get("step_id"))
        n = sid.removeprefix("step-")
        line = lines[int(n) - 1] if lines and n.isdigit() and 0 < int(n) <= len(lines) else ""
        ended = f"step {sid}{f' ({line})' if line else ''} {failed.get('status')}: {failed.get('error')}"
        if not page:   # REA stops at a failed step and captures nothing after it
            page = f"stopped at {ended} (no page captured after it)"
    return Observation(view=page[-VIEW_CHARS:], url=(value("url") or {}).get("url", ""), errors=errors,
                       exit=ended, evidence=evidence, png=value("screenshot"))


def run_browser(team: Team, client: mcp.Client, sc: BehaviourScenario, project: Path) -> Observation:
    if not browser_path(team):
        return Observation(problem="no Chrome or Chromium found; set [behaviour].browser to its path")
    problem = prepare(team, sc, project)
    if problem:
        return Observation(problem=problem)
    try:
        server = Server(team, sc, project)
    except (OSError, sandbox.SandboxError) as e:
        return Observation(problem=f"serve couldn't start: {e}")
    try:
        if not _wait_for(sc.url, min(sc.timeout, 120)):
            return Observation(problem=f"nothing answered at {sc.url} after serve started")
        result = client.call("capture_browser_scenario", browser_input(team, sc), timeout=sc.timeout + 60)
    except mcp.McpError as e:
        return Observation(problem=str(e))
    finally:
        server.stop()
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return Observation(problem=mcp.text_of(result)[:1500])
    return _browser(evidence, sc.steps)


# ---------------------------------------------------------------------------------------------
# electron

def electron_path(sc: BehaviourScenario, project: Path) -> Path | None:
    """The Electron executable: the scenario's, or the one npm installed in the project."""
    if sc.electron:
        p = Path(sc.electron).expanduser()
        return p if p.is_absolute() else project / p
    package = project / "node_modules" / "electron"
    try:   # the electron package names its binary, relative to dist/, in path.txt
        return package / "dist" / (package / "path.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def electron_input(sc: BehaviourScenario, project: Path, executable: Path) -> dict:
    from .steps import parse_electron_steps
    return {"executable_path": str(executable), "application_path": str(project / (sc.app or ".")),
            "args": list(sc.electron_args), "actions": parse_electron_steps(sc.steps)}


def _electron(evidence: dict, project: Path) -> Observation:
    """What a user of the app would notice, from REA's Electron capture: its windows, the external
    effects it attempted, what it asked of the main process, the steps and the errors."""
    r = evidence.get("normalized_result") or {}
    roots = sorted({f"file://{project}/", f"file://{Path(project).resolve()}/"}, key=len, reverse=True)

    def where(url) -> str:   # the project's own pages, without the folder this version is in
        url = str(url or "")
        return next((url[len(x):] for x in roots if url.startswith(x)), url)

    lines = []
    for w in r.get("windows") or []:
        state = ("" if w.get("visible") else " (hidden)") + (" (closed)" if w.get("destroyed") else "")
        lines.append(f"window {json.dumps(w.get('title') or '', ensure_ascii=False)} {where(w.get('url'))}{state}")
    events = (r.get("timeline") or {}).get("events") or []
    blocked: dict[str, int] = {}
    for e in events:
        if e.get("phase") == "blocked":
            key = f"blocked: {e.get('kind')} {e.get('event') or ''}".rstrip()
            blocked[key] = blocked.get(key, 0) + 1
    lines += [k + (f" (x{n})" if n > 1 else "") for k, n in sorted(blocked.items())]
    ipc = set()
    for e in (r.get("ipc") or {}).get("events") or []:
        if e.get("channel"):
            ipc.add(f"ipc {e['channel']}({', '.join(e.get('argument_shapes') or [])})"
                    + (f" -> {e['result_shape']}" if e.get("result_shape") else "") + (" failed" if e.get("error") else ""))
    lines += sorted(ipc)
    errors: dict[str, int] = {}
    for e in events:
        if e.get("kind") == "error":
            errors[str(e.get("event"))] = errors.get(str(e.get("event")), 0) + 1
    actions = r.get("actions") or []
    failed = next((a for a in actions if a.get("status") != "completed"), None)
    windows = r.get("windows") or []
    return Observation(view="\n".join(lines)[-VIEW_CHARS:], url=where(windows[0].get("url")) if windows else "",
                       errors=[f"{k}: {n}" for k, n in sorted(errors.items())],
                       exit=(f"step {failed.get('step_id')} {failed.get('status')}: {failed.get('error')}"
                             if failed else "all steps completed"), evidence=evidence)


def run_electron(team: Team, sc: BehaviourScenario, project: Path, log: Path | None = None) -> Observation:
    if _boxed(team):   # REA starts the app here, outside the container
        return Observation(problem="electron checks start the app on this machine, so they don't run with "
                                   "[sandbox] mode = \"container\"")
    problem = prepare(team, sc, project)
    if problem:
        return Observation(problem=problem)
    executable = electron_path(sc, project)
    if not executable or not executable.exists():
        return Observation(problem=f"no Electron executable at {executable or 'node_modules/electron'} (install "
                                   f"electron in prepare, e.g. npm ci, or set electron)")
    if not (project / (sc.app or ".")).exists():
        return Observation(problem=f"{sc.app} wasn't found in the project")
    # Its own server: a click on something that never appears waits until the timeout, and closing
    # the server is what stops that run (and the app).
    try:
        with mcp.Client(team.mcp[team.behaviour.server], team.root, log) as client:
            result = client.call("capture_electron_scenario", electron_input(sc, project, executable),
                                 timeout=sc.timeout + 60)
    except mcp.McpError as e:
        hint = " (a click on something that never appears waits until the timeout)" if "took longer" in str(e) else ""
        return Observation(problem=f"{e}{hint}")
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return Observation(problem=mcp.text_of(result)[:1500])
    return _electron(evidence, project)


# ---------------------------------------------------------------------------------------------
# api (.NET)

def _clean_type(t) -> str:
    return re.sub(r"(class|valuetype):\d+", r"\1", str(t or "?"))   # numbered references differ between builds


def public_api(evidence: dict) -> list[str]:
    """The public surface of a .NET assembly, one member per line: types, methods and fields other
    code can use (public or protected, not compiler-generated)."""
    r = evidence.get("normalized_result") or {}
    public_types = {t["full_name"] for t in r.get("types") or []
                    if (t.get("flags", 0) & 7) in (1, 2) and "<" not in t.get("full_name", "")}
    out = [f"type {t}" for t in public_types]
    for m in r.get("methods") or []:
        if m.get("declaring_type") in public_types and (m.get("flags", 0) & 7) in (4, 5, 6) and "<" not in m.get("name", ""):
            sig = m.get("signature") or {}
            params = ", ".join(_clean_type(p) for p in sig.get("parameter_types") or [])
            out.append(f"method {m['declaring_type']}.{m['name']}({params}): {_clean_type(sig.get('return_type'))}")
    for f in r.get("fields") or []:
        if f.get("declaring_type") in public_types and (f.get("flags", 0) & 7) in (4, 5, 6) and "<" not in f.get("name", ""):
            sig = f.get("signature") or {}
            out.append(f"field {f['declaring_type']}.{f['name']}: {_clean_type(sig.get('field_type'))}")
    return sorted(out)


def _entry_modules(package: Path) -> set[str]:
    """A JavaScript package's public modules, from package.json (exports, main, module), relative
    to the package; empty when it names none (then every module's exports count)."""
    try:
        meta = json.loads((package / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and v.startswith("./"):
            found.add(v[2:])
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(meta.get("exports"))
    for key in ("main", "module"):
        if isinstance(meta.get(key), str):
            found.add(meta[key].removeprefix("./"))
    return found


def js_exports(evidence: dict, entries: set[str]) -> list[str]:
    """The exported names of a JavaScript package's public modules, one per line."""
    out: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            props = v.get("properties")
            if isinstance(props, dict) and props.get("semantic_role") == "export-binding" and props.get("exported_name"):
                module = str(props.get("module_path", ""))
                if not entries or module in entries:
                    out.add(f"export {module}: {props['exported_name']}")
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(evidence.get("normalized_result") or {})
    return sorted(out)


def run_api(team: Team, client: mcp.Client, sc: BehaviourScenario, project: Path) -> Observation:
    problem = prepare(team, sc, project)
    if problem:
        return Observation(problem=problem)
    path = project / (sc.assembly or sc.package)
    if not path.exists():
        return Observation(problem=f"{sc.assembly or sc.package} wasn't found (check prepare)")
    tool, args = (("inspect_managed_members", {"path": str(path)}) if sc.assembly else
                  ("analyze_javascript_application", {"input_path": str(path)}))
    try:
        result = client.call(tool, args, timeout=sc.timeout + 60)
    except mcp.McpError as e:
        return Observation(problem=str(e))
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return Observation(problem=mcp.text_of(result)[:1500])
    members = public_api(evidence) if sc.assembly else js_exports(evidence, _entry_modules(path))
    return Observation(view="\n".join(members), exit="inspected", evidence=evidence)


# ---------------------------------------------------------------------------------------------
# Comparing two runs

def _first_line_difference(a: str, b: str, what: str) -> str:
    x, y = a.splitlines(), b.splitlines()
    i = next((i for i, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))

    def line(lines):   # as people read it: trimmed, in curly quotes (no escaped ones)
        return f"“{lines[i].strip().removeprefix('- ')}”" if i < len(lines) else "(nothing)"

    return f"{what} line {i + 1}: before {line(x)}, now {line(y)}"


def api_changes(before: Observation, after: Observation) -> tuple[list[str], list[str]]:
    """(removed or changed members, added members) between two public APIs."""
    a, b = set(before.view.splitlines()), set(after.view.splitlines())
    return sorted(a - b), sorted(b - a)


def compare(before: Observation, after: Observation, kind: str = "terminal") -> tuple[str, str]:
    """("same" or "changed", the first difference in words): what a user would notice."""
    if kind == "api":
        removed, added = api_changes(before, after)
        parts = ([f"removed or changed: {', '.join(removed[:5])}"] if removed else []) + \
                ([f"added: {', '.join(added[:5])}"] if added else [])
        return ("changed", "; ".join(parts)) if parts else ("same", "")
    what = {"browser": "page text", "electron": "app"}.get(kind, "screen")
    if before.view != after.view:
        return "changed", _first_line_difference(before.view, after.view, what)
    if before.exit != after.exit:
        return "changed", f"before {before.exit}, now {after.exit}"
    if before.url != after.url:
        return "changed", f"the {'window' if kind == 'electron' else 'page'} ended at {after.url} instead of {before.url}"
    new_errors = [e for e in after.errors if e not in before.errors]
    if new_errors:
        return "changed", f"new error: {new_errors[0]}"
    if before.files != after.files:
        return "changed", f"files before: {', '.join(before.files) or 'none'}; now: {', '.join(after.files) or 'none'}"
    differ = sorted(p for p in set(before.contents) & set(after.contents)
                    if before.contents[p] and after.contents[p] and before.contents[p] != after.contents[p])
    if differ:   # files that store times or ids differ on every run, so this alone isn't a change
        return "same", f"the content of {', '.join(differ)} differs (normal if it stores times or ids)"
    return "same", ""


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            hit = _find(v, key)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find(v, key)
            if hit is not None:
                return hit
    return None


def _pixels(client: mcp.Client, before: Observation, after: Observation) -> float | None:
    """The share of pixels that differ between the two screenshots, if both were taken."""
    if not before.png or not after.png:
        return None
    if before.png.get("sha256") == after.png.get("sha256"):
        return 0.0
    try:
        result = client.call("compare_web_screenshots", {"before": before.png, "after": after.png})
    except mcp.McpError:
        return None
    r = result.get("structuredContent") or {}
    for key in ("changed_pixel_ratio", "changed_ratio", "pixel_change_ratio", "difference_ratio"):
        found = _find(r, key)
        if isinstance(found, (int, float)):
            return float(found)
    return None


# ---------------------------------------------------------------------------------------------
# The whole check

def run(team: Team, base: str | None, target: str | None = None, label: str = "check",
        only: list[str] | None = None) -> list[Outcome]:
    """Run every scenario on `base` (a commit) and on `target` (another commit, or the working tree
    when None), compare them, and keep the evidence."""
    scenarios = [s for s in team.behaviour.scenarios if not only or s.name in only]
    if not scenarios or not base:
        return []
    if team.behaviour.server not in team.mcp:
        ui.warn(f"behaviour checks need [mcp.{team.behaviour.server}] (agent-team rea setup)")
        return []
    if _boxed(team):   # never fall back to running the team's code outside the sandbox
        ok, detail = sandbox.ready(team)
        if not ok:
            ui.warn(f"behaviour checks didn't run: the sandbox isn't ready ({detail})")
            return []
    tmp = Path(tempfile.mkdtemp(prefix="agent-team-behaviour-"))
    base_dir, target_dir, folder = tmp / "base", tmp / "target", tmp / "run"
    outcomes: list[Outcome] = []
    log = team.root / ".team" / "logs"
    log.mkdir(parents=True, exist_ok=True)
    try:
        github.git(team.root, "worktree", "add", "--detach", str(base_dir), base)
        now = team.root.resolve()   # absolute: the runs happen in other folders
        if target:
            github.git(team.root, "worktree", "add", "--detach", str(target_dir), target)
            now = target_dir
        with mcp.Client(team.mcp[team.behaviour.server], team.root, log / f"mcp-{team.behaviour.server}.log") as client:
            for sc in scenarios:
                ui.action(f"behaviour check: {sc.name} ({sc.kind})")
                runs = []
                for project in (base_dir, now):
                    if sc.kind == "browser":
                        runs.append(run_browser(team, client, sc, project))
                    elif sc.kind == "electron":
                        runs.append(run_electron(team, sc, project, log / f"mcp-{team.behaviour.server}.log"))
                    elif sc.kind == "api":
                        runs.append(run_api(team, client, sc, project))
                    else:
                        runs.append(run_terminal(team, client, sc, project, folder))
                before, after = runs
                if before.problem or after.problem:
                    outcomes.append(Outcome(sc.name, "failed", before, after, "", sc.kind))
                    continue
                status, first = compare(before, after, sc.kind)
                outcome = Outcome(sc.name, status, before, after, first if status == "changed" else "", sc.kind,
                                  [first] if status == "same" and first else [])
                if sc.kind == "api":
                    outcome.breaking, outcome.added = api_changes(before, after)
                if sc.kind == "browser":
                    ratio = _pixels(client, before, after)
                    if ratio is not None and ratio >= PIXEL_NOTE:
                        outcome.notes.append(f"{ratio:.1%} of the screenshot's pixels changed")
                        if outcome.status == "same" and ratio >= PIXEL_CHANGE:
                            outcome.status = "changed"
                            outcome.first_difference = f"it looks different: {ratio:.1%} of pixels changed"
                outcomes.append(outcome)
    except (mcp.McpError, github.GitHubError) as e:
        ui.warn(f"behaviour checks didn't run: {e}")
    finally:
        for d in (base_dir, target_dir):
            if d.exists():
                github.git(team.root, "worktree", "remove", "--force", str(d), check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    if outcomes:
        save(team, outcomes, label, base, target)
    return outcomes


# ---------------------------------------------------------------------------------------------
# Evidence: kept under .team/evidence/<time>-<label>/ for the dashboard and later reading

def evidence_root(team: Team) -> Path:
    return team.root / ".team" / "evidence"


def save(team: Team, outcomes: list[Outcome], label: str, base: str, target: str | None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]
    folder = evidence_root(team) / f"{stamp}-{re.sub(r'[^A-Za-z0-9_-]+', '-', label)[:40]}"
    folder.mkdir(parents=True, exist_ok=True)
    items = []
    for n, o in enumerate(outcomes, 1):
        item = {"name": o.name, "kind": o.kind, "status": o.status, "first_difference": o.first_difference,
                "notes": o.notes, "breaking": o.breaking, "added": o.added}
        for side, obs in (("base", o.base), ("work", o.work)):
            if obs.png and obs.png.get("data_base64"):
                obs.screenshot = f"{n}-{side}.png"
                (folder / obs.screenshot).write_bytes(base64.b64decode(obs.png["data_base64"]))
            if obs.evidence:
                (folder / f"{n}-{side}.json").write_text(json.dumps(obs.evidence), encoding="utf-8")
            item[side] = {k: v for k, v in asdict(obs).items() if k not in ("evidence", "png")}
        items.append(item)
    summary = {"label": label, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "base": base, "target": target or "working tree", "outcomes": items}
    (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (folder / "report.md").write_text(report(outcomes, for_pr=True) + "\n", encoding="utf-8")
    for old in sorted(p for p in evidence_root(team).iterdir() if p.is_dir())[:-KEEP_EVIDENCE]:
        shutil.rmtree(old, ignore_errors=True)
    return folder


def recent(team: Team, limit: int = 20) -> list[dict]:
    """The latest checks' summaries, newest first (for the dashboard)."""
    root = evidence_root(team)
    if not root.is_dir():
        return []
    out = []
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)[:limit]:
        try:
            out.append({"id": folder.name, **json.loads((folder / "summary.json").read_text(encoding="utf-8"))})
        except (OSError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------------------------
# The report: for the lead's review (with the screens) or a pull request (shorter)

WORDS = {"same": "behaves as before", "changed": "behaves differently", "failed": "couldn't run"}
API_WORDS = {"same": "public API unchanged", "changed": "public API changed", "failed": "couldn't be inspected"}


def report(outcomes: list[Outcome], for_pr: bool = False) -> str:
    if not outcomes:
        return ""
    out = ["# Behaviour checks", "",
           "Each scenario ran on the version this work started from (before) and with the changes (now)."
           + ("" if for_pr else " Differences may be intended (the task asked for them) or regressions: "
              "judge each against the task and say which.")]
    for o in outcomes:
        words = (API_WORDS if o.kind == "api" else WORDS).get(o.status, o.status)
        out += ["", f"## {o.name}: {words}"]
        for label, r in (("Before", o.base), ("Now", o.work)):
            if r.problem:
                out.append(f"- {label}: {r.problem}")
            elif o.kind != "api":
                extra = [f"files: {', '.join(r.files)}" if r.files else "",
                         f"errors: {'; '.join(r.errors[:3])}" if r.errors else "",
                         f"at {r.url}" if r.url and o.kind in ("browser", "electron") else ""]
                out.append(f"- {label}: {r.exit}" + "".join(f"; {x}" for x in extra if x))
        if o.kind == "api" and o.status == "changed":
            if o.breaking:
                out.append(f"- Removed or changed (breaks callers): {', '.join(o.breaking[:12])}")
            if o.added:
                out.append(f"- Added: {', '.join(o.added[:12])}")
        elif o.first_difference:
            out.append(f"- First difference: {o.first_difference}")
        out += [f"- Note: {n}" for n in o.notes]
        if not for_pr and o.kind != "api":
            what = {"browser": "Page", "electron": "App"}.get(o.kind, "Screen")
            for label, r in ((f"{what} before", o.base), (f"{what} now", o.work)):
                if r.view:
                    out += ["", f"{label}:", "```", r.view, "```"]
    text = "\n".join(out)
    # The screens and pages are output of code the team wrote: data, not instructions.
    return text if for_pr else github.untrusted(text)
