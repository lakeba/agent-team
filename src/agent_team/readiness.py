"""Is this machine and project ready for the team? One checklist for init, doctor and the panel.

Each check says what it found and, when something is missing, the exact fix. Checks never raise:
a missing tool or file is a result, not an error.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from . import keys
from .config import CONFIG_NAME, ConfigError, Team, find_config, load


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    needed_for: str = ""      # what doesn't work until it's fixed; "" means everything


def _run(argv: list[str], cwd: Path, timeout: int = 15) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def ollama_models(url: str, timeout: float = 5.0) -> list[str] | None:
    """The models an Ollama server has pulled, or None if it can't be reached."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None


def is_local(url: str) -> bool:
    return any(h in url for h in ("localhost", "127.0.0.1", "[::1]"))


def _identity_check(member) -> Check:
    """Whether a member's own GitHub token works, and which account it posts as."""
    name, var = f"{member.name}'s GitHub identity", member.github_token_env
    token = os.environ.get(var, "")
    if not token:
        return Check(name, False, f"{var} isn't set",
                     f"agent-team keys set {var}   (the token of {member.name}'s bot account or app)")
    if not shutil.which("gh"):
        return Check(name, False, "the GitHub CLI isn't installed", "install the GitHub CLI (https://cli.github.com)")
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=20,
                           env={**os.environ, "GH_TOKEN": token})
    except (OSError, subprocess.TimeoutExpired):
        return Check(name, False, "GitHub didn't answer", "")
    login = r.stdout.strip()
    if r.returncode == 0 and login:
        return Check(name, True, f"posts as {login}")
    return Check(name, False, "GitHub refused the token", f"replace it: agent-team keys set {var}")


def check(root: Path, ollama_url: str = "") -> list[Check]:
    root = Path(root).resolve()
    out: list[Check] = []

    # Git and GitHub: the PR-based workflows need both.
    code, _ = _run(["git", "rev-parse", "--is-inside-work-tree"], root)
    git_ok = code == 0
    out.append(Check("git repository", git_ok, "yes" if git_ok else "this folder isn't a git repository",
                     "" if git_ok else "git init -b main && git add -A && git commit -m 'Initial commit'",
                     "build --pr, ship, plan"))
    if git_ok:
        name = _run(["git", "config", "user.name"], root)[1]
        email = _run(["git", "config", "user.email"], root)[1]
        ident_ok = bool(name and email)
        out.append(Check("git identity", ident_ok, f"{name} <{email}>" if ident_ok else "no user.name / user.email set, so commits fail",
                         "" if ident_ok else 'git config --global user.name "Your Name" && git config --global user.email "you@example.com"',
                         "commits, build --pr"))
    gh = shutil.which("gh")
    gh_ok = bool(gh) and _run(["gh", "auth", "status"], root)[0] == 0
    out.append(Check("GitHub CLI", gh_ok,
                     "signed in" if gh_ok else ("installed but not signed in" if gh else "not installed"),
                     "" if gh_ok else ("gh auth login" if gh else "install the GitHub CLI (https://cli.github.com), then gh auth login"),
                     "build --pr, ship, plan"))
    origin = _run(["git", "remote", "get-url", "origin"], root)[1] if git_ok else ""
    on_github = "github.com" in origin

    # The team file.
    team: Team | None = None
    try:
        team = load(find_config(root))
        out.append(Check("team file", True, f"{CONFIG_NAME} with {len(team.agents)} members"))
    except ConfigError as e:
        missing = "no " + CONFIG_NAME in str(e)
        out.append(Check("team file", False, "none yet" if missing else str(e),
                         "agent-team init (or /team-init)" if missing else f"fix {CONFIG_NAME}"))

    # The test command's program, which build runs after every round.
    cmd = team.project.test_command.split() if team else []
    if cmd:
        prog = next((w for w in cmd if "=" not in w), cmd[0])   # skip leading VAR=value assignments
        found = shutil.which(prog)
        hint = (" (installed with dotnet-install? add ~/.dotnet to PATH in ~/.profile)"
                if prog == "dotnet" and (Path.home() / ".dotnet" / "dotnet").exists() else "")
        out.append(Check("test command", bool(found), f"{team.project.test_command} ({found})" if found
                         else f"{prog} isn't on the PATH, so `{team.project.test_command}` can't run{hint}",
                         "" if found else f"install {prog}, or set [project].test_command in {CONFIG_NAME}",
                         "build, fix"))

    repo = team.project.repo if team else ""
    if repo:
        out.append(Check("GitHub repo", True, repo))
    elif on_github:
        out.append(Check("GitHub repo", True, f"origin {origin} (used until [project].repo is set)"))
    else:
        name = root.name
        out.append(Check("GitHub repo", False, "no GitHub repository yet",
                         f"gh repo create {name} --private --source . --push" + ("" if git_ok else " (after git init)"),
                         "build --pr, ship, plan"))

    # Keys: every variable a provider names, and the Anthropic key when a member uses Claude.
    needed: dict[str, str] = {}
    if team:
        for p in team.providers.values():
            if p.api_key_env:
                needed[p.api_key_env] = p.name
            elif p.kind == "anthropic":
                needed["ANTHROPIC_API_KEY"] = p.name
    elif ollama_url == "":
        needed["ANTHROPIC_API_KEY"] = "claude"
    for var, provider in needed.items():
        found = keys.where(var)
        out.append(Check(f"key {var}", bool(found),
                         f"found in the {found}" if found else f"not found (needed by [providers.{provider}])",
                         "" if found else f"agent-team keys set {var}   (in your own terminal; it asks for the value)"))
    if team:
        for a in team.agents.values():
            if a.github_token_env:
                out.append(_identity_check(a))
    if keys.loose_permissions():
        out.append(Check("keys file permissions", False, f"{keys.path()} is readable by other users",
                         f"chmod 600 {keys.path()}"))

    if team and team.sandbox.mode == "container":
        from . import sandbox
        ok, detail = sandbox.ready(team)
        out.append(Check("test sandbox", ok, detail,
                         "" if ok else "install or start Docker (or Podman), or set [sandbox].mode = \"off\""))

    # Ollama: every server a member uses, and whether its models are pulled.
    servers: dict[str, list[str]] = {}
    if team:
        for a in team.agents.values():
            p = team.providers[a.provider]
            if p.kind == "ollama":
                servers.setdefault((p.url or "http://localhost:11434").rstrip("/"), []).append(a.model)
    if ollama_url:   # a server being considered (init): check it whether or not a team uses it yet
        servers.setdefault(ollama_url.rstrip("/"), [])
    for url, models in servers.items():
        have = ollama_models(url)
        if have is None:
            fix = ("start Ollama here (the app, or: ollama serve); or, if it runs on another machine, set "
                   "url = \"http://HOST:11434\" under the connection in .team.toml (or the dashboard's Connections)"
                   if is_local(url) else
                   f"on the machine at {url}: let Ollama listen on the network (OLLAMA_HOST=0.0.0.0) and allow port 11434")
            out.append(Check(f"Ollama at {url}", False, "not reachable", fix))
            continue
        out.append(Check(f"Ollama at {url}", True, f"{len(have)} models"))
        for m in models:
            pulled = m in have or f"{m}:latest" in have
            hint = ""
            if not pulled and "mlx" in m and sys.platform != "darwin" and is_local(url):
                hint = " (an -mlx model only runs on Apple Silicon)"
            out.append(Check(f"model {m}", pulled, ("pulled" if pulled else f"not pulled at {url}{hint}"),
                             "" if pulled else (f"ollama pull {m}" if is_local(url) else f"on that machine: ollama pull {m}")))
    return out


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]
