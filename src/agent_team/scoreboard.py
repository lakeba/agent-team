"""The scoreboard: how each member and model is doing, from the team's own logs and usage.

  * builders: builds, how many the lead approved, how many on the first round, average rounds,
    fixes pushed, and what their runs cost;
  * reviewers: reviews and sign-offs given, and how often they asked for changes;
  * the team: PRs merged, and the cost per merged PR.
It answers questions like "is the local builder worth it compared with Claude?" with numbers.
"""
from __future__ import annotations

import re

from . import logs, usage
from .config import Team

def compute(team: Team) -> dict:
    spend = usage.summarize(usage.load(team.root), team.pricing)
    run_cost = {rid: v["cost"] for rid, v in spend["by_run"].items()}
    builders: dict[str, dict] = {}
    reviewers: dict[str, dict] = {}
    merged = 0

    def b(name):
        return builders.setdefault(name, {"builds": 0, "approved": 0, "first_round": 0, "rounds": 0,
                                          "fixes": 0, "fixes_pushed": 0, "cost": 0.0})

    def r(name):
        return reviewers.setdefault(name, {"reviews": 0, "changes_requested": 0, "signoffs": 0, "signoffs_refused": 0})

    for run in logs.parse(team.root):
        entries, cost = run["entries"], run_cost.get(run["id"], 0.0)
        if run["workflow"] == "build":
            made = [e for e in entries if re.match(r"^round \d+$", e["what"]) and e["who"] != "Tests"]
            makers = sorted({e["who"] for e in made})
            rounds = len({e["what"] for e in made})
            approved = run["outcome"].startswith("approved")
            for name in makers:
                s = b(name)
                s["builds"] += 1
                s["rounds"] += rounds
                s["approved"] += approved
                s["first_round"] += approved and rounds == 1
                s["cost"] += cost / max(1, len(makers))
            for e in entries:
                if re.match(r"^review \d+$", e["what"]):
                    s = r(e["who"])
                    s["reviews"] += 1
                    s["changes_requested"] += e["marker"] == "CHANGES"
        elif run["workflow"] == "fix":
            makers = sorted({e["who"] for e in entries if re.match(r"^fix \d+$", e["what"]) and e["who"] != "Tests"})
            pushed = any(e["what"] == "action" and "pushed" in e["text"] for e in entries)
            for name in makers:
                s = b(name)
                s["fixes"] += 1
                s["fixes_pushed"] += pushed
                s["cost"] += cost / max(1, len(makers))
        elif run["workflow"] == "ship":
            for e in entries:
                if e["what"].startswith("review of PR #"):
                    s = r(e["who"])
                    s["reviews"] += 1
                    s["changes_requested"] += e["marker"] == "CHANGES"
                elif e["what"].startswith("sign-off on PR #"):
                    s = r(e["who"])
                    s["signoffs"] += 1
                    s["signoffs_refused"] += e["marker"] == "NO"
                merged += sum(1 for a in e["actions"] if a.startswith("merged PR"))

    for s in builders.values():
        s["approval_rate"] = round(s["approved"] / s["builds"], 2) if s["builds"] else None
        s["first_round_rate"] = round(s["first_round"] / s["builds"], 2) if s["builds"] else None
        s["avg_rounds"] = round(s["rounds"] / s["builds"], 1) if s["builds"] else None
        s["cost"] = round(s["cost"], 2)
    for s in reviewers.values():
        given = s["reviews"] + s["signoffs"]
        s["pushback_rate"] = round((s["changes_requested"] + s["signoffs_refused"]) / given, 2) if given else None
    models = {name: team.agents[name].model or team.agents[name].provider
              for name in set(builders) | set(reviewers) if name in team.agents}
    total = spend["total"]["cost"]
    return {"builders": builders, "reviewers": reviewers, "models": models,
            "members_cost": {k: v["cost"] for k, v in spend["by_agent"].items()},
            "team": {"merged_prs": merged, "cost": round(total, 2),
                     "cost_per_merged_pr": round(total / merged, 2) if merged else None}}
