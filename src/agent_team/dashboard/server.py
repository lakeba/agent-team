"""`agent-team ui`: a read-only dashboard for a project's team, served on this machine only.

Pages are static files; data comes from a small JSON API that re-reads `.team.toml`, the run logs
and the usage file on every request, so it always shows the current state. Nothing in it writes.

Safety: it binds to 127.0.0.1, answers only requests whose Host is that address (no DNS
rebinding), allows GET only, sends a strict Content-Security-Policy, and never returns secrets:
providers show the *name* of their key variable and whether it is set, never its value.
"""
from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from .. import __version__, config, logs, providers, usage
from ..agent import team_roster

STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def team_info(team: config.Team) -> dict:
    roles_needed = {"lead": "plan, build, review", "builder": "build", "devops": "ship, setup", "marketing": "market"}
    members = []
    for a in team.agents.values():
        p = team.providers[a.provider]
        members.append({
            "name": a.name, "role": a.role, "description": a.description, "owns": a.owns,
            "provider": p.name, "kind": p.kind, "model": a.model, "effort": a.effort,
            "url": p.url if p.kind in ("ollama", "openai", "agent-http") else "",
            "key_env": p.api_key_env, "key_set": bool(p.api_key_env and os.environ.get(p.api_key_env)),
            "remote": p.kind == "agent-http" or bool(p.url and "localhost" not in p.url and "127.0.0.1" not in p.url),
            "custom_prompt": bool(a.prompt),
        })
    pr = team.project
    return {
        "version": __version__, "root": str(team.root),
        "project": {"name": pr.name, "repo": pr.repo, "test_command": pr.test_command,
                    "guarantees": pr.guarantees, "context_skip": pr.context_skip},
        "members": members,
        "missing_roles": {r: why for r, why in roles_needed.items() if not team.by_role(r, required=False)},
        "roster": team_roster(team),
    }


def health(team: config.Team, timeout: float = 25.0) -> dict:
    """Run every member's reachability check in parallel; slow checks report a timeout."""
    def check(a):
        p = team.providers[a.provider]
        try:
            return providers.build(p, team.secret(p)).check(a.model)
        except Exception as e:
            return f"FAILED: {type(e).__name__}: {e}"
    out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {a.name: pool.submit(check, a) for a in team.agents.values()}
        for name, fut in futures.items():
            try:
                status = fut.result(timeout=timeout)
            except FutureTimeout:
                status = f"FAILED: no answer within {int(timeout)} seconds"
            out[name] = {"ok": not status.startswith("FAILED"), "status": status}
    return {"checked_at": usage.now(), "members": out}


def usage_info(team: config.Team) -> dict:
    entries = usage.load(team.root)
    summary = usage.summarize(entries, team.pricing)
    by_day: dict[str, dict] = {}
    for e in entries:
        day = (e.get("at") or "")[:10] or "unknown"
        d = by_day.setdefault(day, {"input": 0, "output": 0, "cost": 0.0})
        price = usage.price_for(e.get("model", ""), e.get("kind", ""), team.pricing)
        d["input"] += e.get("input", 0) + e.get("cache_read", 0) + e.get("cache_write", 0)
        d["output"] += e.get("output", 0)
        d["cost"] = round(d["cost"] + price.cost(e), 4)
    summary["by_day"] = dict(sorted(by_day.items()))
    summary["recorded_calls"] = len(entries)
    return summary


class _GitHubCache:
    def __init__(self, ttl: float = 60.0):
        self.ttl, self.at, self.value, self.lock = ttl, 0.0, None, threading.Lock()

    def get(self, team: config.Team) -> dict:
        with self.lock:
            if self.value is not None and time.time() - self.at < self.ttl:
                return self.value
            self.value, self.at = _github(team), time.time()
            return self.value


def _github(team: config.Team) -> dict:
    repo = team.project.repo
    if not repo:
        return {"available": False, "reason": "[project].repo is not set in .team.toml"}
    from .. import github as gh
    try:
        prs = gh.gh_json("pr", "list", "-R", repo, "--state", "open", "--limit", "20", "--json",
                         "number,title,author,isDraft,updatedAt,url")
        issues = gh.gh_json("issue", "list", "-R", repo, "--state", "open", "--limit", "20", "--json",
                            "number,title,labels,updatedAt,url")
        releases = gh.gh_json("release", "list", "-R", repo, "--limit", "5", "--json", "tagName,publishedAt,isLatest")
        merged = gh.gh_json("pr", "list", "-R", repo, "--state", "merged", "--limit", "8", "--json",
                            "number,title,mergedAt,url")
        head = gh.head_sha(repo)
        run = gh.run_for_commit(repo, head)
    except Exception as e:  # gh missing, signed out, no access: show why instead of failing the page
        return {"available": False, "reason": f"GitHub CLI: {e}"}
    return {"available": True, "repo": repo, "url": f"https://github.com/{repo}", "open_prs": prs,
            "open_issues": [{**i, "labels": [l["name"] for l in i.get("labels", [])]} for i in issues],
            "releases": releases, "recently_merged": merged,
            "main": {"sha": head[:10], "ci": f"{run['status']} {run['conclusion'] or ''}".strip() if run else "no CI run"}}


def make_handler(root: Path, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    github_cache = _GitHubCache()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"agent-team-ui/{__version__}"

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, code: int = 200):
            self._send(code, json.dumps(payload, default=str).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            if self.headers.get("Host", "") not in allowed_hosts:
                return self._json({"error": "unexpected Host header"}, 421)
            path = self.path.split("?", 1)[0]
            if path in STATIC:
                name, ctype = STATIC[path]
                body = resources.files("agent_team.dashboard").joinpath("static", name).read_bytes()
                return self._send(200, body, ctype)
            if not path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            try:
                team = config.load(root)
            except config.ConfigError as e:
                return self._json({"error": f"config: {e}"}, 500)
            try:
                if path == "/api/team":
                    return self._json(team_info(team))
                if path == "/api/health":
                    return self._json(health(team))
                if path == "/api/runs":
                    return self._json({"runs": logs.parse(team.root)})
                if path == "/api/usage":
                    return self._json(usage_info(team))
                if path == "/api/github":
                    return self._json(github_cache.get(team))
            except Exception as e:  # keep the dashboard up and say what failed
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"error": "not found"}, 404)

        def _refuse(self):
            self._json({"error": "this dashboard is read-only"}, 405)

        do_POST = do_PUT = do_PATCH = do_DELETE = _refuse

        def log_message(self, fmt, *args):
            pass   # quiet: the terminal stays readable

    return Handler


def serve(project: Path, port: int = 8790, open_browser: bool = True) -> None:
    team = config.load(project)   # fail early with a clear config error
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(team.root, port))
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"agent-team dashboard for {team.project.name}: {url}  (read-only; Ctrl-C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
