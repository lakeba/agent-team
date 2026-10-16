"""Token usage per model call, recorded to <project>/.team/usage.jsonl, and cost estimates.

Every call a team member makes appends one JSON line: when, which run, which member, which
provider and model, and the tokens the provider reported. Costs are estimates from the price table
below (US dollars per million tokens), which a project can override in `.team.toml`:

    [pricing."claude-opus-5-5"]
    input = 4.0
    output = 20.0
"""
from __future__ import annotations

import datetime
import json
import threading
from dataclasses import dataclass
from pathlib import Path

USAGE_FILE = "usage.jsonl"

# Anthropic list prices (USD per million tokens) at the time of writing. Cache writes are billed at
# 1.25x input; cache reads as listed. Local and self-hosted models cost nothing per token.
PRICES: dict[str, dict[str, float]] = {
    "claude-fable-5-1": {"input": 10.0, "output": 50.0, "cache_read": 0.25},
    "claude-fable-5": {"input": 10.0, "output": 50.0},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}
FREE_KINDS = {"ollama", "openai", "agent-http"}   # self-hosted unless the project prices them

_lock = threading.Lock()
_current_run = {"id": "", "milestone": ""}


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def set_run(run_id: str) -> None:
    """Tag the calls that follow with this run (set when a workflow opens its log)."""
    _current_run["id"] = run_id


def set_milestone(name: str) -> None:
    """Tag the calls that follow with the milestone autopilot is working on (for milestone budgets)."""
    _current_run["milestone"] = name


def current_milestone() -> str:
    return _current_run["milestone"]


def current_run() -> str:
    return _current_run["id"]


def record(root: Path, agent: str, kind: str, model: str, usage: dict | None) -> None:
    if not usage:
        return
    entry = {"at": now(), "run": _current_run["id"], **({"milestone": _current_run["milestone"]} if _current_run["milestone"] else {}),
             "agent": agent, "kind": kind, "model": model,
             **{k: int(usage.get(k) or 0) for k in ("input", "output", "cache_read", "cache_write")}}
    folder = Path(root) / ".team"
    folder.mkdir(parents=True, exist_ok=True)
    with _lock, open(folder / USAGE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load(root: Path) -> list[dict]:
    path = Path(root) / ".team" / USAGE_FILE
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue   # a half-written line from an interrupted run
    return out


@dataclass
class Price:
    input: float = 0.0
    output: float = 0.0
    cache_read: float | None = None
    cache_write: float | None = None
    known: bool = True

    def cost(self, e: dict) -> float:
        cr = self.cache_read if self.cache_read is not None else self.input * 0.1
        cw = self.cache_write if self.cache_write is not None else self.input * 1.25
        return (e.get("input", 0) * self.input + e.get("output", 0) * self.output
                + e.get("cache_read", 0) * cr + e.get("cache_write", 0) * cw) / 1_000_000


def price_for(model: str, kind: str, overrides: dict | None = None) -> Price:
    if overrides and model in overrides:
        return Price(**{k: float(v) for k, v in overrides[model].items()})
    if model in PRICES:
        return Price(**PRICES[model])
    if kind in FREE_KINDS:
        return Price()
    return Price(known=False)


def summarize(entries: list[dict], overrides: dict | None = None) -> dict:
    """Totals overall, per member, per model and per run, with estimated cost."""
    def bucket():
        return {"calls": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "cost": 0.0}

    total, by_agent, by_model, by_run, unpriced = bucket(), {}, {}, {}, set()
    for e in entries:
        price = price_for(e.get("model", ""), e.get("kind", ""), overrides)
        if not price.known:
            unpriced.add(e.get("model", "?"))
        cost = price.cost(e)
        for b in (total, by_agent.setdefault(e.get("agent", "?"), bucket()),
                  by_model.setdefault(e.get("model", "?") or "?", bucket()),
                  by_run.setdefault(e.get("run", "") or "(untagged)", bucket())):
            b["calls"] += 1
            for k in ("input", "output", "cache_read", "cache_write"):
                b[k] += int(e.get(k, 0))
            b["cost"] += cost
    rnd = lambda d: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
    return {"total": rnd(total), "by_agent": {k: rnd(v) for k, v in by_agent.items()},
            "by_model": {k: rnd(v) for k, v in by_model.items()},
            "by_run": {k: rnd(v) for k, v in by_run.items()}, "unpriced_models": sorted(unpriced)}
