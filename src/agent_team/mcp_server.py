"""agent-team as an MCP server: the team, as tools for any coding agent.

    agent-team mcp                    # serve over stdio (what a coding agent starts)
    agent-team mcp install --client claude|codex|cursor

Claude Code, Codex, Cursor, Gemini CLI, OpenCode and any other agent that speaks the Model Context
Protocol can then see the team's state and start its runs: "have the team build the export
command as a PR", and the agent calls team_start_run, follows team_run_output, and reports.

Runs go through the same background jobs as the dashboard (.team/jobs/), with the same spend
limits, shift lock and guardrails. What stays with you: approving pull requests and releases.
Those tools aren't offered, so no agent can approve on your behalf.

The built-in playbooks are offered as MCP prompts too, so an agent's own prompt menu lists them
(code-review, plan-feature, fix-bug, ...).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import __version__

PROTOCOL = "2025-06-18"
OUTPUT_LIMIT = 20_000
WORKFLOWS = ["build", "fix", "discuss", "ship", "autopilot", "market", "doctor"]

INSTRUCTIONS = """agent-team runs a small AI dev team on a project: a lead plans and reviews, builders write the
code, tests and behaviour checks run, and a devops member reviews, merges and releases through
GitHub. Use team_status to see the team, then team_start_run to have it work: it returns a run id
at once (builds take minutes); follow it with team_run_output until its status isn't "running",
and report what the team did. Approvals of pull requests and releases are the owner's: tell the
user the command when one waits (team_status lists them)."""

PROJECT = {"type": "string", "description": "The project folder (default: where the agent started this server)."}

TOOLS = [
    {"name": "team_status",
     "description": "The project's agent-team: members and their models, recent runs, spend, and what waits for the "
                    "owner's approval (pull requests, a proposed release).",
     "inputSchema": {"type": "object", "properties": {"project": PROJECT, "health": {
         "type": "boolean", "description": "Also check that every member's model can be reached (slower)."}}}},
    {"name": "team_ready",
     "description": "What this machine and project still need before the team can work (git, GitHub, keys, Ollama, "
                    "models, tool servers), each with the command that fixes it.",
     "inputSchema": {"type": "object", "properties": {"project": PROJECT}}},
    {"name": "team_start_run",
     "description": "Start a team run in the background and return its id at once. build: plan, implement, test, "
                    "review a task (task; with branch and pr: true it opens a pull request). fix: apply review "
                    "feedback on a PR (number). discuss: agree a roadmap (topic). ship: one devops shift (merge, "
                    "release). autopilot: work through a milestone. market: brief, site and deck. doctor: check the "
                    "team. Follow it with team_run_output.",
     "inputSchema": {"type": "object", "required": ["workflow"], "properties": {
         "project": PROJECT,
         "workflow": {"type": "string", "enum": WORKFLOWS},
         "task": {"type": "string", "description": "build: what to build, in a sentence or two."},
         "branch": {"type": "string", "description": "build: create this branch first, e.g. team/export."},
         "pr": {"type": "boolean", "description": "build: open a pull request when approved (needs branch)."},
         "parallel": {"type": "boolean", "description": "build: split the plan across every builder."},
         "number": {"type": "integer", "description": "fix: the pull request number."},
         "topic": {"type": "string", "description": "discuss: what to plan, e.g. next features."},
         "milestone": {"type": "string", "description": "autopilot: e.g. M2."},
         "rounds": {"type": "integer", "description": "build, fix, market: most rounds."}}}},
    {"name": "team_run_output",
     "description": "A run's output since `offset` (start at 0, then pass back the offset returned) and its status: "
                    "running, succeeded, not approved, spend limit, failed or stopped.",
     "inputSchema": {"type": "object", "required": ["run_id"], "properties": {
         "project": PROJECT, "run_id": {"type": "string"}, "offset": {"type": "integer"}}}},
    {"name": "team_runs",
     "description": "The latest background runs with their status.",
     "inputSchema": {"type": "object", "properties": {"project": PROJECT}}},
    {"name": "team_stop_run",
     "description": "Stop a running run (it finishes cleanly at its next step).",
     "inputSchema": {"type": "object", "required": ["run_id"], "properties": {"project": PROJECT, "run_id": {"type": "string"}}}},
    {"name": "team_behaviour",
     "description": "The project's behaviour checks: the user journeys it has, and what the latest check found "
                    "(which journeys behave differently, with the first difference).",
     "inputSchema": {"type": "object", "properties": {"project": PROJECT}}},
]


class ToolError(Exception):
    pass


def _root(args: dict, default: Path) -> Path:
    from .config import ConfigError, find_config
    start = Path(args.get("project") or default).expanduser().resolve()
    try:
        return find_config(start).parent
    except ConfigError:
        raise ToolError(f"no agent-team in {start}: run `agent-team init` there first (or pass project)") from None


def call(name: str, args: dict, default: Path) -> dict:
    """One tool call: plain JSON-able data, or ToolError."""
    from . import jobs
    if name == "team_ready":
        from . import readiness
        start = Path(args.get("project") or default).expanduser().resolve()
        return {"checks": readiness.as_dicts(readiness.check(start))}
    root = _root(args, default)
    from .config import load
    if name == "team_status":
        from .cli import status_data
        return status_data(load(root), bool(args.get("health")))
    if name == "team_start_run":
        workflow = args.get("workflow")
        if workflow not in WORKFLOWS:
            raise ToolError(f"workflow is one of {', '.join(WORKFLOWS)}")
        params = {k: v for k, v in args.items() if k not in ("project", "workflow")}
        try:
            job = jobs.start(root, workflow, params)
        except jobs.JobError as e:
            raise ToolError(str(e)) from None
        return {"run_id": job["id"], "status": job["status"], "argv": job["argv"],
                "next": "call team_run_output with this run_id (offset 0) until status isn't running"}
    if name == "team_run_output":
        try:
            out = jobs.output(root, str(args.get("run_id", "")), int(args.get("offset") or 0))
        except (jobs.JobError, ValueError) as e:
            raise ToolError(str(e)) from None
        text = out["text"]
        if len(text) > OUTPUT_LIMIT:   # the newest part matters most; the offset still covers everything
            text = f"(… {len(text) - OUTPUT_LIMIT:,} earlier characters left out)\n" + text[-OUTPUT_LIMIT:]
        return {"status": out["status"], "offset": out["offset"], "output": text}
    if name == "team_runs":
        return {"runs": [{k: j.get(k) for k in ("id", "workflow", "status", "started", "params")}
                         for j in jobs.list_jobs(root)]}
    if name == "team_stop_run":
        try:
            job = jobs.stop(root, str(args.get("run_id", "")))
        except jobs.JobError as e:
            raise ToolError(str(e)) from None
        return {"run_id": job["id"], "status": job["status"]}
    if name == "team_behaviour":
        from . import behaviour
        team = load(root)
        latest = behaviour.recent(team, 1)
        return {"server_configured": team.behaviour.server in team.mcp,
                "journeys": [{"name": s.name, "kind": s.kind, "source": s.source} for s in team.behaviour.scenarios],
                "latest_check": ({"when": latest[0]["created"], "label": latest[0]["label"],
                                  "outcomes": [{k: o.get(k) for k in ("name", "kind", "status", "first_difference",
                                                                      "breaking", "added", "notes")}
                                               for o in latest[0]["outcomes"]]} if latest else None)}
    raise ToolError(f"no tool named {name!r}")


def _playbooks(default: Path) -> list:
    """The built-in playbooks, and the project's own when the server runs in one."""
    from .workflows import playbook
    try:
        root = _root({}, default)
    except ToolError:
        root = None
    return playbook.catalog(root)


def handle(message: dict, default: Path) -> dict | None:
    """The reply to one JSON-RPC message (None for notifications)."""
    method, rid = message.get("method"), message.get("id")
    if rid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}, "prompts": {}},
                  "serverInfo": {"name": "agent-team", "version": __version__}, "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "prompts/list":
        result = {"prompts": [{"name": e.name, "description": e.description[:300],
                               "arguments": [{"name": "what", "description": "what it's for this time", "required": False}]}
                              for e in _playbooks(default)]}
    elif method == "prompts/get":
        params = message.get("params") or {}
        name = str(params.get("name", ""))
        found = next((e for e in _playbooks(default) if e.name == name), None)
        if not found:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"no prompt named {name!r}"}}
        from .workflows.playbook import text
        what = str((params.get("arguments") or {}).get("what", ""))
        result = {"description": found.description[:300],
                  "messages": [{"role": "user", "content": {"type": "text", "text": text(found, what)}}]}
    elif method == "tools/call":
        params = message.get("params") or {}
        try:
            data = call(str(params.get("name")), params.get("arguments") or {}, default)
            result = {"content": [{"type": "text", "text": json.dumps(data, default=str, indent=1)}],
                      "structuredContent": data}
        except ToolError as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:   # a tool's failure is the caller's to see, not a crash of the server
            result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def serve(default: Path | None = None) -> int:
    """Answer MCP messages on stdin/stdout until stdin closes. Nothing else may print to stdout."""
    default = (default or Path.cwd()).resolve()
    out = sys.stdout
    sys.stdout = sys.stderr   # stray prints from the workflows' code must not corrupt the protocol
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        else:
            reply = handle(message, default)
        if reply is not None:
            out.write(json.dumps(reply, default=str) + "\n")
            out.flush()
    return 0
