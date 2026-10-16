"""Notifications: tell people what the team did, so unattended runs don't need watching.

    [notify]
    webhook_env = "AGENT_TEAM_WEBHOOK"   # the variable holding the URL (agent-team keys set ...)
    format = "slack"                     # slack: {"text"}; json: {"event", "project", "text", "url"}
    events = []                          # empty: all of them

The URL is a secret (anyone with it can post), so it lives in the environment or the keys file,
never in .team.toml. A notification that can't be sent is reported and never stops a run.
"""
from __future__ import annotations

import json
import os
import urllib.request

from . import ui
from .config import Team

EVENTS = {
    "pr_opened": "a pull request was opened",
    "pr_merged": "a pull request was merged",
    "fix_pushed": "a fix was pushed to a pull request",
    "approval_needed": "a pull request waits for the owners' approval",
    "release_proposed": "a release waits for the owners' approval",
    "released": "a release was published",
    "autopilot_stopped": "autopilot finished or stopped",
    "spend_limit": "a run stopped at a spend limit",
    "run_failed": "a background run failed",
}


def _url(team: Team) -> str:
    env = team.notify.webhook_env
    url = os.environ.get(env, "") if env else ""
    if url and not (url.startswith("https://") or url.startswith("http://127.0.0.1") or url.startswith("http://localhost")):
        ui.warn(f"{env} must be an https:// URL; not sending notifications")
        return ""
    return url


def enabled(team: Team, event: str) -> bool:
    return bool(team.notify.webhook_env) and (not team.notify.events or event in team.notify.events)


def send(team: Team, event: str, text: str, link: str = "") -> bool:
    """Post one notification. Returns whether it was sent; failures only warn."""
    if not enabled(team, event):
        return False
    url = _url(team)
    if not url:
        return False
    project = team.project.repo or team.project.name
    if team.notify.format == "json":
        payload = {"event": event, "project": project, "text": text, "url": link}
    else:
        payload = {"text": f"*{project}* · {text}" + (f"\n<{link}>" if link else "")}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "agent-team"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except Exception as e:      # a notification never stops the work
        ui.warn(f"notification ({event}) not sent: {type(e).__name__}")
        return False
