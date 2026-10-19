"""Inspire: an app the founder likes, explored from the outside, as a brief the lead plans from.

    agent-team inspire https://example.com --journey 'click link "Pricing"'

The scout (or the lead, without one) gets what a visitor sees of the app: up to `max_pages` pages
of the same site, each one's text as a screen reader reads it, its address and a screenshot, and
the screens of the journeys the founder asks about. It writes an inspiration brief in its own words:
features, journeys, business model, strengths, gaps, three ways to be different, and what not to
copy. Everything is kept under .team/inspiration/<app>/, which no member's context ever includes.

The boundary, in code:
- REA is asked for exactly CAPTURE (screenshot, accessibility text, address) and nothing else: no
  scripts, network traffic or console, and none of REA's tools that look inside software.
- robots.txt is read first (RFC 9309: unreachable means nothing is allowed); disallowed pages are
  skipped and named. Only the start page's origin is followed, two links deep.
- Pages are fetched without signing in; a journey that needs an account or a payment stops there.
- Everything from the app is wrapped as untrusted before a model reads it.
- Members who write code (builder, qa, docs) are refused the brief and its captures (for_member).
- The founder confirms once per app that they use it and may look at it this way.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from . import github, mcp, ui
from .config import WRITES_CODE, AgentConfig, Team

CAPTURE = ("screenshot", "accessibility", "url")   # the only things ever asked of REA here
USER_AGENT = "agent-team-scout"
MAX_PAGES = 20
MAX_DEPTH = 2
MAX_JOURNEYS = 5
MAX_STEPS = 8
PAGE_CHARS = 4000            # page text per page the model reads
MAX_IMAGES = 12              # screenshots the model sees (pages first, then journey steps)
STEP_MS = 15_000
FETCH_BYTES = 1_000_000
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".pdf", ".zip", ".dmg", ".exe", ".mp4", ".mp3",
            ".css", ".js", ".json", ".xml", ".rss", ".woff", ".woff2")


class InspireError(RuntimeError):
    pass


@dataclass
class Look:
    """One page (or one journey step) as a visitor saw it."""
    url: str
    text: str = ""
    png: str = ""            # base64 PNG, when REA took the screenshot
    problem: str = ""        # why it wasn't seen
    label: str = ""          # "page 3", "journey 1, step 2"


@dataclass
class Exploration:
    start: str
    pages: list[Look] = field(default_factory=list)
    journeys: list[list[Look]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)     # disallowed by robots.txt
    notes: list[str] = field(default_factory=list)


# --- where it's kept ---------------------------------------------------------------------------

def slug(url: str) -> str:
    host = urllib.parse.urlsplit(url).hostname or "app"
    return re.sub(r"[^a-z0-9]+", "-", host.lower().removeprefix("www.")).strip("-")[:60] or "app"


def folder(root: Path | str, url_or_slug: str) -> Path:
    name = slug(url_or_slug) if "://" in url_or_slug else url_or_slug
    if not re.fullmatch(r"[a-z0-9-]{1,60}", name):
        raise InspireError(f"{url_or_slug!r} isn't an app name")
    return Path(root) / ".team" / "inspiration" / name


def confirmed(root: Path, url: str) -> bool:
    return (folder(root, url) / "confirmed.json").is_file()


def confirm(root: Path, url: str) -> None:
    """The founder's confirmation, kept with the app's captures (with the date)."""
    f = folder(root, url)
    f.mkdir(parents=True, exist_ok=True)
    (f / "confirmed.json").write_text(json.dumps({"url": url, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                  "statement": CONFIRMATION}, indent=1), encoding="utf-8")


CONFIRMATION = ("I use this app, and I may look at its public pages this way: from the outside, without signing in, "
                "keeping to its robots.txt. The team won't copy its code, wording, names, logos or designs.")


# --- robots.txt and links ----------------------------------------------------------------------

def _get(url: str, timeout: float = 15) -> tuple[int, str, str]:
    """(status, content type, text) of a plain GET, as agent-team-scout."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(FETCH_BYTES)
            return r.status, r.headers.get("Content-Type", ""), body.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, "", ""


class Robots:
    """robots.txt for one origin. RFC 9309: a 4xx means no rules; a 5xx or no answer means nothing
    may be fetched."""

    def __init__(self, origin: str, get=_get):
        self.parser = urllib.robotparser.RobotFileParser()
        self.blocked_all = False
        self.note = ""
        try:
            status, _, text = get(f"{origin}/robots.txt")
        except (OSError, ValueError) as e:
            status, text = 0, ""
            self.note = f"robots.txt couldn't be read ({e}), so nothing was visited"
        if status >= 500 or status == 0:
            self.blocked_all = True
            self.note = self.note or f"robots.txt answered {status}, so nothing was visited"
        elif 400 <= status < 500:
            self.parser.parse([])
        else:
            self.parser.parse(text.splitlines())

    def allowed(self, url: str) -> bool:
        return not self.blocked_all and self.parser.can_fetch(USER_AGENT, url)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def same_site_links(html: str, base: str) -> list[str]:
    """The page's links that stay on its origin, without fragments, files or duplicates. Only
    <a href> is read; the page's scripts never are."""
    p = _Links()
    try:
        p.feed(html)
    except Exception:   # a broken page still gives the links found so far
        pass
    origin = urllib.parse.urlsplit(base)
    out, seen = [], set()
    for href in p.hrefs:
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        u = urllib.parse.urlsplit(urllib.parse.urljoin(base, href))
        if (u.scheme, u.netloc) != (origin.scheme, origin.netloc):
            continue
        if u.path.lower().endswith(SKIP_EXT):
            continue
        clean = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path or "/", u.query, ""))
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


# --- REA ---------------------------------------------------------------------------------------

def capture_input(browser: str, url: str, actions: list[dict]) -> dict:
    """The one shape of REA call this module makes: a headless browser, the steps, and CAPTURE."""
    return {"browser": {"mode": "launch", "executable_path": browser, "headless": True},
            "start_url": {"url": url}, "actions": actions,
            "capture": {"at_end": list(CAPTURE)}}


def check_input(payload: dict) -> None:
    """Refuse any call asking REA for more than CAPTURE (scripts, events, network...)."""
    cap = payload.get("capture") or {}
    if set(cap) - {"at_end"} or set(cap.get("at_end") or []) - set(CAPTURE):
        raise InspireError(f"refused: inspire only captures {', '.join(CAPTURE)}")


def _actions(url: str, steps: list[str]) -> list[dict]:
    from .steps import parse_steps
    out = parse_steps(steps)
    for a in out:
        if a["action"] == "goto":
            a["destination"]["url"] = urllib.parse.urljoin(url, a["destination"]["url"])
        if a["action"] != "wait_for_timeout":
            a["timeout_ms"] = STEP_MS
    return out + [{"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500}]


RETRY_ERRORS = ("cleanup_incomplete",)   # REA couldn't confirm the browser closed; the next try usually works


def look(client: mcp.Client, browser: str, url: str, steps: list[str] | None = None, label: str = "") -> Look:
    from . import behaviour
    payload = capture_input(browser, url, _actions(url, steps or []))
    check_input(payload)
    for attempt in (1, 2):
        try:
            result = client.call("capture_browser_scenario", payload, timeout=120)
        except mcp.McpError as e:
            return Look(url, problem=f"not observed: {e}", label=label)
        if not (result.get("isError") and any(code in mcp.text_of(result) for code in RETRY_ERRORS)):
            break
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return Look(url, problem=f"not observed: {mcp.text_of(result)[:300]}", label=label)
    seen = behaviour._browser(evidence, steps)
    shot = seen.png or {}
    at = (behaviour._captured(evidence, "url") or {}).get("url", "") or url
    if seen.exit != "all steps completed":
        return Look(at, text=behaviour.page_text(evidence), png=shot.get("data_base64", ""), problem=seen.exit, label=label)
    return Look(at, text=behaviour.page_text(evidence), png=shot.get("data_base64", ""), label=label)


# --- exploring ---------------------------------------------------------------------------------

def explore(client: mcp.Client, browser: str, start: str, journeys: list[list[str]] | None = None,
            max_pages: int = MAX_PAGES, robots: Robots | None = None, get=_get) -> Exploration:
    """Same-site pages from `start`, breadth first, two links deep; then each journey, with a
    screenshot after every step (each step is replayed from the start: the screens of a journey
    that stops show where)."""
    parts = urllib.parse.urlsplit(start)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InspireError(f"{start} isn't a web address (https://...)")
    origin = f"{parts.scheme}://{parts.netloc}"
    robots = robots or Robots(origin, get)
    ex = Exploration(start=start)
    if robots.note:
        ex.notes.append(robots.note)
    queue, seen = [(start, 0)], {start}
    while queue and len(ex.pages) < max_pages:
        url, depth = queue.pop(0)
        if not robots.allowed(url):
            ex.skipped.append(url)
            continue
        ui.action(f"inspire: looking at {url}")
        page = look(client, browser, url, label=f"page {len(ex.pages) + 1}")
        ex.pages.append(page)
        if depth >= MAX_DEPTH:
            continue
        try:
            status, ctype, html = get(url)
        except (OSError, ValueError):
            continue
        if status != 200 or "html" not in ctype:
            continue
        for link in same_site_links(html, url):
            if link not in seen:
                seen.add(link)
                queue.append((link, depth + 1))
    for j, steps in enumerate((journeys or [])[:MAX_JOURNEYS], start=1):
        steps = steps[:MAX_STEPS]
        from .steps import StepError
        try:
            gotos = [a["destination"]["url"] for a in _actions(start, steps) if a["action"] == "goto"]
        except StepError as e:   # a mistyped step: say which, run the other journeys
            ex.notes.append(f"journey {j} wasn't run: {e}")
            continue
        blocked = next((u for u in [start, *gotos] if not robots.allowed(u)), None)
        if blocked:
            ex.notes.append(f"journey {j} wasn't run: robots.txt disallows {blocked}")
            continue
        ui.action(f"inspire: journey {j} ({len(steps)} steps)")
        screens = []
        for k in range(1, len(steps) + 1):
            shot = look(client, browser, start, steps[:k], label=f"journey {j}, step {k}")
            screens.append(shot)
            if shot.problem:
                break
        ex.journeys.append(screens)
    return ex


# --- the brief ---------------------------------------------------------------------------------

def _image(png: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}}


def model_input(ex: Exploration, journeys: list[list[str]]) -> list[dict]:
    """What the scout reads: each page's text (untrusted) and screenshot, then each journey's steps
    and screens. At most MAX_IMAGES screenshots, pages first."""
    blocks: list[dict] = [{"type": "text", "text": f"The app: {ex.start}. What a visitor sees of it, from the outside."}]
    images = 0
    for p in ex.pages:
        head = f"\n## {p.label}: {p.url}\n"
        body = f"(not seen: {p.problem})" if p.problem and not p.text else github.untrusted(p.text[:PAGE_CHARS] or "(no readable text)")
        blocks.append({"type": "text", "text": head + body})
        if p.png and images < MAX_IMAGES:
            blocks.append(_image(p.png))
            images += 1
    for j, screens in enumerate(ex.journeys, start=1):
        wanted = journeys[j - 1] if j <= len(journeys) else []
        blocks.append({"type": "text", "text": f"\n## Journey {j}: " + " → ".join(wanted)})
        for s in screens:
            line = f"\n### {s.label}" + (f" (stopped: {s.problem})" if s.problem else "")
            blocks.append({"type": "text", "text": line + "\n" + github.untrusted(s.text[-1500:] or "(no readable text)")})
            if s.png and images < MAX_IMAGES:
                blocks.append(_image(s.png))
                images += 1
    if ex.skipped:
        blocks.append({"type": "text", "text": "\nNot visited (robots.txt): " + ", ".join(ex.skipped[:20])})
    for n in ex.notes:
        blocks.append({"type": "text", "text": f"\nNote: {n}"})
    blocks.append({"type": "text", "text": "\nWrite the inspiration brief."})
    return blocks


def save(root: Path, ex: Exploration) -> Path:
    """The captures, for the founder and the lead: pages/NN.md + .png, journeys/J-K.md + .png."""
    f = folder(root, ex.start)
    for sub in ("pages", "journeys"):
        (f / sub).mkdir(parents=True, exist_ok=True)

    def keep(path: Path, look_: Look):
        path.with_suffix(".md").write_text(f"# {look_.label}\n\n{look_.url}\n\n{look_.problem and 'Stopped: ' + look_.problem + chr(10) * 2}"
                                           f"{look_.text}\n", encoding="utf-8")
        if look_.png:
            path.with_suffix(".png").write_bytes(base64.b64decode(look_.png))

    for i, p in enumerate(ex.pages, start=1):
        keep(f / "pages" / f"{i:02d}", p)
    for j, screens in enumerate(ex.journeys, start=1):
        for k, s in enumerate(screens, start=1):
            keep(f / "journeys" / f"{j}-{k}", s)
    (f / "index.json").write_text(json.dumps({
        "start": ex.start, "pages": [{"label": p.label, "url": p.url, "problem": p.problem} for p in ex.pages],
        "journeys": [[{"label": s.label, "url": s.url, "problem": s.problem} for s in js] for js in ex.journeys],
        "skipped": ex.skipped, "notes": ex.notes}, indent=1), encoding="utf-8")
    return f


def writer(team: Team) -> AgentConfig:
    """Who writes the brief: the scout, else the lead. Never a member who writes code."""
    cfg = team.by_role("scout", required=False) or team.by_role("lead")
    if cfg.role in WRITES_CODE:
        raise InspireError(f"{cfg.name} writes code, so it can't read another app's captures")
    return cfg


def run(team: Team, url: str, journeys: list[list[str]] | None = None, max_pages: int = MAX_PAGES) -> Path:
    """Explore the app, save the captures, and have the scout (or the lead) write the brief.
    Returns the brief's path. The founder must have confirmed for this app (confirm())."""
    from . import agent, behaviour
    journeys = journeys or []
    if not confirmed(team.root, url):
        raise InspireError("confirm first that you use this app and may look at it this way (agent-team inspire asks)")
    server = team.behaviour.server
    if server not in team.mcp:
        raise InspireError(f"[mcp.{server}] isn't set up: run agent-team rea setup")
    browser = behaviour.browser_path(team)
    if not browser:
        raise InspireError("no Chrome or Chromium found; set [behaviour].browser to its path")
    cfg = writer(team)
    with mcp.Client(team.mcp[server], team.root) as client:
        ex = explore(client, browser, url, journeys, max(1, min(max_pages, 50)))
    where = save(team.root, ex)
    if not any(p.text or p.png for p in ex.pages):
        raise InspireError("nothing of the app could be seen: " + "; ".join(
            [p.problem for p in ex.pages[:3]] + ex.notes + ([f"robots.txt disallows {url}"] if ex.skipped else [])))
    ui.action(f"inspire: {cfg.name} writes the brief")
    scout = agent.make(team, cfg, "inspire")
    text = scout.turn(model_input(ex, journeys))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    brief = where / "brief.md"
    brief.write_text(f"# Inspiration brief: {ex.start}\n\nWritten by {cfg.name} on {stamp} from {len(ex.pages)} pages and "
                     f"{len(ex.journeys)} journeys, seen from the outside.\n\n{text}\n", encoding="utf-8")
    return brief


# --- reading it --------------------------------------------------------------------------------

def apps(root: Path | str) -> list[dict]:
    """Every app explored here: its folder name, address and whether a brief was written."""
    base = Path(root) / ".team" / "inspiration"
    out = []
    for f in sorted(base.iterdir()) if base.is_dir() else []:
        if not f.is_dir():
            continue
        info = json.loads((f / "index.json").read_text(encoding="utf-8")) if (f / "index.json").is_file() else {}
        out.append({"app": f.name, "url": info.get("start", ""), "brief": (f / "brief.md").is_file(),
                    "pages": len(info.get("pages", [])), "journeys": len(info.get("journeys", []))})
    return out


def for_member(team: Team, cfg: AgentConfig) -> str:
    """The briefs (never the captures), for a member who plans. Members who write code are refused:
    what they build comes from the team's own plan, not from another app."""
    if cfg.role in WRITES_CODE:
        raise InspireError(f"{cfg.name} ({cfg.role}) writes code, so it never reads another app's inspiration brief")
    texts = []
    for a in apps(team.root):
        if a["brief"]:
            texts.append((folder(team.root, a["app"]) / "brief.md").read_text(encoding="utf-8"))
    return "\n\n".join(texts)


def forget(root: Path | str, app: str) -> bool:
    import shutil
    f = folder(root, app)
    if not f.is_dir():
        return False
    shutil.rmtree(f)
    return True
