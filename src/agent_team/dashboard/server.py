"""`agent-team ui`: the team's dashboard, served on this machine only.

Pages are static files; data comes from a small JSON API that re-reads `.team.toml`, the run logs
and the usage file on every request, so it always shows the current state.

Safety: it binds to 127.0.0.1 and answers only requests whose Host is that address (no DNS
rebinding); pages get a strict Content-Security-Policy; secrets are never returned (providers show
the *name* of their key variable and whether it is set, never its value). The only writes are to
`.team.toml`, through POST endpoints that require the session token (which other sites can't read:
no CORS), a same-origin Origin header and a JSON body; every save is validated by reading it back
as the CLI would, refused if the file changed meanwhile, and leaves a `.team.toml.bak` backup.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from .. import __version__, config, config_io, jobs, logs, providers, usage
from ..agent import team_roster

STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/edit.js": ("edit.js", "text/javascript; charset=utf-8"),
          "/runs.js": ("runs.js", "text/javascript; charset=utf-8")}
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _release_proposal(root):
    from ..workflows.ship import release_proposal
    return release_proposal(root)


def installed_version() -> str:
    """The agent-team version installed now, which differs from __version__ once this process is
    older than an update (a dashboard started before the installer ran again)."""
    try:
        from importlib.metadata import version
        return version("agent-team")
    except Exception:
        return __version__


def team_info(team: config.Team) -> dict:
    from .. import skills as skills_mod
    skill_problems = skills_mod.problems(team)
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
            "skills": [_skill_label(team, s) for s in a.skills], "skills_problem": skill_problems.get(a.name, ""),
        })
    pr = team.project
    return {
        "version": __version__, "installed_version": installed_version(), "root": str(team.root),
        "project": {"name": pr.name, "repo": pr.repo, "test_command": pr.test_command,
                    "guarantees": pr.guarantees, "context_skip": pr.context_skip},
        "members": members,
        "release_policy": pr.release,
        "release_proposal": _release_proposal(team.root),
        "missing_roles": {r: why for r, why in roles_needed.items() if not team.by_role(r, required=False)},
        "roster": team_roster(team),
    }


def _skill_label(team: config.Team, entry: str) -> dict:
    from .. import skills as skills_mod
    try:
        s = skills_mod.load_one(team, entry)
        return {"path": entry, "name": s.name, "description": s.description, "chars": len(s.text)}
    except config.ConfigError:
        return {"path": entry, "name": entry, "description": "", "chars": 0, "missing": True}


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
    summary["today"] = by_day.get(usage.now()[:10], {}).get("cost", 0.0)
    summary["limits"] = {"per_run": team.limits.per_run, "per_day": team.limits.per_day}
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


MAX_BODY = 1024 * 1024


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def make_handler(root: Path, port: int, token: str | None = None):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}
    session_token = token or secrets.token_urlsafe(32)
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
                if path == "/api/jobs":
                    return self._json({"jobs": jobs.list_jobs(team.root)})
                if path.startswith("/api/jobs/"):
                    query = dict(q.split("=", 1) for q in self.path.partition("?")[2].split("&") if "=" in q)
                    try:
                        offset = int(query.get("offset", "0"))
                    except ValueError:
                        offset = 0
                    job_id = path.removeprefix("/api/jobs/")
                    return self._json({**jobs.get(team.root, job_id), **jobs.output(team.root, job_id, offset)})
                if path == "/api/session":
                    # Readable only by pages from this origin: no CORS headers are ever sent.
                    return self._json({"token": session_token})
                if path == "/api/config":
                    text = (team.root / config.CONFIG_NAME).read_text(encoding="utf-8")
                    return self._json({"data": config_io.to_data(team), "sha": _sha(text),
                                       "has_comments": any(l.lstrip().startswith("#") and not l.startswith("# agent-team configuration")
                                                           and not l.startswith("# Secrets never") for l in text.splitlines())})
            except jobs.JobError as e:
                return self._json({"error": str(e)}, 404)
            except Exception as e:  # keep the dashboard up and say what failed
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.headers.get("Host", "") not in allowed_hosts:
                return self._json({"error": "unexpected Host header"}, 421)
            if self.headers.get("Origin") not in allowed_origins:
                return self._json({"error": "cross-origin request refused"}, 403)
            if not secrets.compare_digest(self.headers.get("X-Agent-Team-Token", ""), session_token):
                return self._json({"error": "missing or wrong session token; reload the page"}, 403)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json({"error": "send JSON"}, 415)
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._json({"error": f"body must be 1..{MAX_BODY} bytes"}, 413)
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError:
                return self._json({"error": "invalid JSON"}, 400)
            path = self.path.split("?", 1)[0]
            try:
                if path == "/api/config/preview":
                    return self._json(config_io.plan_change(root, body.get("data")))
                if path == "/api/config/save":
                    cfg_path = config.find_config(root)
                    current = cfg_path.read_text(encoding="utf-8")
                    if body.get("sha") != _sha(current):
                        return self._json({"error": f"{config.CONFIG_NAME} changed on disk since this page loaded it; reload and redo your edit"}, 409)
                    return self._json(config_io.save(cfg_path.parent, body.get("data"), expected_old=current))
                if path == "/api/node-token":
                    return self._json({"token": secrets.token_urlsafe(32)})
                if path == "/api/test-provider":
                    return self._json(_test_provider(body))
                if path == "/api/discover":
                    from .. import discovery
                    return self._json({"nodes": discovery.discover(1.5)})
                if path == "/api/jobs/start":
                    config.load(root)   # refuse to start anything on a broken config
                    return self._json(jobs.start(root, str(body.get("workflow", "")), body.get("params") or {}))
                if path == "/api/jobs/stop":
                    return self._json(jobs.stop(root, str(body.get("id", ""))))
            except (config.ConfigError, jobs.JobError) as e:
                return self._json({"error": str(e)}, 422)
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"error": "not found"}, 404)

        def _refuse(self):
            self._json({"error": "method not allowed"}, 405)

        do_PUT = do_PATCH = do_DELETE = _refuse

        def log_message(self, fmt, *args):
            pass   # quiet: the terminal stays readable

    return Handler


def _test_provider(body: dict) -> dict:
    """Check a provider the person is about to add, before it's saved. Secrets come from this
    dashboard's own environment (the variable named), never from the request."""
    p = body.get("provider") or {}
    kind = str(p.get("kind", ""))
    if kind not in config.PROVIDER_KINDS:
        raise config.ConfigError(f"unknown kind {kind!r}")
    cfg = config.ProviderConfig(name="test", kind=kind, url=str(p.get("url", "")),
                                api_key_env=str(p.get("api_key_env", "")))
    secret = os.environ.get(cfg.api_key_env, "") if cfg.api_key_env else ""
    status = providers.build(cfg, secret).check(str(body.get("model", "")))
    note = ("" if not cfg.api_key_env or secret else
            f"{cfg.api_key_env} isn't set in the environment this dashboard was started from.")
    return {"ok": not status.startswith("FAILED"), "status": status, "note": note}


def serve(project: Path, port: int = 8790, open_browser: bool = True) -> None:
    team = config.load(project)   # fail early with a clear config error
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(team.root, port))
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"agent-team dashboard for {team.project.name}: {url}  (Ctrl-C to stop; runs started here keep going)", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
