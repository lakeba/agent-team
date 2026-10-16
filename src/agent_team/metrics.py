"""Activity metrics for the dashboard's live charts: what the team did, how well, and what failed.

Everything is derived from the records the team already keeps (usage.jsonl, the run logs, the
background jobs and the eval reports), so there's nothing extra to collect.
"""
from __future__ import annotations

import datetime as dt

from . import evals, jobs, logs, usage
from .config import Team

OUTCOME_FAIL = ("not approved", "incomplete", "no roadmap written")


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute(team: Team, hours: int = 48, days: int = 30) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    entries = usage.load(team.root)

    hour_keys = [(now - dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H") for h in range(hours - 1, -1, -1)]
    hourly = {k: {"hour": k, "calls": 0, "cost": 0.0, "tokens": 0} for k in hour_keys}
    day_keys = [(now - dt.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days - 1, -1, -1)]
    daily = {k: {"day": k, "cost": 0.0, "runs": 0, "approved": 0, "rejected": 0, "merged": 0, "refused": 0,
                 "failed_jobs": 0, "changes_requested": 0} for k in day_keys}
    by_member: dict[str, dict] = {}
    for e in entries:
        price = usage.price_for(e.get("model", ""), e.get("kind", ""), team.pricing)
        cost = price.cost(e)
        at = (e.get("at") or "")
        h = hourly.get(at[:13])
        if h:
            h["calls"] += 1
            h["cost"] += cost
            h["tokens"] += sum(int(e.get(k, 0)) for k in ("input", "output", "cache_read", "cache_write"))
        d = daily.get(at[:10])
        if d:
            d["cost"] += cost
        if at[:10] in daily:
            m = by_member.setdefault(e.get("agent", "?"), {"calls": 0, "cost": 0.0})
            m["calls"] += 1
            m["cost"] += cost

    feed = []
    workflows: dict[str, int] = {}
    for run in logs.parse(team.root):
        day = (run["started"] or "")[:10]
        d = daily.get(day)
        if d:
            d["runs"] += 1
            workflows[run["workflow"]] = workflows.get(run["workflow"], 0) + 1
            if run["workflow"] in ("build", "fix", "market", "setup"):
                if run["outcome"].startswith(OUTCOME_FAIL):
                    d["rejected"] += 1
                elif run["outcome"].startswith("approved") or run["workflow"] == "fix":
                    d["approved"] += 1
        for e in run["entries"]:
            ed = daily.get((e["at"] or run["started"] or "")[:10])
            if ed:
                ed["merged"] += sum(1 for a in e["actions"] if a.startswith("merged PR"))
                ed["refused"] += e["what"] == "refused"
                ed["changes_requested"] += e["marker"] in ("CHANGES", "NO")
            if e["at"]:
                feed.append({"at": e["at"], "workflow": run["workflow"], "who": e["who"], "what": e["what"],
                             "marker": e["marker"], "actions": e["actions"][:2]})
    for j in jobs.list_jobs(team.root, 200):
        if j["status"] == "failed" and j.get("started", "")[:10] in daily:
            daily[j["started"][:10]]["failed_jobs"] += 1
    feed.sort(key=lambda f: f["at"], reverse=True)

    week = day_keys[-7:]
    sums = {k: sum(daily[d][k] for d in week) for k in ("approved", "rejected", "merged", "refused", "failed_jobs", "cost", "runs")}
    judged = sums["approved"] + sums["rejected"]
    running = [j for j in jobs.list_jobs(team.root, 50) if j["status"] == "running"]
    today = daily[day_keys[-1]]
    for row in list(hourly.values()) + list(daily.values()):
        row["cost"] = round(row["cost"], 4)
    return {
        "now": now.isoformat(timespec="seconds"),
        "tiles": {"cost_today": round(today["cost"], 4), "runs_today": today["runs"],
                  "calls_last_hour": hourly[hour_keys[-1]]["calls"], "running": len(running),
                  "approval_rate_7d": round(sums["approved"] / judged, 2) if judged else None,
                  "merged_7d": sums["merged"], "problems_7d": sums["rejected"] + sums["refused"] + sums["failed_jobs"],
                  "cost_7d": round(sums["cost"], 2)},
        "hourly": list(hourly.values()), "daily": list(daily.values()),
        "by_member": {k: {"calls": v["calls"], "cost": round(v["cost"], 4)} for k, v in sorted(by_member.items(), key=lambda kv: -kv[1]["cost"])},
        "workflows": workflows,
        "running": [{"id": j["id"], "workflow": j["workflow"], "started": j["started"],
                     "what": j["params"].get("task") or j["params"].get("topic") or j["params"].get("milestone") or ""}
                    for j in running],
        "feed": feed[:40],
        "evals": [{"at": r["at"], "passed": r["passed"], "total": r["total"], "cost": r["cost"]}
                  for r in evals.history(team.root)][-20:],
    }
