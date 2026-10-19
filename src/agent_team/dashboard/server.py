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
import re
import secrets
import threading
import time
import urllib.parse
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
          "/runs.js": ("runs.js", "text/javascript; charset=utf-8"),
          "/settings.js": ("settings.js", "text/javascript; charset=utf-8"),
          "/activity.js": ("activity.js", "text/javascript; charset=utf-8"),
          "/projects.js": ("projects.js", "text/javascript; charset=utf-8"),
          "/lakeba-mark.svg": ("lakeba-mark.svg", "image/svg+xml"),
          "/behaviour.js": ("behaviour.js", "text/javascript; charset=utf-8"),
          "/setup.js": ("setup.js", "text/javascript; charset=utf-8"),
          "/mvp.js": ("mvp.js", "text/javascript; charset=utf-8")}
# The contract for programs using this API (the LakebaOS desktop client): `api` goes up only when a
# route changes in a way that breaks them; `features` names what this version offers.
API_VERSION = 1
FEATURES = ["meta", "client-token", "jobs.offset", "config.sha", "approve", "release.approve", "estimate", "story", "setup"]
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _approval_requests(root):
    from .. import gates
    return gates.requests(root)


def _lessons(root):
    from .. import memory
    return memory.lessons(root)


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
        "lessons": _lessons(team.root),
        "approval_requests": _approval_requests(team.root),
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


def make_handler(root: Path | None, port: int, token: str | None = None, folder: Path | None = None,
                 client_token: str | None = None):
    """`root` is the project (None: no project yet, so the page shows the setup wizard; creating
    or opening a project there switches this dashboard to it). `folder` is where the dashboard was
    started, which the wizard offers to set up. `client_token`: the program that started this
    dashboard (`ui --client`) may POST with `Authorization: Bearer <it>` instead of the page's
    same-origin header and session token."""
    here = {"root": root}
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
            query = dict(urllib.parse.parse_qsl(self.path.partition("?")[2]))
            if path == "/api/session":
                # Readable only by pages from this origin: no CORS headers are ever sent.
                return self._json({"token": session_token})
            if path == "/api/meta":
                return self._json({"version": __version__, "api": API_VERSION, "features": FEATURES,
                                   "project": str(here["root"]) if here["root"] else "", "setup": here["root"] is None})
            try:
                if path == "/api/setup/status":
                    from .. import setup_wizard
                    return self._json({**setup_wizard.status(), "here": setup_wizard.folder_info(folder),
                                       "project": str(here["root"]) if here["root"] else ""})
                if path == "/api/setup/pull":
                    from .. import setup_wizard
                    return self._json(setup_wizard.pull_status(query.get("url", ""), query.get("model", "")))
                if path == "/api/setup/scan":
                    from .. import setup_wizard
                    return self._json({"servers": setup_wizard.scan()})
                if path == "/api/setup/github":
                    from .. import setup_wizard
                    return self._json({**setup_wizard.github_status(), "login": dict(setup_wizard.LOGIN)})
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            root = here["root"]
            if root is None:
                if path == "/api/team":
                    return self._json({"setup": True})
                return self._json({"error": "no project yet: finish the setup first", "setup": True}, 409)
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
                if path == "/api/estimate":
                    from .. import estimate
                    query = dict(q.split("=", 1) for q in self.path.partition("?")[2].split("&") if "=" in q)
                    wf = query.get("workflow", "build")
                    if wf not in ("build", "fix", "ship", "discuss", "market", "setup", "autopilot"):
                        return self._json({"error": "unknown workflow"}, 400)
                    cycles = int(query["cycles"]) if query.get("cycles", "").isdigit() else 1
                    return self._json(estimate.estimate(team, wf, cycles))
                if path == "/api/behaviour":
                    from .. import behaviour
                    return self._json({"checks": behaviour.recent(team),
                                       "configured": team.behaviour.server in team.mcp})
                if path.startswith("/api/evidence/"):
                    from .. import behaviour
                    parts = urllib.parse.unquote(path.removeprefix("/api/evidence/")).split("/")
                    if (len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", parts[0])
                            or not re.fullmatch(r"\d+-(base|work)\.png", parts[1])):
                        return self._json({"error": "not found"}, 404)
                    png = behaviour.evidence_root(team) / parts[0] / parts[1]
                    if not png.is_file():
                        return self._json({"error": "not found"}, 404)
                    return self._send(200, png.read_bytes(), "image/png")
                if path == "/api/metrics":
                    from .. import metrics
                    return self._json(metrics.compute(team))
                if path == "/api/templates":
                    from .. import templates
                    return self._json({"templates": templates.TEMPLATES})
                if path == "/api/projects":
                    from .. import projects
                    return self._json({"current": str(team.root), "projects": projects.all_summaries()})
                if path == "/api/evals":
                    from .. import evals
                    return self._json({"runs": evals.history(team.root)})
                if path == "/api/scoreboard":
                    from .. import scoreboard
                    return self._json(scoreboard.compute(team))
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
                if path == "/api/setup/ready":
                    from .. import setup_wizard
                    return self._json({"checks": setup_wizard.ready(team.root)})
                if path == "/api/mvp":
                    from .. import mvp
                    return self._json(mvp.summary(team))
                if path == "/api/app":
                    from .. import apprun
                    return self._json({**apprun.status(team.root),
                                       "how": apprun.detect(team.root, team.project.run_command)})
                if path.startswith("/api/story/"):
                    from .. import progress
                    job_id = path.removeprefix("/api/story/")
                    out = jobs.output(team.root, job_id, 0)
                    return self._json({"status": out["status"], "story": progress.story(out["text"])})
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
            bearer = self.headers.get("Authorization", "")
            if client_token and bearer:
                if not secrets.compare_digest(bearer, f"Bearer {client_token}"):
                    return self._json({"error": "wrong client token"}, 403)
            else:
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
            from .. import setup_wizard
            try:
                if path.startswith("/api/setup/"):
                    if path == "/api/setup/project":
                        made = setup_wizard.create_project(body)
                        here["root"] = Path(made["root"])
                        return self._json(made)
                    if path == "/api/setup/open":
                        from .. import projects
                        target = str(body.get("root", ""))
                        if target not in projects.registered():
                            return self._json({"error": "unknown project"}, 404)
                        config.load(Path(target))
                        here["root"] = Path(target)
                        return self._json({"root": target})
                    if path == "/api/setup/key":
                        return self._json(setup_wizard.save_key(str(body.get("value", ""))))
                    if path == "/api/setup/pull":
                        return self._json(setup_wizard.pull_model(str(body.get("url", "")), str(body.get("model", ""))))
                    if path == "/api/setup/github/login":
                        return self._json(dict(setup_wizard.github_login()))
                    if here["root"] is None:
                        return self._json({"error": "create the project first"}, 409)
                    if path == "/api/setup/github/repo":
                        return self._json(setup_wizard.create_repo(here["root"], bool(body.get("private", True))))
                    if path == "/api/setup/identity":
                        name = str(body.get("name", "")).strip()[:80]
                        email = str(body.get("email", "")).strip()[:120]
                        if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+", email or "x@y"):
                            return self._json({"error": "give a name (and an email address if you like)"}, 422)
                        setup_wizard._run(["git", "config", "user.name", name], here["root"])
                        setup_wizard._run(["git", "config", "user.email", email or "builder@lakeba-os.local"], here["root"])
                        return self._json({"ok": True})
                    if path == "/api/setup/tasks":
                        return self._json({"tasks": setup_wizard.suggest_tasks(here["root"])})
                    return self._json({"error": "not found"}, 404)
                root = here["root"]
                if root is None:
                    return self._json({"error": "no project yet: finish the setup first", "setup": True}, 409)
                if path.startswith("/api/app/"):
                    from .. import apprun
                    team = config.load(root)
                    if path == "/api/app/start":
                        return self._json(apprun.start(team.root, team.project.run_command))
                    if path == "/api/app/stop":
                        return self._json(apprun.stop(team.root))
                    if path == "/api/app/cli":
                        return self._json(apprun.run_cli(team.root, str(body.get("args", "")), team.project.run_command))
                if path == "/api/mvp/keep":
                    from .. import mvp
                    return self._json(mvp.keep_version(config.load(root), str(body.get("message", ""))))
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
                    params = body.get("params") or {}
                    if isinstance(params, dict) and "release" in params:
                        return self._json({"error": "approving a release has its own route: POST /api/release/approve"}, 422)
                    return self._json(jobs.start(root, str(body.get("workflow", "")), params))
                if path == "/api/release/approve":
                    # The owner approves the release the devops shift proposed, and only that one: a shift
                    # starts that publishes it. Never offered over MCP.
                    from ..workflows import ship
                    version = body.get("version")
                    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
                        return self._json({"error": "version must look like 1.2.3"}, 422)
                    proposal = ship.release_proposal(root)
                    if not proposal:
                        return self._json({"error": "no release is waiting for your approval"}, 409)
                    if proposal.get("version") != version:
                        return self._json({"error": f"the release waiting is v{proposal.get('version')}, not v{version}"}, 409)
                    config.load(root)
                    return self._json(jobs.start(root, "ship", {"release": version}))
                if path == "/api/composition":
                    from .. import composition as comp
                    current = comp.from_data(body.get("data") or {})
                    return self._json({"composition": {"models": current.models, "ollama_url": current.ollama_url,
                                                       "local_kind": current.local_kind,
                                                       "ollama_model": current.ollama_model, "extras": list(current.extras),
                                                       "builders": current.builders, "per_run": current.per_run,
                                                       "per_day": current.per_day},
                                       "models": comp.MODELS, "max_builders": comp.MAX_BUILDERS,
                                       "extras": {r: {"name": n, "about": a} for r, (n, a) in comp.EXTRAS.items()}})
                if path == "/api/composition/apply":
                    from .. import composition as comp
                    try:
                        data = comp.apply(body.get("data") or {}, comp.from_form(body.get("composition") or {}))
                    except ValueError as e:
                        return self._json({"error": str(e)}, 422)
                    return self._json({"data": data, "preview": config_io.plan_change(root, data)})
                if path == "/api/models":   # what a connection's server serves, for the member editor
                    from ..readiness import probe
                    url = str(body.get("url", "")).strip()
                    if config.address_problem(url) or not url:
                        return self._json({"models": [], "error": config.address_problem(url) or "no address"})
                    found = probe(url, timeout=4)
                    return self._json({"models": (found or {}).get("models", []), "reachable": bool(found)})
                if path == "/api/ollama/find":
                    from ..readiness import find_local
                    return self._json({"servers": find_local(scan=True)})
                if path == "/api/templates/apply":
                    from .. import templates
                    try:
                        data = templates.apply(body.get("data") or {}, str(body.get("id", "")))
                    except ValueError as e:
                        return self._json({"error": str(e)}, 422)
                    return self._json({"data": data, "preview": config_io.plan_change(root, data)})
                if path == "/api/projects/open":
                    from .. import projects
                    target = str(body.get("root", ""))
                    if target not in projects.registered():
                        return self._json({"error": "unknown project"}, 404)
                    return self._json({"url": _open_dashboard(target)})
                if path == "/api/approve":
                    from .. import gates, github as gh_mod
                    team = config.load(root)
                    number = body.get("number")
                    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                        return self._json({"error": "number must be the pull request number"}, 422)
                    info = gh_mod.gh_json("pr", "view", str(number), "-R", team.project.repo, "--json", "headRefOid,state")
                    if info["state"] != "OPEN":
                        return self._json({"error": f"PR #{number} is {info['state'].lower()}"}, 422)
                    gates.approve(team.root, number, info["headRefOid"])
                    return self._json({"approved": number, "sha": info["headRefOid"]})
                if path == "/api/jobs/stop":
                    return self._json(jobs.stop(root, str(body.get("id", ""))))
            except (config.ConfigError, jobs.JobError, setup_wizard.SetupError) as e:
                return self._json({"error": str(e)}, 422)
            except Exception as e:
                from .. import apprun
                if isinstance(e, apprun.RunError):
                    return self._json({"error": str(e)}, 422)
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"error": "not found"}, 404)

        def _refuse(self):
            self._json({"error": "method not allowed"}, 405)

        do_PUT = do_PATCH = do_DELETE = _refuse

        def log_message(self, fmt, *args):
            pass   # quiet: the terminal stays readable

    return Handler


def _open_dashboard(root: str) -> str:
    """Start another project's dashboard on a free port (detached) and return its address."""
    import socket
    import subprocess
    import sys
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.Popen([sys.executable, "-m", "agent_team.cli", "ui", "--no-open", "--port", str(port), "-C", root],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(40):
        time.sleep(0.25)
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
    return f"http://127.0.0.1:{port}/"


def _test_provider(body: dict) -> dict:
    """Check a provider the person is about to add, before it's saved. Secrets come from this
    dashboard's own environment (the variable named), never from the request."""
    p = body.get("provider") or {}
    kind = str(p.get("kind", ""))
    if kind not in config.PROVIDER_KINDS:
        raise config.ConfigError(f"unknown kind {kind!r}")
    cfg = config.ProviderConfig(name="test", kind=kind, url=str(p.get("url", "")),
                                api_key_env=str(p.get("api_key_env", "")))
    problem = config.address_problem(cfg.url)
    if problem:
        return {"ok": False, "status": f"FAILED: {problem}", "note": ""}
    secret = os.environ.get(cfg.api_key_env, "") if cfg.api_key_env else ""
    status = providers.build(cfg, secret).check(str(body.get("model", "")))
    note = ("" if not cfg.api_key_env or secret else
            f"{cfg.api_key_env} isn't set in the environment this dashboard was started from.")
    return {"ok": not status.startswith("FAILED"), "status": status, "note": note}


def serve(project: Path, port: int = 8790, open_browser: bool = True, from_app: bool = False,
          client_token: str | None = None) -> None:
    """The dashboard for `project`; without a .team.toml there (or above it), the setup wizard, which
    offers to set up that folder. Started from the Lakeba OS app (`from_app`), the one project there
    is opens directly. Started by a program (`client_token`, from `ui --client`): it says it's ready
    with one JSON line on stdout, accepts that program's token, and stops when its stdin closes, so
    it never outlives the program."""
    try:
        team = config.load(project)
    except config.ConfigError as e:
        if "no .team.toml found" not in str(e):
            raise   # a broken team file: say so, don't hide it behind the wizard
        team = None
        from .. import projects
        known = [p for p in projects.registered() if (Path(p) / config.CONFIG_NAME).is_file()]
        if from_app and len(known) == 1:   # opened from the app, not from a folder: the one project there is
            try:
                team = config.load(Path(known[0]))
            except config.ConfigError:
                team = None
    httpd = ThreadingHTTPServer(("127.0.0.1", port), None)
    # The port it's actually on (port 0 picks a free one): requests are checked against that Host.
    httpd.RequestHandlerClass = make_handler(team.root if team else None, httpd.server_address[1],
                                             folder=None if from_app else project, client_token=client_token)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    if client_token:
        def until_stdin_closes():
            import sys
            for _ in sys.stdin:
                pass
            httpd.shutdown()
        threading.Thread(target=until_stdin_closes, daemon=True).start()
        print(json.dumps({"event": "ready", "url": url, "port": httpd.server_address[1], "version": __version__,
                          "api": API_VERSION, "project": str(team.root) if team else ""}), flush=True)
    else:
        what = f"for {team.project.name}" if team else "(no project here yet: the setup wizard opens)"
        print(f"agent-team dashboard {what}: {url}  (Ctrl-C to stop; runs started here keep going)", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
