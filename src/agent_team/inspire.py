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
import os
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
    asked: list[list[str]] = field(default_factory=list)  # the journeys the founder asked for
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
        self.links: list[list[str]] = []    # [href, its text]
        self._open: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            self._open = [href, ""] if href else None
            if self._open:
                self.links.append(self._open)

    def handle_data(self, data):
        if self._open is not None:
            self._open[1] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self._open = None


def same_site_links(html: str, base: str, with_text: bool = False) -> list:
    """The page's links that stay on its origin, without fragments, files or duplicates (with each
    one's text when asked). Only <a href> is read; the page's scripts never are."""
    p = _Links()
    try:
        p.feed(html)
    except Exception:   # a broken page still gives the links found so far
        pass
    origin = urllib.parse.urlsplit(base)
    out, seen = [], {}
    for href, text in p.links:
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        u = urllib.parse.urlsplit(urllib.parse.urljoin(base, href))
        if (u.scheme, u.netloc) != (origin.scheme, origin.netloc):
            continue
        if u.path.lower().endswith(SKIP_EXT):
            continue
        path = re.sub(r"/index\.html?$", "/", u.path or "/")   # the same page as its folder
        clean = urllib.parse.urlunsplit((u.scheme, u.netloc, path, u.query, ""))
        text = " ".join(text.split())
        if clean not in seen:
            seen[clean] = len(out)
            out.append([clean, text])
        else:
            out[seen[clean]][1] += " " + text
    return [tuple(x) for x in out] if with_text else [x[0] for x in out]


# What a founder learns most from, first. A word in the link's address or text scores its weight.
PAGE_WORDS = {
    3: ("pricing", "price", "prices", "plans", "plan"),
    2: ("features", "feature", "product", "products", "demo", "tour", "how-it-works", "how it works", "docs",
        "documentation", "guide", "guides", "getting-started", "get started"),
    1: ("about", "help", "faq", "solutions", "use-cases", "integrations", "changelog", "customers"),
}
LOW_WORDS = ("blog", "login", "log-in", "signin", "sign-in", "register", "signup", "sign-up", "privacy", "terms",
             "legal", "cookie", "careers", "jobs", "press", "tag", "category", "author")


def score(url: str, text: str = "") -> int:
    """How much a page likely tells about the app: pricing first, then features, docs and demos; a
    blog post, a sign-in or a legal page last."""
    path = urllib.parse.urlsplit(url).path.lower()
    words = set(re.split(r"[^a-z0-9]+", path)) | set(re.split(r"[^a-z0-9]+", text.lower()))
    hay = f"{path} {text.lower()}"
    best = max((w for w, names in PAGE_WORDS.items() for n in names if (n in words if " " not in n and "-" not in n else n in hay)),
               default=0)
    if words & set(LOW_WORDS) or any(w in path for w in ("/blog/", "/tag/", "/category/")):
        best -= 2
    return best


# --- REA ---------------------------------------------------------------------------------------

def capture_input(browser: str, url: str, actions: list[dict], each_step: bool = False) -> dict:
    """The one shape of REA call this module makes: a headless browser, the steps, and CAPTURE
    (after every step for a journey, at the end for a page)."""
    capture = {"after_each_step": list(CAPTURE), "at_end": ["url"]} if each_step else {"at_end": list(CAPTURE)}
    return {"browser": {"mode": "launch", "executable_path": browser, "headless": True},
            "start_url": {"url": url}, "actions": actions, "capture": capture}


def check_input(payload: dict) -> None:
    """Refuse any call asking REA for more than CAPTURE (scripts, events, network...)."""
    cap = payload.get("capture") or {}
    if set(cap) - {"at_end", "after_each_step"} or any(set(cap.get(k) or []) - set(CAPTURE) for k in cap):
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
RETRY_WAIT = 5                           # seconds before that try


def _scenario(client: mcp.Client, payload: dict) -> tuple[dict | None, str]:
    """(REA's evidence, or None with why it wasn't observed), retrying once when REA asks for it."""
    import time
    check_input(payload)
    for attempt in (1, 2):
        if attempt == 2:
            time.sleep(RETRY_WAIT)
        try:
            result = client.call("capture_browser_scenario", payload, timeout=120)
        except mcp.McpError as e:
            return None, f"not observed: {e}"
        if not (result.get("isError") and any(code in mcp.text_of(result) for code in RETRY_ERRORS)):
            break
    evidence = result.get("structuredContent")
    if result.get("isError") or not isinstance(evidence, dict):
        return None, f"not observed: {mcp.text_of(result)[:300]}"
    return evidence, ""


def look(client: mcp.Client, browser: str, url: str, steps: list[str] | None = None, label: str = "") -> Look:
    """One page as a visitor sees it, after `steps` if any."""
    from . import behaviour
    evidence, problem = _scenario(client, capture_input(browser, url, _actions(url, steps or [])))
    if evidence is None:
        return Look(url, problem=problem, label=label)
    seen = behaviour._browser(evidence, steps)
    shot = seen.png or {}
    at = (behaviour._captured(evidence, "url") or {}).get("url", "") or url
    problem = "" if seen.exit == "all steps completed" else seen.exit
    return Look(at, text=behaviour.page_text(evidence), png=shot.get("data_base64", ""), problem=problem, label=label)


def _artifact(step: dict, key: str):
    a = (step.get("artifacts") or {}).get(key) or {}
    return a.get("value") if a.get("state") == "captured" else None


def link_addresses(text: str, name: str) -> list[str]:
    """The addresses of the links called `name` in an accessibility snapshot (REA's aria text:
    `link "Pricing":` with `- /url: /#pricing` under it)."""
    pattern = rf'^(\s*)- link "{re.escape(name)}"(?: \[[^\]]*\])*:\s*\n\1\s+- /url: (\S+)'
    return [m.group(2) for m in re.finditer(pattern, text, re.M)]


def _repeated(error: str) -> bool:
    return "strict mode violation" in (error or "")


SETTLE_MS = 1500        # after each journey step: wait, capture, and compare...
SETTLE_TRIES = 4        # ...up to this many times, until two screenshots in a row match


def _with_settling(actions: list[dict]) -> list[dict]:
    """A journey's actions, each followed by SETTLE_TRIES short waits. REA captures after every one,
    so the step's screen can be the first that stopped changing (a page still loading, a spinner,
    a dashboard filling in), with no page scripts involved."""
    out = []
    for a in actions:
        out.append(a)
        if a["step_id"].startswith("step-"):
            n = a["step_id"].removeprefix("step-")
            out += [{"step_id": f"settle-{n}-{i}", "action": "wait_for_timeout", "duration_ms": SETTLE_MS}
                    for i in range(1, SETTLE_TRIES + 1)]
    return out


def _settled(by_id: dict, k: int) -> tuple[dict, bool]:
    """Step k's capture once the screen stopped changing (or the last one REA took), and whether it did."""
    chain = [by_id[f"step-{k}"]] + [by_id[i] for i in (f"settle-{k}-{t}" for t in range(1, SETTLE_TRIES + 1)) if i in by_id]
    sha = [(_artifact(c, "screenshot") or {}).get("sha256") for c in chain]
    for i in range(1, len(chain)):
        if sha[i] and sha[i] == sha[i - 1]:
            return chain[i - 1], True
    return chain[-1], len(chain) == 1


def _screens(evidence: dict, url: str, steps: list[str], j: int, notes: list[str] | None = None) -> list[Look]:
    """A Look after each journey step REA ran, once its screen settled, up to the one that failed."""
    by_id = {str(s.get("step_id")): s for s in (evidence.get("normalized_result") or {}).get("steps") or []}
    screens = []
    for k, line in enumerate(steps, start=1):
        s = by_id.get(f"step-{k}")
        if s is None:
            break
        status = s.get("status") or "completed"
        problem = "" if status == "completed" else f"step {k} ({line}) {status}: {str(s.get('error') or '')[:400]}"
        if not problem:
            s, still = _settled(by_id, k)
            if not still and notes is not None:
                notes.append(f"journey {j}, step {k}: the screen was still changing {SETTLE_MS * SETTLE_TRIES // 1000} seconds "
                             "later (a slow load or an animation); its last screenshot is shown")
        shot = _artifact(s, "screenshot") or {}
        screens.append(Look((_artifact(s, "url") or {}).get("url", "") or url, text=(_artifact(s, "accessibility") or {}).get("text", ""),
                            png=shot.get("data_base64", ""), problem=problem, label=f"journey {j}, step {k}"))
        if problem:
            break
    return screens


def journey(client: mcp.Client, browser: str, start: str, steps: list[str], j: int, robots: Robots,
            notes: list[str]) -> list[Look]:
    """One journey in one browser run, with a screenshot after every step once its screen settled.
    A click on a link whose name the page repeats (a header and a footer "Pricing") goes to that
    link's address instead, when it stays on the site and robots.txt allows it."""
    actions = _actions(start, steps)[:-1]   # the settling waits replace the final pause
    origin = urllib.parse.urlsplit(start)[:2]
    for _ in range(len(steps) + 1):
        evidence, problem = _scenario(client, capture_input(browser, start, _with_settling(actions), each_step=True))
        if evidence is None:
            return [Look(start, problem=problem, label=f"journey {j}, step 1")]
        found_notes: list[str] = []
        screens = _screens(evidence, start, steps, j, found_notes)
        if not screens:   # REA stopped before the first step
            return [Look(start, problem="not observed: no step was run", label=f"journey {j}, step 1")]
        last = screens[-1]
        k = len(screens)
        a = actions[k - 1]
        loc = a.get("locator") or {}
        failed = next((s for s in (evidence.get("normalized_result") or {}).get("steps") or [] if s.get("step_id") == f"step-{k}"), {})
        if not (last.problem and a["action"] == "click" and loc.get("role") == "link" and _repeated(str(failed.get("error")))):
            notes += found_notes
            return screens
        before = screens[-2].text if k > 1 else (_artifact((evidence["normalized_result"]["steps"] or [{}])[0], "accessibility") or {}).get("text", "")
        found = link_addresses(before, loc.get("name", "")) or re.findall(r'<a [^>]*href="([^"]+)"', str(failed.get("error")))
        href = urllib.parse.urljoin(last.url or start, found[0]) if found else ""
        if not href or urllib.parse.urlsplit(href)[:2] != origin:
            last.problem += f" (the links named {loc.get('name')!r} lead off the site, so they weren't followed)" if href else ""
            notes += found_notes
            return screens
        if not robots.allowed(href):
            last.problem += f" (robots.txt disallows {href}, where the link leads)"
            notes += found_notes
            return screens
        notes.append(f"journey {j}, step {k} went to {href}, the address of the {loc.get('name')!r} link: the capture "
                     "tool can only click a link whose name appears once on a page (this one appears more than once, "
                     "as is common in a header and footer)")
        actions[k - 1] = {"step_id": a["step_id"], "action": "goto", "destination": {"url": href}, "wait_until": "load",
                          "timeout_ms": STEP_MS}
    return screens


# --- exploring ---------------------------------------------------------------------------------

def explore(client: mcp.Client, browser: str, start: str, journeys: list[list[str]] | None = None,
            max_pages: int = MAX_PAGES, robots: Robots | None = None, get=_get) -> Exploration:
    """Same-site pages from `start`, two links deep, the likeliest useful ones first (pricing,
    features, docs, a demo); then each journey, with a screenshot after every step."""
    import heapq
    parts = urllib.parse.urlsplit(start)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InspireError(f"{start} isn't a web address (https://...)")
    origin = f"{parts.scheme}://{parts.netloc}"
    robots = robots or Robots(origin, get)
    ex = Exploration(start=start, asked=[list(j) for j in (journeys or [])[:MAX_JOURNEYS]])
    if robots.note:
        ex.notes.append(robots.note)
    queue, seen, order = [(0, 0, 0, start)], {start}, 0
    while queue and len(ex.pages) < max_pages:
        _, depth, _, url = heapq.heappop(queue)
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
        for link, text in same_site_links(html, url, with_text=True):
            if link not in seen:
                seen.add(link)
                order += 1
                heapq.heappush(queue, (-score(link, text), depth + 1, order, link))
    from .steps import StepError
    for j, steps in enumerate((journeys or [])[:MAX_JOURNEYS], start=1):
        steps = steps[:MAX_STEPS]
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
        ex.journeys.append(journey(client, browser, start, steps, j, robots, ex.notes))
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
    if ex.notes:   # about the capture, not the app: never gaps or friction
        blocks.append({"type": "text", "text": "\nHow the capture went (about the team's tools, not the app: never list "
                                               "these as the app's gaps or friction):\n" + "\n".join(f"- {n}" for n in ex.notes)})
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
        "skipped": ex.skipped, "notes": ex.notes, "asked": ex.asked}, indent=1), encoding="utf-8")
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
    provider = team.providers.get(cfg.provider)
    if provider and provider.kind == "anthropic" and not (team.secret(provider) or os.environ.get("ANTHROPIC_API_KEY")):
        raise InspireError(f"{cfg.name} writes the brief with Claude, and no Anthropic key is set: save it with "
                           "agent-team keys set ANTHROPIC_API_KEY in your own terminal (nothing was explored)")
    with mcp.Client(team.mcp[server], team.root) as client:
        ex = explore(client, browser, url, journeys, max(1, min(max_pages, 50)))
    where = save(team.root, ex)
    if not any(p.text or p.png for p in ex.pages):
        raise InspireError("nothing of the app could be seen: " + "; ".join(
            [p.problem for p in ex.pages[:3]] + ex.notes + ([f"robots.txt disallows {url}"] if ex.skipped else [])))
    ui.action(f"inspire: {cfg.name} writes the brief")
    scout = agent.make(team, cfg, "inspire")
    try:
        text = scout.turn(model_input(ex, journeys))
    except Exception as e:   # the model couldn't be reached: the captures are kept for the next try
        raise InspireError(f"the captures are saved in {where.relative_to(team.root)}, but {cfg.name} couldn't write "
                           f"the brief: {str(e)[:300]}") from e
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
        url = info.get("start", "")
        if not url and (f / "confirmed.json").is_file():   # confirmed, not explored yet
            url = json.loads((f / "confirmed.json").read_text(encoding="utf-8")).get("url", "")
        when = max((g.stat().st_mtime for g in (f / "index.json", f / "brief.md") if g.is_file()), default=None)
        out.append({"app": f.name, "url": url, "brief": (f / "brief.md").is_file(),
                    "confirmed": (f / "confirmed.json").is_file(),
                    "pages": len(info.get("pages", [])), "journeys": len(info.get("journeys", [])),
                    "updated": datetime.fromtimestamp(when, timezone.utc).isoformat(timespec="seconds") if when else None})
    return out


SHOT_RE = re.compile(r"(pages/\d{2}|journeys/\d{1,2}-\d{1,2})\.png")


def details(root: Path | str, app: str) -> dict:
    """One app, for the owner's screens: the brief, every page and journey step with its address,
    problem and screenshot name, and the notes. Raises InspireError for an app that isn't here."""
    f = folder(root, app)
    if not f.is_dir():
        raise InspireError(f"no app called {app} here")
    info = json.loads((f / "index.json").read_text(encoding="utf-8")) if (f / "index.json").is_file() else {}

    def with_shot(item: dict, name: str) -> dict:
        return {**item, "shot": name if (f / name).is_file() else None}

    return {"app": app, "url": info.get("start", ""), "confirmed": (f / "confirmed.json").is_file(),
            "brief": (f / "brief.md").read_text(encoding="utf-8") if (f / "brief.md").is_file() else None,
            "pages": [with_shot(p, f"pages/{i:02d}.png") for i, p in enumerate(info.get("pages", []), start=1)],
            "journeys": [[with_shot(s, f"journeys/{j}-{k}.png") for k, s in enumerate(js, start=1)]
                         for j, js in enumerate(info.get("journeys", []), start=1)],
            "skipped": info.get("skipped", []), "notes": info.get("notes", []), "asked": info.get("asked", [])}


def shot(root: Path | str, app: str, name: str) -> Path | None:
    """A screenshot's file, only by the names details() gives (pages/NN.png, journeys/J-K.png)."""
    if not SHOT_RE.fullmatch(name or ""):
        return None
    path = folder(root, app) / name
    return path if path.is_file() else None


def check_url(url: str) -> str:
    """A web address inspire may start from, or InspireError."""
    url = (url or "").strip() if isinstance(url, str) else ""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(url) > 2000 or any(c.isspace() for c in url):
        raise InspireError("the app's address must be a web address (https://...)")
    return url


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
