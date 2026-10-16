"""Cost estimates before a run, from what the same kind of run cost before in this project.

Estimates use the recorded runs of the same workflow (usage.jsonl tags every call with its run):
a typical cost (the median) and a high one (the 90th percentile). With no history yet there's
no estimate, rather than a made-up number. Autopilot is estimated per cycle, as a build plus a
shift.
"""
from __future__ import annotations

import statistics

from . import budget, usage
from .config import Team


def run_costs(team: Team) -> dict[str, list[float]]:
    """Workflow -> the cost of each recorded run, oldest first."""
    spend = usage.summarize(usage.load(team.root), team.pricing)["by_run"]
    out: dict[str, list[float]] = {}
    for run_id, v in spend.items():
        workflow = run_id.split("@", 1)[0] if "@" in run_id else ""
        if workflow and v["calls"]:
            out.setdefault(workflow, []).append(v["cost"])
    return out


def _quantiles(costs: list[float]) -> tuple[float, float]:
    if len(costs) == 1:
        return costs[0], costs[0]
    ordered = sorted(costs)
    high = ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]
    return statistics.median(ordered), high


def estimate(team: Team, workflow: str, cycles: int = 1) -> dict:
    """{workflow, runs (history size), typical, high, note, warning} in US dollars."""
    history = run_costs(team)
    parts = ["build", "ship"] if workflow == "autopilot" else [workflow]
    typical = high = 0.0
    sizes = []
    for part in parts:
        costs = history.get(part, [])
        if not costs:
            return {"workflow": workflow, "runs": 0, "typical": None, "high": None, "warning": "",
                    "note": f"No {part} runs recorded yet, so there's no estimate."}
        t, h = _quantiles(costs)
        typical, high = typical + t, high + h
        sizes.append(len(costs))
    n = max(1, cycles) if workflow == "autopilot" else 1
    typical, high = round(typical * n, 2), round(high * n, 2)
    what = f"{n} cycle(s) of build + shift" if workflow == "autopilot" else f"one {workflow}"
    note = f"About ${typical:.2f} for {what} (up to ${high:.2f}), from {min(sizes)} past run(s)."
    warning = ""
    limits, spent = team.limits, budget.spent(team, run="")
    if limits.per_run and high > limits.per_run and workflow != "autopilot":
        warning = f"It may reach the per-run limit of ${limits.per_run:.2f}."
    if limits.per_day and spent["today"] + high > limits.per_day:
        left = max(0.0, limits.per_day - spent["today"])
        warning = (warning + " " if warning else "") + f"Only ${left:.2f} of today's ${limits.per_day:.2f} is left."
    return {"workflow": workflow, "runs": min(sizes), "typical": typical, "high": high, "note": note, "warning": warning}
