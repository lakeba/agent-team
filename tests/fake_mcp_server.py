"""A small MCP server for the tests: stdio, one JSON-RPC message per line.

Tools: echo (returns its text and the server's environment variable names), big (a large result),
hidden (never allowed), and REA's two process tools, done simply: capture_process_scenario really
runs the command with the scripted input and reports the screen, exit and created files;
compare_process_captures compares two such captures.
"""
import json
import os
import subprocess
import sys

TOOLS = [
    {"name": "echo", "description": "Echo text.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "big", "description": "A large result.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "hidden", "description": "x" * 5000, "inputSchema": {"type": "object", "properties": {}}},
    {"name": "capture_process_scenario", "description": "Run a command.", "inputSchema": {"type": "object"}},
    {"name": "compare_process_captures", "description": "Compare two runs.", "inputSchema": {"type": "object"}},
]


def files_in(paths):
    out = set()
    for root in paths:
        for folder, _, names in os.walk(root):
            out |= {os.path.relpath(os.path.join(folder, n), root) for n in names}
    return out


def capture(args):
    before = files_in(args.get("filesystem_observation_paths") or [])
    typed = "".join(e["data"].replace("\r", "\n") for e in args.get("events") or [] if e["type"] == "input")
    r = subprocess.run([args["executable"], *args.get("arguments", [])], cwd=args.get("working_directory"),
                       input=typed, capture_output=True, text=True, timeout=args.get("timeout_ms", 60000) / 1000)
    after = files_in(args.get("filesystem_observation_paths") or [])
    lines = (r.stdout + r.stderr).splitlines()
    return {"evidence_id": "ev_" + "0" * 64, "operation": "capture_process_scenario",
            "normalized_result": {
                "rendered_frames": [{"lines": lines + [""] * 3}],
                "exit": {"code": r.returncode, "signal": 0, "reason": "exited"},
                "filesystem_effects": [{"path": f"root_0:{p}", "status": "created"} for p in sorted(after - before)]}}


def compare(args):
    left, right = (args[k]["normalized_result"] for k in ("left", "right"))
    a, b = left["rendered_frames"][-1]["lines"], right["rendered_frames"][-1]["lines"]
    if a == b and left["exit"] == right["exit"]:
        return {"status": "equivalent", "first_divergence": {"status": "none"}}
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return {"status": "changed", "first_divergence": {
        "status": "found", "dimension": "terminal",
        "left": {"data": a[i] if i < len(a) else ""}, "right": {"data": b[i] if i < len(b) else ""}}}


def result(rid, value):
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": value}), flush=True)


for line in sys.stdin:
    msg = json.loads(line)
    method, rid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if method == "initialize":
        result(rid, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                     "serverInfo": {"name": "fake", "version": "1.0"}})
    elif method == "tools/list":
        result(rid, {"tools": TOOLS})
    elif method == "tools/call":
        name, args = params["name"], params.get("arguments") or {}
        if name == "echo":
            result(rid, {"content": [{"type": "text", "text": args["text"] + " | env: " + ",".join(sorted(os.environ))}]})
        elif name == "big":
            result(rid, {"content": [{"type": "text", "text": "y" * 50_000}]})
        elif name in ("capture_process_scenario", "compare_process_captures"):
            value = capture(args) if name.startswith("capture") else {"normalized_result": compare(args)}   # as REA
            result(rid, {"content": [{"type": "text", "text": json.dumps(value)}], "structuredContent": value})
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"no tool {name}"}}),
                  flush=True)
    elif rid is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown"}}), flush=True)
