"""A run's output in plain language, for people who don't read logs.

`story(text)` turns the output of a build, fix, market or doctor run (what a terminal shows) into
short steps: "Atlas is writing the plan", "Tests: 12 passed", "Atlas approved it after 2 rounds".
The full output stays available; this is a second view of it, never a replacement.
"""
from __future__ import annotations

import re

ANSI = re.compile(r"\x1b\[[0-9;]*m")
WRITING = re.compile(r"^--- (\S+) · (\S+)(?: · [^(]*)? \(([^)]*)\) is (?:writing|working)")
ROUND = re.compile(r"=+ Round (\d+)/(\d+) =+")
RAN = re.compile(r"^Ran (\d+) tests? in")
PYTEST = re.compile(r"^(?:=+ )?(?:(\d+) failed, )?(\d+) passed")
VERDICT = re.compile(r"^\s*VERDICT:\s*(APPROVED|CHANGES)\s*$")
APPROVED_AFTER = re.compile(r"^(\S+) approved after (\d+) round")
STOPPED = re.compile(r"^Stopped after (\d+) rounds without approval")
HELD = re.compile(r"held back ([^\s:]+)")
ACTION = re.compile(r"^\s*▸ (.+)$")
CHECK = re.compile(r"^## Check `([^`]+)`: (passed|FAILED)")
BEHAVIOUR = re.compile(r"^## (.+): behaves (as before|differently)")
LEFTOVERS = re.compile(r"^## Possible debug leftovers")

DOING = {"lead": "planning and reviewing", "builder": "writing the code", "qa": "writing the tests",
         "security": "checking security", "docs": "updating the docs", "marketing": "writing the marketing",
         "devops": "working on GitHub", "factcheck": "checking the facts", "reviewer": "reviewing"}


def story(text: str) -> list[dict]:
    """[{kind, text}] in order; kind is info, good, warn, bad or done."""
    out: list[dict] = []
    last_writer = ""
    rounds = 0

    def add(kind: str, msg: str):
        if not out or out[-1]["text"] != msg:
            out.append({"kind": kind, "text": msg})

    for raw in ANSI.sub("", text or "").splitlines():
        line = raw.rstrip()
        m = WRITING.match(line)
        if m:
            name, role, _ = m.groups()
            if (name, role) != last_writer:
                doing = DOING.get(role, "working")
                if role == "lead":
                    doing = "reviewing the work" if rounds else "writing the plan"
                add("info", f"{name} is {doing}")
                last_writer = (name, role)
            continue
        m = ROUND.search(line)
        if m:
            rounds = int(m.group(1))
            last_writer = ""
            add("info", f"Round {m.group(1)} of {m.group(2)}")
            continue
        m = RAN.match(line)
        if m:
            add("info", f"Ran {m.group(1)} tests")
            continue
        if line.strip() == "OK" or line.startswith("OK ("):
            add("good", "Tests: all passed")
            continue
        if line.startswith("FAILED (") or re.match(r"^=+ .*\bfailed\b", line):
            add("bad", "Tests: some failed, the team is fixing them")
            continue
        m = PYTEST.search(line)
        if m:
            if m.group(1):
                add("bad", f"Tests: {m.group(1)} failed, {m.group(2)} passed; the team is fixing them")
            else:
                add("good", f"Tests: {m.group(2)} passed")
            continue
        m = CHECK.match(line)
        if m:
            add("good" if m.group(2) == "passed" else "bad", f"Check {m.group(1)}: {'passed' if m.group(2) == 'passed' else 'failed'}")
            continue
        m = BEHAVIOUR.match(line)
        if m:
            add("info" if m.group(2) == "as before" else "warn",
                f"Used like a user would: “{m.group(1)}” {'works as before' if m.group(2) == 'as before' else 'behaves differently now'}")
            continue
        if LEFTOVERS.match(line):
            add("warn", "Some leftover debug code was spotted for the lead to look at")
            continue
        m = VERDICT.match(line)
        if m and rounds:
            who = last_writer[0] if last_writer else "The lead"
            add("good" if m.group(1) == "APPROVED" else "warn",
                f"{who} approved it" if m.group(1) == "APPROVED" else f"{who} asked for changes")
            continue
        m = APPROVED_AFTER.match(line)
        if m:
            add("done", f"Done: {m.group(1)} approved the work after {m.group(2)} round{'s' if m.group(2) != '1' else ''}")
            continue
        m = STOPPED.match(line)
        if m:
            add("bad", f"Stopped after {m.group(1)} rounds without approval: try again with a smaller task, or more rounds")
            continue
        m = HELD.search(line)
        if m:
            add("warn", f"A change to {m.group(1)} waits for the builder to explain it first")
            continue
        m = ACTION.match(line)
        if m:
            msg = m.group(1).strip()
            if msg.startswith(("opened PR", "created branch", "applied the", "secret check", "merged")):
                add("info", msg[0].upper() + msg[1:])
            continue
        if line.startswith("Spend limit"):
            add("bad", "Stopped: the spend limit was reached")
    return out
