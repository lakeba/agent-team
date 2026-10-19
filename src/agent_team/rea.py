"""REA (https://rea.tools), set up for the team without any hand configuration.

REA is the tool server behind behaviour checks: it captures terminal runs, drives a browser through
a web app, and inspects .NET assemblies. This module finds it (on the PATH, in agent-team's own
copy, or registered with Claude Code by `rea-agents setup`), installs a pinned version when asked,
and writes the `[mcp.rea]` and `[behaviour]` sections a project needs.

agent-team installs REA into its own folder (no sudo, no global packages), at a version its checks
were tried with. A REA you installed yourself is used as it is.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import ui
from .config import CONFIG_NAME

PACKAGE = "rea-agents"
VERSION = "6.5.0"           # the version agent-team's behaviour checks were tried with


def home() -> Path:
    """agent-team's own REA install."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "agent-team" / "rea"


def own_command() -> Path:
    return home() / "node_modules" / ".bin" / "rea"


def claude_registration() -> dict | None:
    """REA's registration in Claude Code (`rea-agents setup` writes mcpServers.rea), if any."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    path = Path(config_dir) / ".claude.json" if config_dir else Path.home() / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = (data.get("mcpServers") or {}).get("rea")
    return entry if isinstance(entry, dict) and entry.get("command") else None


def node_file() -> Path:
    return home() / "node.json"


def _node_version(node: str) -> tuple[int, int] | None:
    try:
        r = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.match(r"v(\d+)\.(\d+)", r.stdout.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def supported(v: tuple[int, int] | None) -> bool:
    return bool(v) and ((v[0] == 22 and v[1] >= 19) or (v[0] == 24 and v[1] >= 11) or v[0] >= 26)


def pin_node(node: str | None = None) -> str:
    """Remember the Node.js agent-team's REA copy was installed with, so it keeps running with it when
    the PATH's node changes (nvm, Homebrew). Returns the pinned node, or "" if it isn't supported."""
    node = node or shutil.which("node") or ""
    if not node:
        return ""
    node = os.path.realpath(node)
    v = _node_version(node)
    if not supported(v):
        return ""
    node_file().write_text(json.dumps({"node": node, "version": "%d.%d" % v}) + "\n", encoding="utf-8")
    return node


def pinned_node() -> str:
    """The Node.js REA was installed with, if it's still there and still supported."""
    try:
        node = json.loads(node_file().read_text(encoding="utf-8")).get("node", "")
    except (OSError, ValueError):
        return ""
    return node if node and os.access(node, os.X_OK) and supported(_node_version(node)) else ""


def find() -> tuple[str, list[str], str]:
    """(command, args, where it came from) for a usable REA, or ("", [], "") if there's none.
    agent-team's own copy runs with the Node.js it was installed with, while that one is there."""
    if own_command().exists():
        node = pinned_node()
        if node:
            return node, [os.path.realpath(own_command()), "--mcp"], "agent-team's copy"
        return str(own_command()), ["--mcp"], "agent-team's copy"
    on_path = shutil.which("rea")
    if on_path:
        return on_path, ["--mcp"], "on the PATH"
    reg = claude_registration()
    if reg:
        command = reg["command"]
        if shutil.which(command) or Path(command).exists():
            return command, [str(a) for a in reg.get("args") or []], "registered with Claude Code"
    return "", [], ""


def _argv(command: str, args=()) -> list[str]:
    """REA's command line without --mcp, for --version and doctor."""
    return [command, *(str(a) for a in args if a != "--mcp")]


def version(command: str, args=()) -> str:
    try:
        r = subprocess.run([*_argv(command, args), "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"(\d+\.\d+\.\d+)", r.stdout + r.stderr)
    return m.group(1) if m else ""


def node_ok() -> tuple[bool, str]:
    node = shutil.which("node")
    if not node or not shutil.which("npm"):
        return False, "Node.js and npm aren't installed (REA needs Node.js 22.19+, 24.11+ or 26+)"
    r = subprocess.run([node, "--version"], capture_output=True, text=True)
    m = re.match(r"v(\d+)\.(\d+)", r.stdout.strip())
    if not m:
        return False, f"couldn't read the Node.js version ({r.stdout.strip()})"
    major, minor = int(m.group(1)), int(m.group(2))
    ok = (major == 22 and minor >= 19) or (major == 24 and minor >= 11) or major >= 26
    return ok, f"Node.js {r.stdout.strip()}" + ("" if ok else " is too old: REA needs 22.19+, 24.11+ or 26+")


def install(yes: bool = False) -> str:
    """Install the pinned REA into agent-team's folder; returns its command. Asks first unless yes."""
    ok, detail = node_ok()
    if not ok:
        raise SystemExit(f"Can't install REA: {detail}. See https://rea.tools/get-started/")
    target = home()
    if not yes:
        import sys
        if not sys.stdin.isatty():
            raise SystemExit(f"Installing REA {VERSION} needs your OK: run agent-team rea setup --yes")
        answer = input(f"Install REA {VERSION} ({PACKAGE} from npm) into {target}? [Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            raise SystemExit("Nothing was installed.")
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "package.json").exists():
        (target / "package.json").write_text('{"name": "agent-team-rea", "private": true}\n', encoding="utf-8")
    ui.action(f"installing {PACKAGE}@{VERSION} into {target} (a minute or two)")
    r = subprocess.run(["npm", "install", "--no-fund", "--no-audit", f"{PACKAGE}@{VERSION}"], cwd=target,
                       capture_output=True, text=True)
    if r.returncode != 0 or not own_command().exists():
        raise SystemExit(f"npm couldn't install REA:\n{(r.stdout + r.stderr)[-2000:]}")
    pin_node()
    return str(own_command())


SECTION = '''
# REA (https://rea.tools) captures behaviour checks: terminal runs, browser journeys, .NET APIs.
# Added by agent-team. Members listed with mcp = ["rea"] may also call the tools below.
[mcp.rea]
command = "{command}"
args = {args}
tools = ["capture_process_scenario"]

[behaviour]
server = "rea"
'''


def _ours(command: str, args: list) -> bool:
    """Whether an [mcp.rea] entry runs agent-team's own REA copy (its shim, or a node with its script)."""
    own = {str(own_command()), os.path.realpath(own_command())}
    return command in own or any(str(a) in own for a in args)


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def configure(root: Path, command: str, args: list[str]) -> bool:
    """Add [mcp.rea] and [behaviour] to the project's team file if they're missing (text appended,
    so comments stay). An [mcp.rea] that runs agent-team's own copy is brought up to date (it runs
    with the Node.js REA was installed with). Returns whether anything changed."""
    import tomllib
    path = Path(root) / CONFIG_NAME
    text = path.read_text(encoding="utf-8")
    if re.search(r"^\s*\[mcp\.rea\]", text, re.M):
        try:
            entry = (tomllib.loads(text).get("mcp") or {}).get("rea") or {}
        except tomllib.TOMLDecodeError:
            return False
        old = (entry.get("command", ""), list(entry.get("args") or []))
        if not _ours(*old) or old == (command, args):
            return False
        head = re.search(r"^\s*\[mcp\.rea\][^\n]*\n", text, re.M)
        nxt = re.search(r"^\s*\[", text[head.end():], re.M)
        end = head.end() + (nxt.start() if nxt else len(text) - head.end())
        body = re.sub(r"^command\s*=.*$", lambda _: f"command = {_toml_str(command)}", text[head.end():end], count=1, flags=re.M)
        body = re.sub(r"^args\s*=.*$", lambda _: f"args = {json.dumps(args)}", body, count=1, flags=re.M)
        path.write_text(text[:head.end()] + body + text[end:], encoding="utf-8")
        return True
    block = SECTION.format(command=_toml_str(command)[1:-1], args=json.dumps(args))
    if re.search(r"^\s*\[behaviour\]", text, re.M):
        block = block.split("\n[behaviour]")[0] + "\n"
    path.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
    return True


def doctor(command: str, args=()) -> tuple[bool, str]:
    """What REA's own doctor says about what behaviour checks need (Node and the host). The deep
    native-analysis engines (Hopper, Ghidra, IDA, JADX) aren't needed and aren't reported."""
    try:
        r = subprocess.run([*_argv(command, args), "doctor", "--format", "json"], capture_output=True, text=True, timeout=120)
        data = json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False, "rea doctor didn't answer"
    checks = {c.get("name"): c for c in data.get("scope_checks") or []}
    needed = [checks[n] for n in ("node", "host") if n in checks]
    bad = [c for c in needed if not c.get("ok")]
    if bad:
        return False, "; ".join(f"{c['name']}: {c.get('detail') or c.get('remediation', '')}" for c in bad)
    return True, ", ".join(f"{c['name']} {c.get('detail', 'ok')}" for c in needed)


def status(root: Path | None = None) -> dict:
    command, args, where = find()
    out = {"command": command, "args": args, "where": where, "version": version(command, args) if command else "",
           "pinned": VERSION, "claude_code": bool(claude_registration()), "configured": False}
    if root and (Path(root) / CONFIG_NAME).exists():
        out["configured"] = bool(re.search(r"^\s*\[mcp\.rea\]", (Path(root) / CONFIG_NAME).read_text(encoding="utf-8"), re.M))
    return out
