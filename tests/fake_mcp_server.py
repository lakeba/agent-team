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
    {"name": "capture_browser_scenario", "description": "Drive a browser.", "inputSchema": {"type": "object"}},
    {"name": "capture_electron_scenario", "description": "Drive an Electron app.", "inputSchema": {"type": "object"}},
    {"name": "compare_web_screenshots", "description": "Compare two PNGs.", "inputSchema": {"type": "object"}},
    {"name": "inspect_managed_members", "description": "Read a .NET assembly.", "inputSchema": {"type": "object"}},
    {"name": "analyze_javascript_application", "description": "Read a JS package.", "inputSchema": {"type": "object"}},
]


def browse(args):
    """A pretend browser: the page's text (tags removed, then its links as REA's aria snapshot lists
    them) after the steps, which must name real text. A link name used twice fails a click on it, as
    Playwright's strict mode does. Captures after each step when asked, else at the end."""
    import re
    import urllib.parse
    import urllib.request

    def fetch(url):
        return urllib.request.urlopen(url, timeout=5).read().decode()

    def anchors(html):
        return [(h, " ".join(re.sub(r"<[^>]+>", " ", t).split())) for h, t in re.findall(r'<a [^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.S)]

    def artifacts(html, url):
        text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        text += "".join(f'\n- link "{t}":\n  - /url: {h}' for h, t in anchors(html))
        sha = os.urandom(32).hex() if "animated" in html else "a" * 64 if "v2" not in html else "b" * 64   # a spinner never settles
        png = {"sha256": sha, "bytes": 4, "media_type": "image/png",
               "data_base64": "iVBORw=="}
        return {"accessibility": {"state": "captured", "value": {"text": text}},
                "url": {"state": "captured", "value": {"url": url}},
                "screenshot": {"state": "captured", "value": png}}

    each = bool((args.get("capture") or {}).get("after_each_step"))
    url = args["start_url"]["url"]
    html = fetch(url)
    steps = [{"step_id": "scenario_start", "status": "completed", "artifacts": artifacts(html, url) if each else {}}]
    for a in args["actions"]:
        step = {"step_id": a["step_id"], "status": "completed", "artifacts": {}}
        name = (a.get("locator") or {}).get("name")
        if a["action"] == "goto":
            url = urllib.parse.urljoin(url, a["destination"]["url"])
            html = fetch(url)
        elif a["action"] == "click" and name is not None:
            same = [h for h, t in anchors(html) if t == name]
            if (a.get("locator") or {}).get("role") == "link" and len(same) > 1:
                error = (f"locator.click: Error: strict mode violation: getByRole('link', {{ name: '{name}', exact: true }}) "
                         f"resolved to {len(same)} elements:\n" + "".join(f'    {i}) <a href="{h}">{name}</a>\n' for i, h in enumerate(same, 1)))
                step.update(status="failed", error=error, artifacts=artifacts(html, url) if each else {})
                return {"normalized_result": {"steps": steps + [step], "events": {"items": []}}}
            if name not in html:   # as REA does: the scenario stops there, with no final capture
                step.update(status="failed", error=f"no element named {name}", artifacts=artifacts(html, url) if each else {})
                return {"normalized_result": {"steps": steps + [step], "events": {"items": []}}}
            elif same and (a.get("locator") or {}).get("role") == "link":   # a link: follow it
                url = urllib.parse.urljoin(url, same[0])
                html = fetch(url)
            else:   # clicking inside a <dialog> closes it, as accepting a cookie banner does
                html = re.sub(r"<dialog>.*?</dialog>", "", html, flags=re.S) if re.search(
                    rf"<dialog>[^<]*(<[^>]+>[^<]*)*?{re.escape(name)}", html) else html
        if each:
            step["artifacts"] = artifacts(html, url)
        steps.append(step)
    if not each:
        steps[-1]["artifacts"] = artifacts(html, args["start_url"]["url"])
    errors = [{"kind": "page-error", "text": "boom"}] if "boom" in html else []
    return {"normalized_result": {"steps": steps, "events": {"items": errors}}}


def electron(args):
    """A pretend Electron app, described by electron.json in its folder, in the shape REA reports:
    windows, blocked external effects, IPC channels, errors; a click needs a selector it lists."""
    app = args["application_path"]
    if not os.path.isfile(args["executable_path"]):
        raise FileNotFoundError(args["executable_path"])
    spec = json.load(open(os.path.join(app, "electron.json")))
    actions = [{"step_id": a["step_id"], "kind": a["kind"], "error": None,
                "status": "completed" if a["kind"] != "click" or a["selector"] in spec.get("selectors", []) else "failed"}
               for a in args.get("actions") or []]
    windows = [{"window_id": f"window:{i + 1}", "url": f"file://{app}/{w['page']}", "title": w["title"],
                "visible": True, "destroyed": False} for i, w in enumerate(spec.get("windows", []))]
    events = ([{"kind": k, "event": e, "phase": "blocked"} for k, e in spec.get("blocked", [])]
              + [{"kind": "error", "event": "console-message", "phase": "observed"}] * spec.get("errors", 0))
    ipc = [{"channel": c, "argument_shapes": shapes, "result_shape": result, "error": False}
           for c, shapes, result in spec.get("ipc", [])]
    return {"normalized_result": {"actions": actions, "windows": windows, "timeline": {"events": events},
                                  "ipc": {"events": ipc}}}


def javascript(args):
    """Pretend static analysis: `export function|const NAME` lines in each .js file."""
    import re
    root = args["input_path"]
    obs = []
    for folder, _, names in os.walk(root):
        for n in names:
            if n.endswith(".js"):
                rel = os.path.relpath(os.path.join(folder, n), root)
                for name in re.findall(r"^export (?:function|const) (\w+)", open(os.path.join(folder, n)).read(), re.M):
                    obs.append({"properties": {"semantic_role": "export-binding", "module_path": rel, "exported_name": name}})
    return {"normalized_result": {"semantic_graph": {"nodes": [{"observations": obs}]}}}


def assembly(args):
    """A pretend assembly: a JSON file with types and methods in REA's shape."""
    return {"normalized_result": json.load(open(args["path"]))}


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
        elif name in ("capture_process_scenario", "compare_process_captures", "capture_browser_scenario", "capture_electron_scenario",
                      "inspect_managed_members", "compare_web_screenshots", "analyze_javascript_application"):
            value = {"capture_process_scenario": capture, "capture_browser_scenario": browse, "capture_electron_scenario": electron,
                     "inspect_managed_members": assembly, "analyze_javascript_application": javascript,
                     "compare_web_screenshots": lambda a: {"normalized_result": {"changed_pixel_ratio": 0.05}},
                     "compare_process_captures": lambda a: {"normalized_result": compare(a)}}[name](args)
            result(rid, {"content": [{"type": "text", "text": json.dumps(value)}], "structuredContent": value})
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"no tool {name}"}}),
                  flush=True)
    elif rid is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown"}}), flush=True)
