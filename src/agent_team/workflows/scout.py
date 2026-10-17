"""The scout: what other products look like from the outside, before the team plans.

With a member whose role is `scout` and `[research] sites = [...]`, `discuss` first has REA open
each site in a browser and read it the way a visitor (or a screen reader) does: the page's text,
nothing behind it. The scout turns that into a short brief for the discussion. The brief is kept
under .team/research/ and goes to the discussion only: it never reaches the builders, and the
scout can't be given tools that look inside other software (config.SCOUT_TOOLS).
"""
from __future__ import annotations

from datetime import datetime, timezone

import urllib.parse

from .. import agent, behaviour, github, mcp, ui
from ..config import AgentConfig, Team

MAX_SITES = 5
STEP_MS = 15_000   # a step whose element never appears (a dialog that didn't come) gives up after this


def actions(url: str, steps: list[str]) -> list[dict]:
    """REA's browser actions for one site: its steps (relative goto paths are on the site, and each
    gives up after STEP_MS), then a pause."""
    from ..steps import parse_steps
    out = parse_steps(steps)
    for a in out:
        if a["action"] == "goto":
            a["destination"]["url"] = urllib.parse.urljoin(url, a["destination"]["url"])
        if a["action"] != "wait_for_timeout":
            a["timeout_ms"] = STEP_MS
    return out + [{"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500}]


def _look(client: mcp.Client, browser: str, url: str, steps: list[str]) -> tuple[str, str]:
    """(the page's text, "") when the steps worked; (the step that failed, "step"), or (why it
    wasn't observed, "problem")."""
    try:
        result = client.call("capture_browser_scenario", {
            "browser": {"mode": "launch", "executable_path": browser, "headless": True},
            "start_url": {"url": url}, "actions": actions(url, steps),
            "capture": {"at_end": ["accessibility", "url"]}}, timeout=120)
    except mcp.McpError as e:
        return f"not observed: {e}", "problem"
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return f"not observed: {mcp.text_of(result)[:300]}", "problem"
    seen = behaviour._browser(evidence)   # for whether the steps worked; the text is read from the top
    return (behaviour.page_text(evidence), "") if seen.exit == "all steps completed" else (seen.exit, "step")


def observe(team: Team) -> list[tuple[str, str]]:
    """(url, what a visitor reads there, or the problem) for each site, through REA's browser.
    A site's steps (e.g. accepting a cookie dialog) run before the page is read."""
    server, pages = team.behaviour.server, team.research.pages()
    if server not in team.mcp:
        return [(u, f"not observed: [mcp.{server}] isn't set up (agent-team rea setup)") for u, _ in pages]
    browser = behaviour.browser_path(team)
    if not browser:
        return [(u, "not observed: no Chrome or Chromium found ([behaviour].browser)") for u, _ in pages]
    out = []
    with mcp.Client(team.mcp[server], team.root) as client:
        for url, steps in pages[:MAX_SITES]:
            ui.action(f"scout: looking at {url}")
            page, trouble = _look(client, browser, url, steps)
            note = ""
            if trouble == "step":   # REA stops at a step that fails: read the page as a visitor first sees it
                note = f"(a step didn't work: {page[:200]})\n\n"
                page, trouble = _look(client, browser, url, [])
            if not trouble:
                page = page[: team.research.max_chars] or "(the page had no readable text)"
            out.append((url, note + page))
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
