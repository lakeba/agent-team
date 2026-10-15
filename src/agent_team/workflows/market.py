"""market: the marketing member writes a brief, then a website and pitch deck. A fact-checker
checks claims against the code and the lead reviews with screenshots, until approved."""
from __future__ import annotations

import base64
import time

from .. import agent, context, files, screenshots, ui
from ..config import Team


def deliverables(m: dict) -> str:
    brief, site, deck = m.get("brief", "BRIEF.md"), m.get("site", "site/index.html"), m.get("deck", "deck/index.html")
    return f"""All self-contained (no CDNs, web fonts, external images or network requests; inline SVG and
system fonts are fine):
- {brief}: the positioning brief (audience, problem, one-line pitch, three key messages, tone,
  visual direction, claims we may make and where they come from, things we must not say).
- {site} (with its stylesheet next to it): a single landing page that works at 1440px and 390px.
- {deck}: an HTML pitch deck of 8-10 slides, CSS and JS inline. Each slide is a
  <section class="slide">, 16:9 at 1280x720. Arrow keys and space navigate. On load it shows
  slide N for URL hash #N (1-based), else slide 1; the team's screenshot tool depends on this."""


def _with_images(text: str, shots) -> list:
    blocks = [{"type": "text", "text": text}]
    for caption, png in shots:
        data = base64.standard_b64encode(png.read_bytes()).decode()
        blocks += [{"type": "text", "text": caption},
                   {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}]
    return blocks


def run(team: Team, rounds: int = 3, reuse_brief: bool = False) -> bool:
    m = team.project.marketing
    brief, site, deck = m.get("brief", "BRIEF.md"), m.get("site", "site/index.html"), m.get("deck", "deck/index.html")
    mk_cfg, lead_cfg = team.by_role("marketing"), team.by_role("lead")
    fc_cfg = team.by_role("factcheck", required=False) or team.by_role("builder")
    owned = tuple(mk_cfg.owns) or (brief, site.rsplit("/", 1)[0] + "/", deck.rsplit("/", 1)[0] + "/")
    browser = screenshots.find_browser(m.get("browser", ""))
    if not browser:
        ui.warn("no Chromium-family browser found; the lead reviews without screenshots")
    skip, limit = tuple(team.project.context_skip), team.project.context_limit
    marketing_dirs = tuple(p for p in owned if p.endswith("/"))

    code = context.for_topic(team, skip_extra=marketing_dirs)
    spark = agent.make(team, mk_cfg, "marketing", deliverables=deliverables(m), file_format=files.FILE_FORMAT,
                       files=context.for_topic(team, {rel for rel, _ in files.project_files(team.root, only=owned)}))
    lead = agent.make(team, lead_cfg, "review_marketing", deliverables=deliverables(m), files=code)
    checker = agent.make(team, fc_cfg, "factcheck", files=code)
    log = files.Log(team.root, "market", "Marketing")

    review = "VERDICT: APPROVED"
    if not (reuse_brief and (team.root / brief).exists()):
        ui.heading("Stage 1: positioning brief")
        msg = f"Start with the positioning brief, {brief}. Don't build the site or deck yet."
        for _ in range(3):
            draft = spark.turn(msg)
            log.record(f"{mk_cfg.name}: brief", draft, files.write_files(team.root, draft, allowed=owned))
            review = lead.turn(f"{mk_cfg.name}'s positioning brief:\n\n{draft}\n\nReview the brief only.")
            log.record(f"{lead_cfg.name}: brief review", review)
            if files.last_marker(files.VERDICT_RE, review) == "APPROVED":
                break
            msg = f"{lead_cfg.name} reviewed your brief:\n\n{review}\n\nRevise {brief}."

    msg = f"The brief ({brief}) is approved. Follow it. Now build the website and the pitch deck."
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for rnd in range(1, rounds + 1):
        ui.heading(f"=========== Website and deck, round {rnd}/{rounds} ===========")
        build = spark.turn(msg)
        log.record(f"{mk_cfg.name}: build {rnd}", build, files.write_files(team.root, build, allowed=owned))
        shots = screenshots.capture(team.root, site, deck, team.root / files.LOG_DIR / "shots" / f"{stamp}-{rnd}",
                                    browser) if browser else []
        material = files.snapshot(team.root, only=owned, limit=limit)
        check = checker.turn(f"Fact-check this marketing material (round {rnd}):\n\n{material}")
        log.record(f"{fc_cfg.name}: fact-check {rnd}", check)
        review = lead.turn(_with_images(
            f"# {mk_cfg.name}'s note (round {rnd})\n\n{files.strip_files(build)}\n\n# Fact-check\n\n{check}"
            f"\n\n# Current marketing files\n\n{material}\n\n# Screenshots", shots))
        log.record(f"{lead_cfg.name}: review {rnd}", review)
        if files.last_marker(files.VERDICT_RE, review) == "APPROVED":
            ui.heading(f"{lead_cfg.name} approved the website and deck after {rnd} round(s).")
            return True
        msg = _with_images(f"# {lead_cfg.name}'s review\n\n{review}\n\n# Fact-check\n\n{check}\n\n"
                           "Revise the site and deck; output each changed file in full. Screenshots follow.", shots)
    ui.heading(f"Stopped after {rounds} rounds without approval. Log: {log.path}")
    return False
