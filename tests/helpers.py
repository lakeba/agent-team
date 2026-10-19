"""Test helpers: a scripted provider, so workflows run without any real model."""
from __future__ import annotations

import io
import contextlib
import tempfile
from collections import defaultdict, deque
from pathlib import Path

import os

# Tests never touch the real ~/.config/agent-team (keys file, project list).
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="agent-team-test-config-")
# This computer's own REA (agent-team's copy, or one registered with Claude Code) must not change
# what the tests see: they get an empty data folder and Claude Code config of their own.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="agent-team-test-data-")
os.environ["CLAUDE_CONFIG_DIR"] = tempfile.mkdtemp(prefix="agent-team-test-claude-")

from agent_team import config  # noqa: E402
from agent_team import readiness  # noqa: E402

# Nor do they search the network for Ollama servers: only the addresses a test names are tried.
REAL_OLLAMA_CANDIDATES = readiness.ollama_candidates
readiness.ollama_candidates = lambda: []
REAL_LAN_CANDIDATES = readiness.lan_candidates
readiness.lan_candidates = lambda: []      # nor scan the local network
REAL_HOME_NETWORKS = readiness.home_networks
readiness.home_networks = lambda: []       # nor, in a VM, the home networks
from agent_team.providers.base import Provider, Reply, register

# label substring (the agent's name) -> queue of replies
SCRIPTS: dict[str, deque] = defaultdict(deque)
CALLS: list[dict] = []


@register("fake")
class FakeProvider(Provider):
    supports_images = False

    def complete(self, system, messages, *, model, effort, label):
        CALLS.append({"label": label, "system": system, "messages": [dict(m) for m in messages]})
        for name, queue in SCRIPTS.items():
            if name in label and queue:
                text = queue.popleft()
                return Reply(text=text, content=text)
        raise AssertionError(f"no scripted reply left for {label!r}")

    def check(self, model):
        return "ok (fake)"


def reset():
    SCRIPTS.clear()
    CALLS.clear()


TEAM_TOML = """
[project]
name = "demo"
repo = ""
test_command = "{test_command}"
guarantees = ["Never delete user data"]

[providers.fake]
kind = "fake"

[[agents]]
name = "Atlas"
role = "lead"
provider = "fake"
model = "m"
owns = ["ROADMAP.md"]

[[agents]]
name = "Forge"
role = "builder"
provider = "fake"
model = "m"

[[agents]]
name = "Spark"
role = "marketing"
provider = "fake"
model = "m"
owns = ["BRIEF.md", "site/"]

[[agents]]
name = "Quill"
role = "reviewer"
provider = "fake"
model = "m"
description = "Security reviewer: looks for unsafe file handling."
"""


def project(test_command: str = "true", files: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / ".team.toml").write_text(TEAM_TOML.format(test_command=test_command), encoding="utf-8")
    for rel, body in (files or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    return root


def load(root: Path) -> config.Team:
    return config.load(root)


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield
