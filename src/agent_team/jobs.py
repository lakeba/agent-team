"""Runs started from the dashboard or the Claude panel, in the background.

A job is one CLI workflow run (`agent-team build ...`) in its own process, detached from whatever
started it, so closing the dashboard doesn't stop it. Each job keeps two files in `.team/jobs/`:
`<id>.json` (what, when, process id, exit code) and `<id>.log` (its output). The same spend
limits and shift lock apply as in a terminal. Only one job that changes files runs at a time.

    python -m agent_team.jobs <project> <id>     # internal: runs a job and records its exit code
"""
from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ID_RE = re.compile(r"^[a-z]+-\d{8}T\d{6}-[0-9a-f]{6}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
WRITERS = {"build", "discuss", "market", "setup", "fix", "autopilot"}       # change files in the working tree
SKIPPABLE = ("qa", "security", "docs")


class JobError(ValueError):
    pass


def _dir(root: Path) -> Path:
    d = Path(root) / ".team" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def argv_for(workflow: str, params: dict) -> list[str]:
    """The CLI arguments for a run, from untrusted form input: only known options, checked types."""
    p = params or {}

    def text(key: str, required: bool = False, limit: int = 2000) -> str:
        v = p.get(key, "")
        if not isinstance(v, str):
            raise JobError(f"{key} must be text")
        v = v.strip()
        if required and not v:
            raise JobError(f"{key} is required")
        if len(v) > limit:
            raise JobError(f"{key} is too long")
        return v

    def number(key: str, default: int, lo: int, hi: int) -> str:
        v = p.get(key, default)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise JobError(f"{key} must be a whole number from {lo} to {hi}")
        return str(v)

    if workflow == "doctor":
        return ["doctor"]
    if workflow == "ship":
        argv = ["ship", "--max-steps", number("max_steps", 30, 1, 100)]
        release = p.get("release", "")
        if release:
            if not isinstance(release, str) or not re.fullmatch(r"\d+\.\d+\.\d+", release):
                raise JobError("release must look like 1.2.3")
            argv += ["--release", release]
        return argv
    if workflow == "market":
        return ["market", "--rounds", number("rounds", 3, 1, 10)]
    if workflow == "discuss":
        return ["discuss", text("topic", required=True), "--turns", number("turns", 12, 2, 40)]
    if workflow == "autopilot":
        argv = ["autopilot", "--max-cycles", number("max_cycles", 6, 1, 30)]
        milestone = text("milestone", limit=40)
        if milestone:
            if not re.fullmatch(r"[A-Za-z0-9 ._-]+", milestone):
                raise JobError("milestone may contain letters, digits, spaces, . _ and -")
            argv += ["--milestone", milestone]
        return argv
    if workflow == "fix":
        n = p.get("number")
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise JobError("number must be the pull request number")
        return ["fix", str(n), "--rounds", number("rounds", 2, 1, 5)]
    if workflow == "build":
        argv = ["build", text("task", required=True), "--rounds", number("rounds", 3, 1, 10)]
        branch = text("branch", limit=100)
        if branch:
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch) or branch.startswith(("-", "/")) or ".." in branch:
                raise JobError("branch may contain letters, digits, . _ / and -")
            argv += ["--branch", branch]
        if p.get("pr"):
            if not branch:
                raise JobError("opening a pull request needs a branch")
            argv.append("--pr")
        if p.get("parallel"):
            argv.append("--parallel")
        skip = p.get("skip") or []
        if not isinstance(skip, list) or any(s not in SKIPPABLE for s in skip):
            raise JobError(f"skip takes {', '.join(SKIPPABLE)}")
        if skip:
            argv += ["--skip", ",".join(skip)]
        return argv
    raise JobError(f"can't start {workflow!r}; choose doctor, build, fix, autopilot, discuss, market or ship")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def status_of(job: dict) -> str:
    if job.get("stopped"):
        return "stopped"
    if job.get("exit_code") is None:
        return "running" if job.get("pid") and _alive(job["pid"]) else "lost"
    return {0: "succeeded", 2: "not approved", 3: "spend limit", 4: "skipped"}.get(job["exit_code"], "failed")


def list_jobs(root: Path, limit: int = 20) -> list[dict]:
    out = []
    for path in _dir(root).glob("*.json"):
        job = _read(path)
        if job and ID_RE.match(job.get("id", "")):
            out.append({**job, "status": status_of(job)})
    out.sort(key=lambda j: j.get("started", ""), reverse=True)
    return out[:limit]


def start(root: Path, workflow: str, params: dict | None = None) -> dict:
    argv = argv_for(workflow, params or {})
    running = [j for j in list_jobs(root, 100) if j["status"] == "running"]
    if workflow in WRITERS and any(j["workflow"] in WRITERS for j in running):
        busy = next(j for j in running if j["workflow"] in WRITERS)
        raise JobError(f"{busy['workflow']} ({busy['id']}) is still changing files; wait for it or stop it")
    if any(j["workflow"] == workflow for j in running):
        raise JobError(f"a {workflow} run is already going")
    job_id = f"{workflow}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{secrets.token_hex(3)}"
    folder = _dir(root)
    job = {"id": job_id, "workflow": workflow, "argv": argv, "params": params or {},
           "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pid": None, "exit_code": None}
    _write(folder / f"{job_id}.json", job)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "agent_team.jobs", str(Path(root).resolve()), job_id],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, env=env, cwd=str(root))
    threading.Thread(target=proc.wait, daemon=True).start()   # reap it when it ends, wherever we are
    job["pid"] = proc.pid
    _write(folder / f"{job_id}.json", job)
    return {**job, "status": "running"}


def get(root: Path, job_id: str) -> dict:
    if not ID_RE.match(job_id or ""):
        raise JobError("unknown job")
    job = _read(_dir(root) / f"{job_id}.json")
    if not job:
        raise JobError("unknown job")
    return {**job, "status": status_of(job)}


def output(root: Path, job_id: str, offset: int = 0, limit: int = 200_000) -> dict:
    """The job's output from byte `offset`, colour codes removed: {"text", "offset", "status"}."""
    job = get(root, job_id)
    path = _dir(root) / f"{job_id}.log"
    data = b""
    if path.exists():
        with open(path, "rb") as f:
            f.seek(max(0, int(offset)))
            data = f.read(limit)
    return {"text": ANSI_RE.sub("", data.decode("utf-8", errors="replace")), "offset": max(0, int(offset)) + len(data),
            "status": job["status"]}


def stop(root: Path, job_id: str) -> dict:
    job = get(root, job_id)
    if job["status"] != "running":
        return job
    try:
        os.kill(job["pid"], signal.SIGINT)    # the runner passes it on; workflows stop cleanly on Ctrl-C
    except ProcessLookupError:
        pass
    path = _dir(root) / f"{job_id}.json"
    saved = _read(path) or job
    saved["stopped"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write(path, saved)
    return {**saved, "status": "stopped"}


def _run(root: Path, job_id: str) -> int:
    """Run the job's CLI command with output to its log, then record the exit code."""
    folder = _dir(root)
    path = folder / f"{job_id}.json"
    job = _read(path)
    if not job:
        return 1
    with open(folder / f"{job_id}.log", "ab") as log:
        log.write(f"$ agent-team {' '.join(job['argv'])}\n".encode())
        log.flush()
        child = subprocess.Popen([sys.executable, "-m", "agent_team.cli", *job["argv"], "-C", str(root)],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))

        def forward(signum, _frame):
            child.send_signal(signum)
        signal.signal(signal.SIGINT, forward)
        signal.signal(signal.SIGTERM, forward)
        code = child.wait()
    saved = _read(path) or job
    saved["exit_code"] = code
    saved["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write(path, saved)
    if code not in (0, 2, 3, 4) and not saved.get("stopped"):   # 2/3/4: not approved, spend limit, skipped
        try:
            from . import config, keys, notify
            keys.load_into_env()
            notify.send(config.load(root), "run_failed", f"The background {job['workflow']} run {job_id} failed "
                        f"(exit code {code}); see agent-team jobs log {job_id}.")
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(_run(Path(sys.argv[1]), sys.argv[2]))
