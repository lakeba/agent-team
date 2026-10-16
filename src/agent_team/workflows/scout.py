"""The scout: what other products look like from the outside, before the team plans.

With a member whose role is `scout` and `[research] sites = [...]`, `discuss` first has REA open
each site in a browser and read it the way a visitor (or a screen reader) does: the page's text,
nothing behind it. The scout turns that into a short brief for the discussion. The brief is kept
under .team/research/ and goes to the discussion only: it never reaches the builders, and the
scout can't be given tools that look inside other software (config.SCOUT_TOOLS).
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import agent, behaviour, github, mcp, ui
from ..config import AgentConfig, Team

MAX_SITES = 5


def observe(team: Team) -> list[tuple[str, str]]:
    """(url, what a visitor reads there, or the problem) for each site, through REA's browser."""
    server = team.behaviour.server
    if server not in team.mcp:
        return [(u, f"not observed: [mcp.{server}] isn't set up (agent-team rea setup)") for u in team.research.sites]
    browser = behaviour.browser_path(team)
    if not browser:
        return [(u, "not observed: no Chrome or Chromium found ([behaviour].browser)") for u in team.research.sites]
    out = []
    with mcp.Client(team.mcp[server], team.root) as client:
        for url in team.research.sites[:MAX_SITES]:
            ui.action(f"scout: looking at {url}")
            try:
                result = client.call("capture_browser_scenario", {
                    "browser": {"mode": "launch", "executable_path": browser, "headless": True},
                    "start_url": {"url": url},
                    "actions": [{"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500}],
                    "capture": {"at_end": ["accessibility", "url"]}}, timeout=120)
            except mcp.McpError as e:
                out.append((url, f"not observed: {e}"))
                continue
            evidence = result.get("structuredContent")
            if result.get("isError") or not isinstance(evidence, dict):
                out.append((url, f"not observed: {mcp.text_of(result)[:300]}"))
                continue
            page = behaviour._browser(evidence).view
            out.append((url, page[: team.research.max_chars] or "(the page had no readable text)"))
    return out


def brief(team: Team, cfg: AgentConfig) -> str:
    """The scout's brief for the discussion ("" when there's nothing to observe)."""
    if not team.research.sites:
        return ""
    pages = observe(team)
    seen = "\n\n".join(f"## {url}\n\n{github.untrusted(text)}" for url, text in pages)
    scout = agent.make(team, cfg, "scout")
    text = scout.turn(f"Pages observed from the outside, for the planning discussion:\n\n{seen}\n\nWrite your brief.")
    folder = team.root / ".team" / "research"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    (folder / f"{stamp}.md").write_text(f"# Scout brief ({cfg.name})\n\nSites: {', '.join(u for u, _ in pages)}\n\n"
                                        f"{text}\n", encoding="utf-8")
    return text
