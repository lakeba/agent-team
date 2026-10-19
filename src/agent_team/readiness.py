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


# Local model servers that speak the OpenAI API: mlx_lm.server (port 8080), LM Studio (1234),
# llama.cpp's server (8080). They're used through a provider of kind "openai".
OPENAI_PORTS = (8080, 1234)


def openai_models(url: str, timeout: float = 5.0) -> tuple[list[str] | None, str]:
    """(the models an OpenAI-compatible server lists, its Server header), or (None, "")."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/v1/models", timeout=timeout) as r:
            data = json.load(r)
            server = r.headers.get("Server", "")
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return None, ""
        return [m.get("id", "") for m in data["data"] if isinstance(m, dict) and m.get("id")], server
    except Exception:
        return None, ""


def server_label(url: str, models: list[str], server: str) -> str:
    """What an OpenAI-compatible server probably is, for people to recognise it."""
    s = server.lower()
    if "llama" in s:
        return "llama.cpp"
    if any("mlx" in m.lower() for m in models) or s.startswith("basehttp"):
        return "mlx_lm"            # mlx_lm.server is Python's http.server, serving MLX models
    if url.rstrip("/").endswith(":1234"):
        return "LM Studio"
    return "OpenAI-compatible server"


def probe(url: str, timeout: float = 1.5) -> dict | None:
    """{url, kind, label, models} for a local model server at `url`: Ollama, or an OpenAI-compatible
    one such as mlx_lm. None when nothing answers."""
    url = url.rstrip("/")
    port = url.rsplit(":", 1)[-1]
    if not (port.isdigit() and int(port) in OPENAI_PORTS):   # Ollama's port, or an address given by hand
        models = ollama_models(url, timeout=timeout)
        if models is not None:
            return {"url": url, "kind": "ollama", "label": "Ollama", "models": models}
        if port == "11434":
            return None
    models, server = openai_models(url, timeout=timeout)
    if models is not None:
        # mlx_lm also lists models by their cache folder; people pick by name, so leave the paths out
        named = [m for m in models if not m.startswith(("/", "~", "./")) and "\\" not in m]
        return {"url": url, "kind": "openai", "label": server_label(url, models, server), "models": named}
    return None


def local_candidates() -> list[str]:
    """Where to look for local model servers: the Ollama addresses, and the same hosts on the
    ports OpenAI-compatible servers use (mlx_lm, LM Studio)."""
    ollama = ollama_candidates()
    hosts = [u.rsplit(":", 1)[0] for u in ollama]
    extra = [f"{h}:{p}" for h in dict.fromkeys(hosts) for p in OPENAI_PORTS]
    for name in ("MLX_LM_URL", "OPENAI_BASE_URL"):
        v = os.environ.get(name, "").strip().rstrip("/")
        if v.startswith(("http://", "https://")):
            extra.insert(0, v.removesuffix("/v1"))
    return list(dict.fromkeys(ollama + extra))


SCAN_PORTS = (11434, *OPENAI_PORTS)
SCAN_NETWORKS = 3          # at most this many of this machine's networks are scanned
# In a VM, the computers of the home network aren't on the VM's own network: try the usual ones.
HOME_NETWORKS = ("192.168.0", "192.168.1", "10.0.0")
VM_VENDORS = ("parallels", "vmware", "virtualbox", "innotek", "qemu", "kvm", "xen", "microsoft corporation",
              "bochs", "utm", "apple virtualization")


def in_vm() -> bool:
    """Whether this machine is a virtual machine (or a container on one), as far as it can tell."""
    for f in ("/sys/class/dmi/id/sys_vendor", "/sys/class/dmi/id/product_name"):
        try:
            text = Path(f).read_text(errors="replace").lower()
        except OSError:
            continue
        if any(v in text for v in VM_VENDORS):
            return True
    if sys.platform == "darwin":
        code, out = _run(["sysctl", "-n", "kern.hv_vmm_present"], Path.cwd(), timeout=3)
        return code == 0 and out.strip() == "1"
    return any(ip.startswith(("10.211.55.", "10.37.129.", "10.0.2.", "192.168.64.")) for ip in _own_addresses())


def _private(ip: str) -> bool:
    a, b = (int(x) for x in ip.split(".")[:2])
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


def lan_candidates() -> list[str]:
    """Every address on this machine's local networks (the /24 around each of its private IPv4
    addresses, not its own) on the model servers' ports: other computers on the network. (In a VM,
    home_networks() adds the host's.)"""
    mine = _own_addresses()
    nets = list(dict.fromkeys(ip.rsplit(".", 1)[0] for ip in sorted(mine) if _private(ip)))[:SCAN_NETWORKS]
    return [f"http://{net}.{n}:{port}" for net in nets for n in range(1, 255)
            if f"{net}.{n}" not in mine for port in SCAN_PORTS]


def _port_open(url: str, timeout: float = 0.4) -> bool:
    import socket
    host, port = url.split("://", 1)[1].rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _connect(host: str, port: int, timeout: float) -> str:
    """open, refused (something is there) or none (nothing answered in time)."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "open"
    except ConnectionRefusedError:
        return "refused"
    except OSError:
        return "none"


def home_networks() -> list[str]:
    """In a VM: the usual home networks (192.168.0, 192.168.1, 10.0.0) whose router answers, the ones
    the host is probably on. Empty when this isn't a VM."""
    if not in_vm():
        return []
    mine = {ip.rsplit(".", 1)[0] for ip in _own_addresses()}
    from concurrent.futures import ThreadPoolExecutor
    def alive(net: str) -> bool:
        return any(_connect(f"{net}.1", port, 0.6) != "none" for port in (53, 80, 443, 8080))
    nets = [n for n in HOME_NETWORKS if n not in mine]
    with ThreadPoolExecutor(max_workers=len(nets) or 1) as pool:
        return [n for n, ok in zip(nets, pool.map(alive, nets)) if ok]


def _gentle_scan(nets: list[str], timeout: float) -> list[dict]:
    """Scan networks seen through a VM's address translation, which refuses every connection for a
    while after a burst: a few addresses at a time."""
    from concurrent.futures import ThreadPoolExecutor
    def host(ip: str) -> list[dict]:
        # the ports at once (a firewall may drop some silently), then probe the open ones
        with ThreadPoolExecutor(max_workers=len(SCAN_PORTS)) as ports:
            states = list(ports.map(lambda p: _connect(ip, p, 0.5), SCAN_PORTS))
        return [f for port, state in zip(SCAN_PORTS, states)
                if state == "open" and (f := probe(f"http://{ip}:{port}", timeout))]
    ips = [f"{net}.{n}" for net in nets for n in range(1, 255)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [f for found in pool.map(host, ips) for f in found]


def _scan(urls: list[str], timeout: float) -> list[dict]:
    """probe() the addresses whose port is open: a quick connection test first, so the many
    addresses with nothing on them cost a fraction of a second each, all at once."""
    from concurrent.futures import ThreadPoolExecutor
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=256) as pool:
        open_urls = [u for u, ok in zip(urls, pool.map(_port_open, urls)) if ok]
        return [f for f in pool.map(lambda u: probe(u, timeout), open_urls) if f]


def find_local(timeout: float = 1.5, candidates: list[str] | None = None, scan: bool = False) -> list[dict]:
    """Every local model server that answers, nearest first: Ollama servers (find_ollama), then
    OpenAI-compatible ones such as mlx_lm, LM Studio or llama.cpp, as probe() describes them. With
    `scan`, also every other computer on this machine's local networks (a few seconds more).
    Tries them all at once."""
    from concurrent.futures import ThreadPoolExecutor
    urls = candidates if candidates is not None else local_candidates()
    ollama_urls = [u for u in urls if u.rstrip("/").endswith(":11434")]
    other = [u for u in urls if u not in ollama_urls]
    lan = [u for u in lan_candidates() if u not in urls] if scan and candidates is None else []
    with ThreadPoolExecutor(max_workers=2) as pool:
        ollama_job = pool.submit(find_ollama, timeout, ollama_urls if candidates is not None else None)
        with ThreadPoolExecutor(max_workers=max(1, min(128, len(other) + len(lan)))) as inner:
            near_jobs = [inner.submit(probe, u, timeout) for u in other]
            found_other = [f for j in near_jobs if (f := j.result())]
        found_lan = _scan(lan, timeout)
        if scan and candidates is None:
            found_lan += _gentle_scan(home_networks(), timeout)
        ollama = [{"url": u.rstrip("/"), "kind": "ollama", "label": "Ollama", "models": m} for u, m in ollama_job.result()]
    seen, out = set(), []
    for f in ollama + found_other + found_lan:
        if f["url"] not in seen:
            seen.add(f["url"])
            out.append(f)
    return out


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
    if team and "rea" not in team.mcp:   # behaviour checks are optional: offer them
        from . import rea
        command, _, where = rea.find()
        out.append(Check("REA (behaviour checks)", bool(command),
                         f"installed ({where}), not used by this team yet" if command else "not installed",
                         "agent-team rea setup", "behaviour checks", optional=True))
    if team and team.sandbox.mode == "container":
        from . import sandbox
        ok, detail = sandbox.ready(team)
        out.append(Check("test sandbox", ok, detail,
                         "" if ok else "install or start Docker (or Podman), or set [sandbox].mode = \"off\""))

    # Paths members own, spelled differently from the folder (tests/ for Tests/): their writes there
    # would be refused on a case-sensitive disk, and sign-offs wouldn't match.
    if team:
        for a in team.agents.values():
            for owned in a.owns:
                top = owned.split("/")[0]
                names = {p.name for p in Path(team.root).iterdir()}
                if not top or top == "*" or top in names:
                    continue
                real = next((n for n in sorted(names) if n.lower() == top.lower()), "")
                if real:
                    fixed = real + owned[len(top):]
                    out.append(Check(f"{a.name} owns {owned}", False, f"the folder is {real}/, so {owned} matches nothing",
                                     f'in .team.toml, {a.name}\'s owns: "{fixed}" (or the dashboard: Team → Edit team)'))

    # Ollama: every server a member uses, and whether its models are pulled.
    servers: dict[str, list[str]] = {}
    if team:
        for a in team.agents.values():
            p = team.providers[a.provider]
            if p.kind == "ollama":
                servers.setdefault((p.url or "http://localhost:11434").rstrip("/"), []).append(a.model)
    given = probe(ollama_url, timeout=3) if ollama_url else None
    if ollama_url and (not given or given["kind"] == "ollama"):   # a server being considered (init)
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
    # OpenAI-compatible servers on this network (mlx_lm, LM Studio...): reachable, and serving the model.
    openai_servers: dict[str, list[str]] = {}
    if team:
        for a in team.agents.values():
            p = team.providers[a.provider]
            if p.kind == "openai" and p.url and not p.api_key_env:   # hosted gateways need their key: doctor checks them
                openai_servers.setdefault(p.url.rstrip("/"), []).append(a.model)
    if given and given["kind"] == "openai":
        openai_servers.setdefault(given["url"], [])
    for url, models in openai_servers.items():
        have, server = openai_models(url)
        if have is None:
            fix = ("start it (mlx_lm: mlx_lm.server --model MODEL); on another machine it must listen on the network "
                   "(mlx_lm.server --host 0.0.0.0) with its port open")
            out.append(Check(f"model server at {url}", False, "not reachable", fix))
            continue
        out.append(Check(f"model server at {url}", True, f"{server_label(url, have, server)}, {len(have)} models"))
        for m in dict.fromkeys(models):
            listed = not have or m in have
            out.append(Check(f"model {m}", listed, "served" if listed else f"not served at {url}",
                             "" if listed else f"start the server with this model (mlx_lm.server --model {m})"))
    return out


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]
