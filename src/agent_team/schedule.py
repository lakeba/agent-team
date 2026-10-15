"""Scheduled shifts: run a workflow (normally `ship`) every so often, never two at once.

`agent-team ship --every 6h` keeps a shift loop running in the foreground. `agent-team schedule`
installs the same thing with the system's own scheduler, so it survives logouts and restarts:
a launchd agent on macOS, a crontab line elsewhere. Every run takes a lock in `.team/`, so a
shift that is still going when the next one is due makes the next one skip.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import plistlib
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from . import ui

DURATION_RE = re.compile(r"^(\d+)\s*([mhd])$")
CRON_MARK = "# agent-team schedule:"


class AlreadyRunning(RuntimeError):
    pass


def parse_every(text: str) -> int:
    """'30m', '6h' or '1d' -> seconds (at least 5 minutes)."""
    m = DURATION_RE.match(text.strip().lower())
    if not m:
        raise ValueError(f"use a duration like 30m, 6h or 1d, not {text!r}")
    seconds = int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
    if seconds < 300:
        raise ValueError("the shortest interval is 5m")
    return seconds


@contextlib.contextmanager
def lock(root: Path, name: str):
    """Hold `.team/<name>.lock` for the duration, or raise AlreadyRunning if another process does."""
    folder = Path(root) / ".team"
    folder.mkdir(parents=True, exist_ok=True)
    f = open(folder / f"{name}.lock", "a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            holder = f.read().strip() or "another process"
            raise AlreadyRunning(f"a {name} run is already in progress ({holder})") from None
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()} since {time.strftime('%Y-%m-%d %H:%M:%S')}")
        f.flush()
        yield
    finally:
        with contextlib.suppress(OSError):
            f.seek(0)
            f.truncate()
        f.close()   # closing releases the lock


def loop(every: int, once) -> None:
    """Call `once()` now and then every `every` seconds; a failed run is reported, not fatal."""
    while True:
        started = time.time()
        try:
            once()
        except AlreadyRunning as e:
            ui.warn(f"skipped: {e}")
        except SystemExit as e:
            if e.code not in (0, None):
                ui.warn(f"run stopped: {e}")
        except Exception as e:   # keep the schedule alive; the next run may succeed
            ui.warn(f"run failed: {type(e).__name__}: {e}")
        wait = max(60, every - (time.time() - started))
        ui.say(f"\nNext run in {int(wait // 60)} minutes (Ctrl-C to stop).")
        time.sleep(wait)


# ---------- installing with the system scheduler ----------

def _label(root: Path, workflow: str) -> str:
    digest = hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9]+", "-", Path(root).resolve().name.lower()).strip("-") or "project"
    return f"dev.agent-team.{slug}-{digest}.{workflow}"


def command(root: Path, workflow: str, extra: list[str] | None = None) -> list[str]:
    """The command a scheduler runs: this Python's agent-team, through the login shell so the API
    keys set in the person's shell profile are there, as they are in a terminal."""
    inner = " ".join(shlex.quote(a) for a in [sys.executable, "-m", "agent_team.cli", workflow, "-C",
                                              str(Path(root).resolve()), *(extra or [])])
    return [os.environ.get("SHELL") or "/bin/zsh", "-ic", f"exec {inner}"]


def launchd_plist(root: Path, workflow: str, every: int, extra: list[str] | None = None) -> bytes:
    log = str(Path(root).resolve() / ".team" / "schedule.log")
    return plistlib.dumps({
        "Label": _label(root, workflow), "ProgramArguments": command(root, workflow, extra),
        "StartInterval": every, "RunAtLoad": False, "WorkingDirectory": str(Path(root).resolve()),
        "StandardOutPath": log, "StandardErrorPath": log, "ProcessType": "Background",
    })


def cron_line(root: Path, workflow: str, every: int, extra: list[str] | None = None) -> str:
    minutes = every // 60
    if minutes < 60:
        when = f"*/{minutes} * * * *"
    elif minutes % 1440 == 0:
        when = f"0 3 */{minutes // 1440} * *" if minutes > 1440 else "0 3 * * *"
    else:
        when = f"0 */{max(1, minutes // 60)} * * *"
    log = shlex.quote(str(Path(root).resolve() / ".team" / "schedule.log"))
    cmd = " ".join(shlex.quote(a) for a in command(root, workflow, extra))
    return f"{when} {cmd} >> {log} 2>&1 {CRON_MARK} {_label(root, workflow)}"


def _plist_path(root: Path, workflow: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_label(root, workflow)}.plist"


def _crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def _write_crontab(lines: list[str]) -> None:
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)


def install(root: Path, workflow: str, every: int, extra: list[str] | None = None) -> str:
    (Path(root) / ".team").mkdir(exist_ok=True)
    if sys.platform == "darwin":
        path = _plist_path(root, workflow)
        path.parent.mkdir(parents=True, exist_ok=True)
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(path)], capture_output=True)
        path.write_bytes(launchd_plist(root, workflow, every, extra))
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True, capture_output=True)
        return f"launchd agent {path}"
    label = _label(root, workflow)
    lines = [l for l in _crontab() if not l.endswith(f"{CRON_MARK} {label}")]
    _write_crontab(lines + [cron_line(root, workflow, every, extra)])
    return "a line in your crontab"


def remove(root: Path, workflow: str) -> bool:
    if sys.platform == "darwin":
        path = _plist_path(root, workflow)
        if not path.exists():
            return False
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)], capture_output=True)
        path.unlink()
        return True
    label = _label(root, workflow)
    lines = _crontab()
    kept = [l for l in lines if not l.endswith(f"{CRON_MARK} {label}")]
    if len(kept) == len(lines):
        return False
    _write_crontab(kept)
    return True


def show(root: Path, workflow: str = "ship") -> dict | None:
    """The installed schedule for this project, if any: {"every": seconds, "where": ...}."""
    if sys.platform == "darwin":
        path = _plist_path(root, workflow)
        if not path.exists():
            return None
        data = plistlib.loads(path.read_bytes())
        return {"workflow": workflow, "every": data.get("StartInterval"), "where": str(path)}
    label = _label(root, workflow)
    for l in _crontab():
        if l.endswith(f"{CRON_MARK} {label}"):
            return {"workflow": workflow, "every": None, "where": "crontab", "line": l}
    return None
