"""Run my app: start the project the team built, so its owner can see it working.

How to run it comes from `[project].run_command` when set, else from the project itself:

    package.json with a dev or start script     npm run dev / npm start (npm install first if needed)
    manage.py                                   python manage.py runserver
    app.py or main.py using Flask, FastAPI...   flask run / uvicorn / streamlit run / python
    a Python package (pyproject.toml)           a command-line tool: run with the arguments typed in the page
    index.html                                  served on this computer and opened in the browser
    *.csproj, go.mod, Cargo.toml                dotnet run / go run . / cargo run

A web app runs in the background (its output in .team/app.log, its address found there) until it's
stopped; a command-line tool runs once with the given arguments and shows its output.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1?\])(?::\d+)?[^\s\"'<>]*")
STATE = "app.json"
LOG = "app.log"


class RunError(ValueError):
    pass


def _team_dir(root: Path) -> Path:
    d = Path(root) / ".team"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _python_module(root: Path) -> str:
    """The importable package of a Python project, if it has one with a __main__ or cli module."""
    for base in (root / "src", root):
        if not base.is_dir():
            continue
        for pkg in sorted(base.iterdir()):
            if pkg.is_dir() and (pkg / "__init__.py").exists() and not pkg.name.startswith(("test", "_", ".")):
                if (pkg / "__main__.py").exists():
                    return pkg.name
                if (pkg / "cli.py").exists():
                    return f"{pkg.name}.cli"
    return ""


def _python_script(root: Path) -> str:
    """A Python file meant to be run (it has `if __name__ == "__main__":`), outside the tests."""
    candidates = sorted(list(root.glob("*.py")) + list(root.glob("src/*.py")) + list(root.glob("src/*/*.py")),
                        key=lambda p: (p.stem not in ("main", "cli", "app", "__main__"), len(p.parts), p.name))
    for p in candidates:
        if p.name.startswith("test") or p.name == "conftest.py":
            continue
        try:
            if re.search(r"^if __name__ == [\"']__main__[\"']:", p.read_text(encoding="utf-8", errors="replace"), re.M):
                return p.relative_to(root).as_posix()
        except OSError:
            continue
    return ""


def detect(root: Path, configured: str = "") -> dict:
    """{kind: web|cli|static|none, command, why}: how this project runs."""
    root = Path(root)
    venv = next((v for v in (root / ".venv" / "bin" / "python", root / "venv" / "bin" / "python") if v.exists()), None)
    py = shlex.quote(str(venv) if venv else sys.executable)   # the project's own environment when it has one
    if configured:
        return {"kind": "web", "command": configured, "why": "[project].run_command"}
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except ValueError:
            scripts = {}
        for name in ("dev", "start", "preview"):
            if name in scripts:
                install = "" if (root / "node_modules").is_dir() else "npm install && "
                return {"kind": "web", "command": f"{install}npm run {name}", "why": f"package.json's {name} script"}
    if (root / "manage.py").is_file():
        return {"kind": "web", "command": f"{py} manage.py runserver", "why": "a Django project"}
    for name in ("app.py", "main.py", "streamlit_app.py"):
        f = root / name
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="replace")
            mod = f.stem
            if "streamlit" in text:
                return {"kind": "web", "command": f"{py} -m streamlit run {name}", "why": f"{name} uses Streamlit"}
            if "FastAPI(" in text:
                return {"kind": "web", "command": f"{py} -m uvicorn {mod}:app", "why": f"{name} is a FastAPI app"}
            if "Flask(" in text:
                return {"kind": "web", "command": f"{py} -m flask --app {mod} run", "why": f"{name} is a Flask app"}
            return {"kind": "cli", "command": f"{py} {name}", "why": f"{name}"}
    web = _web_package(root)
    if web:
        prepare = ("" if venv or not (root / "requirements.txt").is_file() else
                   "python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt && ")
        run_py = ".venv/bin/python" if prepare else py
        kind, module, why = web
        command = (f"{run_py} -m flask --app {module} run" if kind == "flask" else f"{run_py} -m uvicorn {module}:app")
        return {"kind": "web", "command": prepare + command, "why": why}
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        mod = _python_module(root)
        if mod:
            env = "PYTHONPATH=src " if (root / "src").is_dir() else ""
            return {"kind": "cli", "command": f"{env}{py} -m {mod}", "why": f"the Python package {mod.split('.')[0]}"}
    script = _python_script(root)
    if script:
        path = Path(script)
        if (root / path.parent / "__init__.py").exists():   # inside a package: run it as a module
            module = ".".join(path.with_suffix("").parts)
            return {"kind": "cli", "command": f"{py} -m {module}", "why": f"{script} (it has a main entry point)"}
        return {"kind": "cli", "command": f"{py} {shlex.quote(script)}", "why": f"{script} (it has a main entry point)"}
    if any(root.glob("*.csproj")) or any(root.glob("src/*/*.csproj")):
        return {"kind": "web" if any("Web" in p.read_text(errors="replace") for p in root.rglob("*.csproj")) else "cli",
                "command": "dotnet run" if any(root.glob("*.csproj")) else f"dotnet run --project {next(root.glob('src/*/*.csproj')).parent}",
                "why": "a .NET project"}
    if (root / "go.mod").is_file():
        return {"kind": "cli", "command": "go run .", "why": "a Go module"}
    if (root / "Cargo.toml").is_file():
        return {"kind": "cli", "command": "cargo run --quiet --", "why": "a Rust crate"}
    for page in ("index.html", "public/index.html", "site/index.html", "dist/index.html"):
        if (root / page).is_file():
            return {"kind": "static", "command": str(Path(page).parent), "why": page}
    return {"kind": "none", "command": "",
            "why": "There’s nothing to run yet. Once the team has built something you can use, it starts from here. "
                   "(Developers: [project].run_command says how to start it.)"}


def _state(root: Path) -> dict:
    try:
        return json.loads((_team_dir(root) / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def status(root: Path) -> dict:
    s = _state(root)
    running = bool(s.get("pid")) and _alive(s["pid"])
    log = _team_dir(root) / LOG
    text = log.read_text(encoding="utf-8", errors="replace")[-6000:] if log.exists() else ""
    url = s.get("url") or next(iter(URL_RE.findall(text)), "")
    url = url.replace("0.0.0.0", "127.0.0.1")
    return {"running": running, "url": url if running else "", "command": s.get("command", ""), "output": text}


def start(root: Path, configured: str = "") -> dict:
    """Start the web app (or serve the static page) in the background."""
    root = Path(root)
    if status(root)["running"]:
        return status(root)
    how = detect(root, configured)
    if how["kind"] == "none":
        raise RunError(how["why"])
    if how["kind"] == "cli":
        raise RunError("this is a command-line tool: run it with arguments instead")
    url = ""
    if how["kind"] == "static":
        port = _free_port()
        argv = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(root / how["command"])]
        url, command = f"http://127.0.0.1:{port}/", f"serve {how['command'] or '.'}/"
    else:
        argv, command = ["/bin/sh", "-c", how["command"]], how["command"]
    log = open(_team_dir(root) / LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    (_team_dir(root) / STATE).write_text(json.dumps({"pid": proc.pid, "command": command, "url": url}), encoding="utf-8")
    for _ in range(30):   # give it a moment to print its address
        time.sleep(0.5)
        s = status(root)
        if s["url"] or not s["running"]:
            break
    return status(root)


def stop(root: Path) -> dict:
    s = _state(root)
    if s.get("pid") and _alive(s["pid"]):
        try:
            os.killpg(s["pid"], signal.SIGTERM)
        except OSError:
            pass
    (_team_dir(root) / STATE).write_text(json.dumps({}), encoding="utf-8")
    return status(root)


def run_cli(root: Path, args: str, configured: str = "", timeout: int = 60) -> dict:
    """Run a command-line tool once with `args` (as typed) and return its output."""
    how = detect(root, configured)
    if how["kind"] != "cli":
        raise RunError("this project isn't a command-line tool")
    if len(args) > 500:
        raise RunError("the arguments are too long")
    try:
        argv = shlex.split(args)
    except ValueError as e:
        raise RunError(f"the arguments don't parse: {e}") from None
    command = f"{how['command']} {' '.join(shlex.quote(a) for a in argv)}".strip()
    try:
        r = subprocess.run(["/bin/sh", "-c", command], cwd=root, capture_output=True, text=True, timeout=timeout)
        return {"command": command, "exit_code": r.returncode, "output": (r.stdout + r.stderr)[-8000:]}
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": None, "output": f"(still running after {timeout} seconds; stopped)"}


def _web_package(root: Path) -> tuple[str, str, str] | None:
    """("flask"|"fastapi", the module to run, why) for a web app that lives in a package rather than a
    top-level file: a Flask app or factory in <pkg>/__init__.py (`flask --app <pkg>` finds create_app),
    or `app = FastAPI(...)` in <pkg>/main.py, app.py or __init__.py."""
    skip = {"tests", "test", ".venv", "venv", "node_modules", "build", "dist", "docs", "team"}
    for pkg in sorted(d for d in root.iterdir() if d.is_dir() and d.name not in skip and not d.name.startswith(".")):
        init = pkg / "__init__.py"
        if not init.is_file():
            continue
        text = init.read_text(encoding="utf-8", errors="replace")
        if "Flask(" in text or ("def create_app" in text and "flask" in text.lower()):
            return "flask", pkg.name, f"the Flask app in {pkg.name}/"
        for name in ("main.py", "app.py", "__init__.py"):
            f = pkg / name
            if f.is_file() and re.search(r"(?m)^app\s*=\s*FastAPI\(", f.read_text(encoding="utf-8", errors="replace")):
                module = pkg.name if name == "__init__.py" else f"{pkg.name}.{f.stem}"
                return "fastapi", module, f"the FastAPI app in {pkg.name}/{name}"
    return None
