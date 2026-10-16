"""Spend limits: stop a run before it costs more than `[limits]` allows.

    [limits]
    per_run = 5.0     # US dollars for one workflow run
    per_day = 20.0    # US dollars per UTC day, across every run in this project

Checked before every model call, from the estimates in `.team/usage.jsonl`. A call already in
flight finishes, so a run can go over by at most one reply.
"""
from __future__ import annotations

from . import usage
from .config import Team


class SpendLimitError(RuntimeError):
    pass


def spent(team: Team, run: str | None = None) -> dict:
    """Estimated dollars spent in this run and today (UTC)."""
    run = usage.current_run() if run is None else run
    today = usage.now()[:10]
    out = {"run": 0.0, "today": 0.0}
    for e in usage.load(team.root):
        cost = usage.price_for(e.get("model", ""), e.get("kind", ""), team.pricing).cost(e)
        if run and e.get("run") == run:
            out["run"] += cost
        if (e.get("at") or "")[:10] == today:
            out["today"] += cost
    return {k: round(v, 4) for k, v in out.items()}


def milestone_spent(team: Team, milestone: str) -> float:
    return round(sum(usage.price_for(e.get("model", ""), e.get("kind", ""), team.pricing).cost(e)
                     for e in usage.load(team.root) if e.get("milestone") == milestone), 4)


def check(team: Team) -> None:
    limits = team.limits
    milestone = usage.current_milestone()
    cap = limits.milestones.get(milestone) if milestone else None
    if cap:
        spent_m = milestone_spent(team, milestone)
        if spent_m >= cap:
            raise SpendLimitError(f"milestone {milestone} has spent an estimated ${spent_m:.2f}, reaching its "
                                  f"[limits.milestones] budget of ${cap:.2f}")
    if not (limits.per_run or limits.per_day):
        return
    s = spent(team)
    if limits.per_run and s["run"] >= limits.per_run:
        raise SpendLimitError(f"this run has spent an estimated ${s['run']:.2f}, reaching the "
                              f"[limits].per_run limit of ${limits.per_run:.2f}")
    if limits.per_day and s["today"] >= limits.per_day:
        raise SpendLimitError(f"this project has spent an estimated ${s['today']:.2f} today (UTC), reaching "
                              f"the [limits].per_day limit of ${limits.per_day:.2f}")
