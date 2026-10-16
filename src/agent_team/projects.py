"""Every project you use agent-team in, for the dashboard's control room.

Projects are remembered in ~/.config/agent-team/projects.json when a command loads their team.
The control room summarises each one from its own records (spend, runs, what waits for you,
background runs) without contacting any model or GitHub, and can open a project's own dashboard.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import keys, usage

FILE = "projects.json"


def _path() -> Path:
    return keys.path().parent / FILE


def registered() -> list[str]:
    try:
        return [p for p in json.loads(_path().read_text(encoding="utf-8")) if isinstance(p, str)]
    except (OSError, ValueError):
        return []


def register(root) -> None:
    root = str(Path(root).resolve())
    known = registered()
    if root in known:
        return
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known + [root], indent=1), encoding="utf-8")
    except OSError:
        pass    # remembering projects is a convenience; never fail a command over it


def forget(root) -> bool:
    root = str(Path(root).resolve())
    known = registered()
    if root not in known:
        return False
    _path().write_text(json.dumps([p for p in known if p != root], indent=1), encoding="utf-8")
    return True


def summary(root: str) -> dict:
    from . import config, gates, jobs, logs
    from .workflows import ship
    out = {"root": root, "name": Path(root).name, "ok": False}
    if not (Path(root) / config.CONFIG_NAME).exists():
        out["problem"] = "no .team.toml here any more"
        return out
    try:
        team = config.load(root)
    except config.ConfigError as e:
        out["problem"] = f"config: {e}"
        return out
    spend = usage.summarize(usage.load(team.root), team.pricing)
    today = usage.now()[:10]
    cost_today = sum(usage.price_for(e.get("model", ""), e.get("kind", ""), team.pricing).cost(e)
                     for e in usage.load(team.root) if (e.get("at") or "").startswith(today))
    runs = logs.parse(team.root)
    running = [j for j in jobs.list_jobs(team.root, 50) if j["status"] == "running"]
    proposal = ship.release_proposal(team.root)
    out.update({
        "ok": True, "name": team.project.name, "repo": team.project.repo, "members": len(team.agents),
        "cost_total": round(spend["total"]["cost"], 2), "cost_today": round(cost_today, 2),
        "limit_per_day": team.limits.per_day,
        "last_run": {k: runs[0][k] for k in ("workflow", "title", "started", "outcome")} if runs else None,
        "running": [j["workflow"] for j in running],
        "waiting": [f"approve PR #{r['number']}" for r in gates.requests(team.root)]
                   + ([f"release v{proposal['version']}"] if proposal else []),
    })
    return out


def all_summaries() -> list[dict]:
    return [summary(p) for p in registered() if os.path.isdir(p)]
