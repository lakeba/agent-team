"""Sandboxed test runs: the code models write runs in a throwaway container, not on your machine.

Every build round runs the project's test command, which executes code the team just wrote.
With

    [sandbox]
    mode = "container"     # off (default): run on this machine, as before
    image = ""             # default: chosen from the project's stack
    network = false        # true if the tests must download dependencies
    engine = ""            # docker or podman; default: whichever is installed

the command runs in `docker run --rm` (or podman) with only the project folder mounted, no
network unless allowed, none of your environment variables or keys, as your user id, and with
memory, CPU and process limits. If the engine is missing the run fails loudly rather than
quietly running unsandboxed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

from .config import Team

STACK_IMAGES = [   # (marker, image): the first marker found in the project wins
    (("*.sln", "*.slnx", "*.csproj", "*/*.csproj", "src/*/*.csproj"), "mcr.microsoft.com/dotnet/sdk:10.0"),
    (("package.json",), "node:22-bookworm-slim"),
    (("pyproject.toml", "setup.py", "requirements.txt"), "python:3.12-slim"),
    (("go.mod",), "golang:1.23"),
    (("Cargo.toml",), "rust:1"),
]
DEFAULT_IMAGE = "debian:bookworm-slim"


class SandboxError(RuntimeError):
    pass


def engine(team: Team) -> str | None:
    wanted = team.sandbox.engine
    for name in ([wanted] if wanted else ["docker", "podman"]):
        if shutil.which(name):
            return name
    return None


def ready(team: Team) -> tuple[bool, str]:
    """(usable, detail): the engine is installed and its daemon answers."""
    eng = engine(team)
    if not eng:
        return False, f"{team.sandbox.engine or 'docker or podman'} isn't installed"
    try:
        r = subprocess.run([eng, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False, f"{eng} isn't answering"
    if r.returncode != 0:
        return False, f"{eng} is installed but not running (start Docker Desktop, or the {eng} service)"
    return True, describe(team)


def image_for(team: Team) -> str:
    if team.sandbox.image:
        return team.sandbox.image
    root = Path(team.root)
    for markers, image in STACK_IMAGES:
        if any(next(root.glob(m), None) for m in markers):
            return image
    return DEFAULT_IMAGE


def command(team: Team, test_command: str, name: str) -> list[str]:
    eng = engine(team)
    if not eng:
        raise SandboxError(f"[sandbox].mode is container, but {team.sandbox.engine or 'docker or podman'} isn't installed")
    root = str(Path(team.root).resolve())
    argv = [eng, "run", "--rm", "--name", name, "-v", f"{root}:/work", "-w", "/work",
            "-e", "HOME=/tmp", "-e", "CI=true", "--memory", "2g", "--cpus", "2", "--pids-limit", "512"]
    if not team.sandbox.network:
        argv += ["--network", "none"]
    if hasattr(os, "getuid") and eng == "docker":
        argv += ["--user", f"{os.getuid()}:{os.getgid()}"]
    return argv + [image_for(team), "sh", "-c", test_command]


def run(team: Team, test_command: str, timeout: int = 600) -> tuple[int, str]:
    """Run the test command, sandboxed if configured. Returns (exit code, output)."""
    if team.sandbox.mode != "container":
        r = subprocess.run(test_command, shell=True, cwd=team.root, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    name = f"agent-team-{uuid.uuid4().hex[:12]}"
    try:
        r = subprocess.run(command(team, test_command, name), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run([engine(team) or "docker", "kill", name], capture_output=True)
        raise
    return r.returncode, r.stdout + r.stderr


def describe(team: Team) -> str:
    if team.sandbox.mode != "container":
        return "off (tests run on this machine)"
    net = "with network" if team.sandbox.network else "no network"
    return f"{engine(team) or 'NO ENGINE'} · {image_for(team)} · {net}"
