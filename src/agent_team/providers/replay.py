"""A recorded run, for `agent-team try` without any model: replies are played back, not generated.

Each member's reply is chosen by its role (from its label) and by a phrase in what it was asked,
from agent_team/demo/replay.json. Nothing is sent anywhere; the files, tests and checks around the
replies are real.
"""
from __future__ import annotations

import json
import re
import time
from importlib import resources

from .base import Provider, Reply, register


@register("replay")
class ReplayProvider(Provider):
    pause = 0.6   # seconds, so the run reads like one

    def __init__(self, cfg, secret: str = ""):
        super().__init__(cfg, secret)
        data = json.loads(resources.files("agent_team").joinpath("demo", "replay.json").read_text(encoding="utf-8"))
        self.script = data["script"]

    def complete(self, system, messages, *, model, effort, label):
        parts = re.sub(r"\x1b\[[0-9;]*m", "", label).split("·")   # "Name · role[ · part: ...]"
        role = parts[1].strip().split()[0] if len(parts) > 1 and parts[1].strip() else ""
        asked = str(messages[-1].get("content", "")) if messages else ""
        for rule in self.script.get(role) or self.script["default"]:
            if rule["when"] in asked:
                from .. import ui
                ui.say(f"\n--- {label} (replay) is working...")
                time.sleep(self.pause)
                ui.say(rule["reply"])
                return Reply(text=rule["reply"], content=rule["reply"], usage={"input": 0, "output": 0})
        return Reply(text="", content="")

    def check(self, model):
        return "ok (a recorded run: no model is called)"
