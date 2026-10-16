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
    optional: bool = False    # only needed for some setups: shown as ○, never counted as missing


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


# Where a VM or container usually reaches the machine it runs on.
HOST_NAMES = ("host.docker.internal", "host.containers.internal", "host.lima.internal")
HOST_ADDRESSES = ("10.0.2.2",          # VirtualBox, QEMU and WSL1-style user networking
                  "192.168.64.1",      # UTM and Apple's Virtualization framework
                  "10.211.55.2", "10.37.129.2")   # Parallels shared and host-only networks


def _ollama_url(host: str) -> str:
    """http://HOST:11434 from OLLAMA_HOST-style values: "0.0.0.0", "host:port", "http://host"."""
    host = host.strip().rstrip("/")
    if not host:
        return ""
    if "://" not in host:
        host = "http://" + host
    scheme, rest = host.split("://", 1)
    name = rest.split("/", 1)[0]
    if name.startswith(("0.0.0.0", "[::]")):
        name = "localhost" + name[len("0.0.0.0" if name.startswith("0.0.0.0") else "[::]"):]
    if ":" not in name.split("]")[-1]:
        name += ":11434"
    return f"{scheme}://{name}"


def _gateways() -> list[str]:
    """The default gateways of this machine: in a VM, usually the machine it runs on."""
    out: list[str] = []
    try:   # Linux: /proc/net/route lists the default route with destination 00000000
        for line in Path("/proc/net/route").read_text().splitlines()[1:]:
            f = line.split()
            if len(f) > 2 and f[1] == "00000000":
                g = int(f[2], 16)
                out.append(".".join(str((g >> s) & 255) for s in (0, 8, 16, 24)))
    except (OSError, ValueError):
        pass
    if not out and sys.platform == "darwin":
        code, text = _run(["route", "-n", "get", "default"], Path.cwd(), timeout=3)
        out += [line.split()[-1] for line in text.splitlines() if code == 0 and "gateway:" in line]
    return [g for g in out if g and g != "0.0.0.0"]


def _own_addresses() -> set[str]:
    """This machine's IPv4 addresses (not loopback)."""
    import re
    code, text = _run(["ip", "-4", "-o", "addr"], Path.cwd(), timeout=3)
    if code != 0:
        code, text = _run(["ifconfig"], Path.cwd(), timeout=3)
    return {m for m in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", text if code == 0 else "") if not m.startswith("127.")}


def _neighbours(mine: set[str]) -> list[str]:
    """x.y.z.1 and x.y.z.2 on each of this machine's own IPv4 networks: where a hypervisor puts
    the host (Parallels uses .2, many others .1)."""
    out = []
    for ip in sorted(mine):
        base = ip.rsplit(".", 1)[0]
        out += [f"{base}.{n}" for n in (1, 2)]
    return out


def ollama_candidates() -> list[str]:
    """Addresses worth trying for an Ollama server, nearest first, without duplicates."""
    mine = _own_addresses()
    urls = [_ollama_url(os.environ.get("OLLAMA_HOST", "")), "http://localhost:11434"]
    urls += [f"http://{h}:11434" for h in (*HOST_NAMES, *_gateways(), *HOST_ADDRESSES, *_neighbours(mine))
             if h not in mine]   # this machine's own addresses reach the same server as localhost
    seen, out = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:24]


def find_ollama(timeout: float = 1.5, candidates: list[str] | None = None) -> list[tuple[str, list[str]]]:
    """Every Ollama server that answers, as (url, models), in the order of ollama_candidates().
    Tries them all at once, so it takes about `timeout` seconds at most."""
    from concurrent.futures import ThreadPoolExecutor
    urls = candidates if candidates is not None else ollama_candidates()
    with ThreadPoolExecutor(max_workers=max(1, len(urls))) as pool:
        found = list(pool.map(lambda u: ollama_models(u, timeout=timeout), urls))
    return [(u, m) for u, m in zip(urls, found) if m is not None]


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
    if team:   # only the connections some member actually uses
        used = {a.provider for a in team.agents.values()}
        for p in team.providers.values():
            if p.name not in used:
                continue
            if p.api_key_env:
                needed[p.api_key_env] = p.name
            elif p.kind == "anthropic":
                needed["ANTHROPIC_API_KEY"] = p.name
    for var, provider in needed.items():
        found = keys.where(var)
        out.append(Check(f"key {var}", bool(found),
                         f"found in the {found}" if found else f"not found (needed by [providers.{provider}])",
                         "" if found else f"agent-team keys set {var}   (in your own terminal; it asks for the value)"))
    if not team:   # before a team exists, Claude is a choice, not a requirement
        found = keys.where("ANTHROPIC_API_KEY")
        out.append(Check("key ANTHROPIC_API_KEY", True if found else False,
                         f"found in the {found}" if found else
                         "not set: only needed if members will run on Claude (local and network models need none)",
                         "" if found else "if you'll use Claude: agent-team keys set ANTHROPIC_API_KEY", optional=not found))
    if team:
        for a in team.agents.values():
            if a.github_token_env:
                out.append(_identity_check(a))
    if keys.loose_permissions():
        out.append(Check("keys file permissions", False, f"{keys.path()} is readable by other users",
                         f"chmod 600 {keys.path()}"))

    if team:   # tool servers: is each one's program installed? (doctor also starts them)
        for name, s in team.mcp.items():
            found = shutil.which(s.command)
            out.append(Check(f"MCP server {name}", bool(found), found or f"{s.command} isn't on the PATH",
                             "" if found else (f"install it (REA: npm install --global rea-agents)" if "rea" in s.command
                                               else f"install {s.command}, or fix command in [mcp.{name}]"),
                             "behaviour checks" if team.behaviour.server == name and team.behaviour.scenarios
                             else "members' MCP tools"))
    if team and team.behaviour.scenarios and team.sandbox.mode == "container":
        out.append(Check("behaviour checks", True, "skipped while [sandbox] mode is container", optional=True))
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
