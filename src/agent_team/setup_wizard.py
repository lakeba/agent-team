"""The first-run wizard behind the dashboard: from an idea to a team at work, with no terminal.

The dashboard calls these functions from its /api/setup/* endpoints. Each step writes exactly what
the command line would (`init` writes .team.toml, `keys set` the keys file, `templates apply` the
library pieces), so a project set up here is the same as one set up in a terminal.

    status()            what this machine has: projects, git, GitHub, Claude key, Ollama and its models
    create_project()    a folder for the idea, git, VISION.md, README.md, .team.toml, the template, a first commit
    save_key()          the Anthropic key into agent-team's keys file, checked at once
    pull_model()        an Ollama model, pulled in the background with progress
    github_login()      `gh auth login --web`, its one-time code shown in the page
    create_repo()       a private GitHub repository for the project, pushed
    ready()             the readiness checklist, with the fixes the page can do itself
    suggest_tasks()     the lead reads the vision and proposes the first tasks
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

HOME_ENV = "LAKEBA_OS_HOME"
KEY_NAME = "ANTHROPIC_API_KEY"
TASK_RE = re.compile(r"^\s*(?:[-*\d.)]+\s*)?TASK:\s*(.+?)\s*$", re.M)


class SetupError(ValueError):
    pass


def home() -> Path:
    """Where new projects go: ~/LakebaOS unless LAKEBA_OS_HOME says otherwise."""
    return Path(os.environ.get(HOME_ENV) or Path.home() / "LakebaOS").expanduser()


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40].strip("-") or "my-idea"


def _run(argv: list[str], cwd: Path | None = None, timeout: int = 60, stdin: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, input=stdin)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def git_identity(root: Path | None = None) -> tuple[str, str]:
    where = ["-C", str(root)] if root else []
    name = _run(["git", *where, "config", "user.name"])[1] if shutil.which("git") else ""
    email = _run(["git", *where, "config", "user.email"])[1] if shutil.which("git") else ""
    return (name if "\n" not in name else ""), (email if "\n" not in email else "")


def github_status() -> dict:
    if not shutil.which("gh"):
        return {"installed": False, "signed_in": False, "user": ""}
    code, out = _run(["gh", "auth", "status", "--hostname", "github.com"], timeout=20)
    m = re.search(r"account (\S+)", out) or re.search(r"as (\S+)", out)
    return {"installed": True, "signed_in": code == 0, "user": m.group(1) if m and code == 0 else ""}


def claude_key_set() -> bool:
    from . import keys
    keys.load_into_env()
    return bool(os.environ.get(KEY_NAME))


def _project_name(root: str) -> str:
    import tomllib
    try:
        return tomllib.loads((Path(root) / ".team.toml").read_text(encoding="utf-8"))["project"]["name"]
    except Exception:
        return Path(root).name


def status() -> dict:
    """What the wizard needs to know about this machine, in one call."""
    from . import composition, projects
    from .readiness import find_ollama
    servers = [{"url": u, "models": m} for u, m in find_ollama()]
    name, email = git_identity()
    return {
        "first_run": not projects.registered(),
        "projects": [{"root": p, "name": _project_name(p)} for p in projects.registered() if Path(p).is_dir()],
        "home": str(home()),
        "git": bool(shutil.which("git")), "git_name": name, "git_email": email,
        "github": github_status(),
        "claude_key": claude_key_set(),
        "ollama": servers,
        "recommended_model": composition.DEFAULT_MODEL,
        "extras": {r: {"name": n, "about": a} for r, (n, a) in composition.EXTRAS.items()},
        "max_builders": composition.MAX_BUILDERS,
    }


# ---------------------------------------------------------------------------------------------
# Creating the project

def _text(form: dict, key: str, limit: int, required: bool = False) -> str:
    v = form.get(key, "")
    if not isinstance(v, str):
        raise SetupError(f"{key} must be text")
    v = v.strip()
    if required and not v:
        raise SetupError(f"{key} is required")
    if len(v) > limit:
        raise SetupError(f"{key} is too long ({len(v)} characters, at most {limit})")
    return v


def folder_info(folder: Path | None) -> dict:
    """The folder the dashboard was started in, for the wizard to offer: can it become a project
    (not the home folder or /, no team yet), what's in it, and its VISION.md if it has one."""
    if folder is None:
        return {}
    from . import packs
    path = Path(folder).expanduser().resolve()
    usable = (path.is_dir() and path not in (Path.home().resolve(), Path("/"))
              and not (path / ".team.toml").exists())
    files = [p for p in path.iterdir() if p.name not in (".DS_Store", ".git")] if path.is_dir() else []
    vision = path / "VISION.md"
    return {"path": str(path), "name": path.name, "usable": usable, "has_files": bool(files),
            "git": (path / ".git").exists(),
            "language": packs.detect(path).name if usable else "",
            "language_label": packs.detect(path).about.split(":")[0] if usable and files else "",
            "vision": vision.read_text(encoding="utf-8", errors="replace")[:20_000] if vision.is_file() else ""}


def create_project(form: dict) -> dict:
    """A project for an idea: its folder, git, VISION.md, README.md, .team.toml (as `init` writes it),
    the template for its language, and a first commit. Returns {"root", "notes"}.

    With `existing`, the project is the folder given, which may already hold code: nothing in it is
    changed or removed; agent-team adds its own files (and VISION.md and README.md when missing) and
    commits only those."""
    from . import composition, packs, projects
    from .config import load
    from .workflows import init
    name = _text(form, "name", 80, required=True)
    vision = _text(form, "vision", 20_000, required=True)
    owner = _text(form, "owner", 80)
    models = _text(form, "models", 10) or "mixed"
    if models not in composition.MODELS:
        raise SetupError(f"models is one of {', '.join(composition.MODELS)}")
    extras = form.get("extras") or []
    if not isinstance(extras, list) or any(e not in composition.EXTRAS for e in extras):
        raise SetupError(f"optional members are {', '.join(composition.EXTRAS)}")
    builders = form.get("builders", 1)
    if not isinstance(builders, int) or isinstance(builders, bool) or not 1 <= builders <= composition.MAX_BUILDERS:
        raise SetupError(f"builders is 1 to {composition.MAX_BUILDERS}")
    per_day = form.get("per_day", 0)
    if not isinstance(per_day, (int, float)) or isinstance(per_day, bool) or not 0 <= per_day <= 1000:
        raise SetupError("the daily limit is US dollars from 0 to 1000")
    ollama_url = _text(form, "ollama_url", 200)
    if ollama_url and not re.match(r"^https?://[\w.\-\[\]:]+/?$", ollama_url):
        raise SetupError("the Ollama address looks like http://localhost:11434")
    ollama_model = _text(form, "ollama_model", 120)
    if not shutil.which("git"):
        raise SetupError("git isn't installed on this computer; install it (macOS: xcode-select --install) and try again")
    folder = _text(form, "folder", 500)
    existing = bool(form.get("existing"))
    root = Path(folder).expanduser() if folder else home() / slug(name)
    if existing:
        info = folder_info(root)
        if not folder or not info.get("usable"):
            raise SetupError(f"{root} can't be set up here (it's missing, your home folder, or already has a team)")
    elif root.exists() and any(p.name != ".DS_Store" for p in root.iterdir()):
        raise SetupError(f"{root} already has files in it; choose another name or folder")
    created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    added_readme = added_vision = False
    notes = []
    try:
        if not (root / ".git").exists() and _run(["git", "init", "-q", "-b", "main"], root)[0] != 0:
            _run(["git", "init", "-q"], root)
        g_name, g_email = git_identity(root)
        if not g_name or not g_email:   # commits need an identity; keep it to this project
            _run(["git", "config", "user.name", owner or g_name or "Lakeba OS builder"], root)
            _run(["git", "config", "user.email", g_email or "builder@lakeba-os.local"], root)
            notes.append("set a git identity for this project only")
        first = next((l.strip() for l in vision.splitlines() if l.strip() and not l.startswith("#")), name)
        if not (root / "README.md").exists():
            (root / "README.md").write_text(f"# {name}\n\n{first}\n", encoding="utf-8")
            added_readme = True
        vision_file = root / "VISION.md"
        plain = lambda t: re.sub(r"^#\s*Vision\s*\n+", "", t.strip(), flags=re.I).strip()
        if vision_file.exists() and plain(vision_file.read_text(encoding="utf-8", errors="replace")) != plain(vision):
            body = vision if vision.lstrip().startswith("#") else f"# Vision\n\n{vision}"
            vision_file.write_text(body.rstrip() + "\n", encoding="utf-8")   # edited in the wizard
            added_vision = True
        added_vision = added_vision or not vision_file.exists()
        try:
            init.run(root, ollama_url=ollama_url, builder_model=ollama_model, models=models,
                     extras=tuple(extras), builders=builders, per_day=float(per_day) or None,
                     vision=vision, use_rea=False)
        except SystemExit as e:
            raise SetupError(str(e)) from None
        cfg = root / ".team.toml"
        from .config_io import _str
        cfg.write_text(re.sub(r'(?m)^name = ".*"$', f"name = {_str(name)}", cfg.read_text(encoding="utf-8"), count=1),
                       encoding="utf-8")
        team = load(root)
        packs.apply(team, packs.detect(root), yes=True)
        if existing:   # only what agent-team added: the code stays as the owner left it
            ours = [".team.toml", ".gitignore", "team"] + (["README.md"] if added_readme else []) + \
                   (["VISION.md"] if added_vision else [])
            _run(["git", "add", "--", *[p for p in ours if (root / p).exists()]], root)
        else:
            _run(["git", "add", "-A"], root)
        code, out = _run(["git", "commit", "-q", "-m", f"Start {name}" if not existing else f"Add the agent-team for {name}"], root)
        if code != 0:
            notes.append(f"the first commit didn't work: {out[-200:]}")
    except Exception:
        if created and not (root / ".team.toml").exists():
            shutil.rmtree(root, ignore_errors=True)   # nothing half-made left behind (never a folder we didn't make)
        raise
    projects.register(root)
    return {"root": str(root.resolve()), "notes": notes}


# ---------------------------------------------------------------------------------------------
# Keys, models, GitHub

def save_key(value: str) -> dict:
    """Save the Anthropic key in agent-team's keys file (owner-only), put it in this process's
    environment, and check it. The value is never returned."""
    from . import keys, providers
    from .config import ProviderConfig
    value = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,300}", value):
        raise SetupError("that doesn't look like an API key; copy it again from console.anthropic.com")
    keys.set_key(KEY_NAME, value)
    os.environ[KEY_NAME] = value
    try:
        result = providers.build(ProviderConfig(name="claude", kind="anthropic", api_key_env=KEY_NAME), value) \
            .check("claude-sonnet-5-5")
    except Exception as e:
        result = f"FAILED: {type(e).__name__}: {e}"
    return {"saved": True, "ok": not result.startswith("FAILED"), "status": result}


PULLS: dict[str, dict] = {}
_lock = threading.Lock()


def pull_model(url: str, model: str) -> dict:
    """Start pulling `model` on the Ollama server at `url` (in the background); see pull_status."""
    from .readiness import is_local
    if not re.match(r"^https?://", url or "") or not re.fullmatch(r"[\w.:/\-]{1,120}", model or ""):
        raise SetupError("give the Ollama address and a model name")
    if not is_local(url):
        raise SetupError("models can only be pulled from here on Ollama on this computer; "
                         f"on the other machine run: ollama pull {model}")
    key = f"{url.rstrip('/')}|{model}"
    with _lock:
        if PULLS.get(key, {}).get("state") == "pulling":
            return PULLS[key]
        PULLS[key] = {"state": "pulling", "status": "starting", "completed": 0, "total": 0, "error": ""}

    def work():
        p = PULLS[key]
        try:
            req = urllib.request.Request(f"{url.rstrip('/')}/api/pull", data=json.dumps({"model": model}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3600) as r:
                for line in r:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if msg.get("error"):
                        raise RuntimeError(msg["error"])
                    p["status"] = msg.get("status", p["status"])
                    if msg.get("total"):
                        p["total"], p["completed"] = msg["total"], msg.get("completed", 0)
            p["state"] = "done"
        except Exception as e:
            p["state"], p["error"] = "failed", str(e)[:300]
    threading.Thread(target=work, daemon=True).start()
    return PULLS[key]


def pull_status(url: str, model: str) -> dict:
    return PULLS.get(f"{(url or '').rstrip('/')}|{model}", {"state": "none"})


LOGIN: dict = {"state": "none"}


def github_login() -> dict:
    """Start `gh auth login --web`: GitHub's own page signs the person in; this shows the code."""
    if not shutil.which("gh"):
        raise SetupError("the GitHub CLI isn't installed; get it from https://cli.github.com (or skip this step)")
    if LOGIN.get("state") == "waiting":
        return LOGIN
    LOGIN.clear()
    LOGIN.update({"state": "starting", "code": "", "url": "https://github.com/login/device", "output": ""})
    env = {**os.environ, "GH_PROMPT_DISABLED": "", "BROWSER": "true"}   # we open the page ourselves

    def work():
        try:
            proc = subprocess.Popen(["gh", "auth", "login", "--web", "--hostname", "github.com", "--git-protocol", "https"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, env=env)
            try:
                proc.stdin.write("\n\n")
                proc.stdin.flush()
            except OSError:
                pass
            for line in proc.stdout:
                LOGIN["output"] = (LOGIN["output"] + line)[-2000:]
                m = re.search(r"code\b.*?\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", line, re.I)
                if m:
                    LOGIN.update({"code": m.group(1), "state": "waiting"})
            proc.wait(timeout=900)
            LOGIN["state"] = "done" if proc.returncode == 0 else "failed"
        except Exception as e:
            LOGIN.update({"state": "failed", "output": str(e)})
    threading.Thread(target=work, daemon=True).start()
    return LOGIN


def create_repo(root: Path, private: bool = True) -> dict:
    """A GitHub repository for the project (private unless asked), with the code pushed."""
    from .workflows.init import github_repo
    root = Path(root)
    if github_repo(root):
        return {"repo": github_repo(root), "created": False}
    gh = github_status()
    if not gh["signed_in"]:
        raise SetupError("sign in to GitHub first")
    code, out = _run(["gh", "repo", "create", root.name, "--private" if private else "--public",
                      "--source", str(root), "--remote", "origin", "--push"], root, timeout=180)
    if code != 0:
        raise SetupError(f"GitHub didn't create the repository: {out[-300:]}")
    return {"repo": github_repo(root), "created": True}


# ---------------------------------------------------------------------------------------------
# Ready check and the first tasks

OPTIONAL_HERE = {"GitHub CLI": "Optional: connect GitHub to keep your code online (the GitHub step).",
                 "GitHub repo": "Optional: connect GitHub to keep your code online (the GitHub step).",
                 "REA (behaviour checks)": "Optional: behaviour checks use the app like a user would. Set up later."}


def ready(root: Path) -> list[dict]:
    """The readiness checklist for the wizard: each check once, GitHub and behaviour checks
    optional, and `action` set where the page can fix it itself."""
    from . import readiness
    out, seen = [], set()
    for c in readiness.as_dicts(readiness.check(Path(root))):
        name, action = c["name"], ""
        if name in seen:
            continue
        seen.add(name)
        short = name.split(":")[0]
        if short in OPTIONAL_HERE and not c["ok"]:
            c = {**c, "optional": True, "fix": "", "detail": f"{c['detail']}. {OPTIONAL_HERE[short]}"}
        if not c["ok"]:
            if name.startswith(f"key {KEY_NAME}"):
                action = "key"
            elif name.startswith("model ") and "on that machine" not in (c.get("fix") or ""):
                action = "pull:" + name.removeprefix("model ")
            elif name.startswith("git identity"):
                action = "identity"
            elif name.startswith(("GitHub CLI", "GitHub repo")):
                action = "github"
        out.append({**c, "action": action})
    return out


SUGGEST = """Read the product vision below and propose the first {n} tasks that would make a small working
first version (an MVP) of it. Each task is something a builder can finish in one go, described in
one sentence a non-programmer understands, in the order to build them. Reply with only lines like:
TASK: <the task>

# The vision

{vision}"""


def suggest_tasks(root: Path, n: int = 4) -> list[str]:
    from . import agent
    from .config import load
    team = load(root)
    vision_path = Path(root) / "VISION.md"
    vision = vision_path.read_text(encoding="utf-8") if vision_path.exists() else ""
    if not vision.strip():
        raise SetupError("the project has no VISION.md to plan from")
    lead = agent.make(team, team.by_role("lead"), "member", label_suffix=" · first tasks")
    reply = lead.turn(SUGGEST.format(n=n, vision=vision[:12_000]))
    tasks = [t.strip().strip("`") for t in TASK_RE.findall(reply)][:6]
    if not tasks:
        raise SetupError("the lead didn't propose tasks; write your own below")
    return tasks
