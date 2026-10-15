"""Test helpers: a scripted provider, so workflows run without any real model."""
from __future__ import annotations

import io
import contextlib
import tempfile
from collections import defaultdict, deque
from pathlib import Path

from agent_team import config
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
