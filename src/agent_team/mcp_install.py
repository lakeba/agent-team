"""Registering agent-team's MCP server with coding agents (Claude Code, Codex, Cursor, others)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import ui

CLIENTS = ("claude", "codex", "cursor")


def launch() -> tuple[str, list[str]]:
    """How a coding agent starts the server: this install's agent-team, by absolute path."""
    found = shutil.which("agent-team")   # the PATH entry (e.g. ~/.local/bin/agent-team) survives reinstalls
    if found:
        return str(Path(found).absolute()), ["mcp"]
    return sys.executable, ["-m", "agent_team", "mcp"]


def snippets() -> str:
    command, args = launch()
    entry = json.dumps({"mcpServers": {"agent-team": {"command": command, "args": args}}}, indent=2)
    return (f"Claude Code:   claude mcp add --scope user agent-team -- {command} {' '.join(args)}\n\n"
            f"Codex (~/.codex/config.toml):\n[mcp_servers.agent-team]\ncommand = \"{command}\"\nargs = {json.dumps(args)}\n\n"
            f"Cursor (~/.cursor/mcp.json), and most other agents' mcp.json:\n{entry}\n")


def _confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        ui.say(f"{question} Run again with --yes to go ahead, or add it yourself:\n\n{snippets()}")
        return False
    return input(f"{question} [Y/n] ").strip().lower() in ("", "y", "yes")


def install(client: str, yes: bool = False, scope: str = "user") -> int:
    command, args = launch()
    if client == "claude":
        claude = shutil.which("claude")
        if not claude:
            ui.say("Claude Code's `claude` command isn't on the PATH. In Claude Code you can also run:\n"
                   f"  claude mcp add --scope {scope} agent-team -- {command} {' '.join(args)}")
            return 1
        argv = [claude, "mcp", "add", "--scope", scope, "agent-team", "--", command, *args]
        if not _confirm(f"Register agent-team with Claude Code ({scope} scope)?", yes):
            return 0
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0 and "already exists" in (r.stdout + r.stderr):
            ui.say("Claude Code already has an agent-team server.")
            return 0
        if r.returncode != 0:
            ui.say(f"claude mcp add failed: {(r.stdout + r.stderr).strip()}")
            return 1
        ui.action("registered with Claude Code; start a new session and ask it to use the agent-team tools")
        return 0
    if client == "codex":
        path = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if re.search(r"^\[mcp_servers\.agent-team\]", text, re.M):
            ui.say(f"{path} already has agent-team.")
            return 0
        if not _confirm(f"Add agent-team to {path}?", yes):
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        block = f'\n[mcp_servers.agent-team]\ncommand = {json.dumps(command)}\nargs = {json.dumps(args)}\n'
        path.write_text(text.rstrip() + "\n" + block if text else block.lstrip(), encoding="utf-8")
        ui.action(f"added agent-team to {path}; start a new Codex session")
        return 0
    if client == "cursor":
        path = Path.home() / ".cursor" / "mcp.json"
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                ui.say(f"{path} isn't valid JSON; add this yourself:\n\n{snippets()}")
                return 1
        servers = data.setdefault("mcpServers", {})
        if "agent-team" in servers:
            ui.say(f"{path} already has agent-team.")
            return 0
        if not _confirm(f"Add agent-team to {path}?", yes):
            return 0
        servers["agent-team"] = {"command": command, "args": args}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        ui.action(f"added agent-team to {path}; reload Cursor's MCP servers")
        return 0
    ui.say(f"Clients this can set up: {', '.join(CLIENTS)}. For any other agent:\n\n{snippets()}")
    return 1
