"""autopilot: work through the roadmap, a PR at a time, until a milestone is done.

Each cycle does one thing:
  * if the team has open PRs (branches named team/...), run a devops shift: it reviews them, has
    the builder fix what the lead asks for, and merges what's approved;
  * otherwise the lead picks the next PR-sized task from ROADMAP.md, and `build` builds it as a PR.
It stops when the lead says the milestone is done, when the open PRs stop moving for two shifts,
when a build isn't approved, after --max-cycles, or when a spend limit is reached. Every rule of
the normal workflows still applies: approvals are tied to commits, releases follow
[project].release, and nothing merges without green CI.
"""
from __future__ import annotations

import re

from .. import agent, files, github, schedule, ui, usage
from ..config import Team
from . import build, ship

NEXT_RE = re.compile(r"^TASK:\s*(.+?)\s*$", re.M)
BRANCH_RE = re.compile(r"^BRANCH:\s*(.+?)\s*$", re.M)
DONE_RE = re.compile(r"^DONE:\s*(.+?)\s*$", re.M)

PICK = """You are choosing the team's next pull request{scope}.

# ROADMAP.md
{roadmap}

# Recently merged pull requests
{merged}

# Open issues
{issues}

Pick the single next task that isn't done yet, in roadmap order, small enough for one PR (a few
rounds of building). Check the merged PRs so you don't repeat finished work. Reply with:
TASK: <one paragraph: what to build, which roadmap item it completes, and anything the builder must not miss>
BRANCH: team/<short-slug>
or, if {done_when}:
DONE: <why>"""


def team_prs(repo: str) -> list[dict]:
    prs = github.gh_json("pr", "list", "-R", repo, "--state", "open", "--limit", "50", "--json",
                         "number,title,headRefName,headRefOid,isCrossRepository") or []
    return [p for p in prs if p["headRefName"].startswith("team/") and not p["isCrossRepository"]]


def pick_next(team: Team, lead, milestone: str) -> tuple[str, str, str]:
    """(task, branch, done_reason) from the lead; exactly one of task or done_reason is set."""
    repo = team.project.repo
    roadmap_path = team.root / "ROADMAP.md"
    roadmap = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else "(no ROADMAP.md)"
    merged = github.gh_json("pr", "list", "-R", repo, "--state", "merged", "--limit", "20",
                            "--json", "number,title") or []
    issues = github.gh_json("issue", "list", "-R", repo, "--state", "open", "--limit", "20",
                            "--json", "number,title") or []
    scope = f" within milestone {milestone}" if milestone else ""
    done_when = f"every item of {milestone} is already merged" if milestone else "the whole roadmap is done"
    reply = lead.turn(PICK.format(
        scope=scope, roadmap=roadmap[:30_000], done_when=done_when,
        merged="\n".join(f"- #{p['number']} {p['title']}" for p in merged) or "(none)",
        issues=github.untrusted("\n".join(f"- #{i['number']} {i['title']}" for i in issues)) if issues else "(none)"))
    done = DONE_RE.search(reply)
    task, branch = NEXT_RE.search(reply), BRANCH_RE.search(reply)
    if done and not task:
        return "", "", done.group(1)
    if not task:
        return "", "", ""
    slug = branch.group(1) if branch else "team/autopilot"
    slug = re.sub(r"[^A-Za-z0-9._/-]+", "-", slug).strip("-/")
    if not slug.startswith("team/"):
        slug = "team/" + slug
    return task.group(1), slug, ""


def default_branch(root) -> str:
    ref = github.git(root, "rev-parse", "--abbrev-ref", "origin/HEAD", check=False).strip()
    return ref.removeprefix("origin/") if ref.startswith("origin/") else "main"


def _free_branch(root, name: str) -> str:
    existing = set(github.git(root, "branch", "-a", "--format=%(refname:short)", check=False).split())
    candidate, n = name, 2
    while candidate in existing or f"origin/{candidate}" in existing:
        candidate, n = f"{name}-{n}", n + 1
    return candidate


def run(team: Team, milestone: str = "", max_cycles: int = 6, rounds: int = 3, max_steps: int = 30) -> bool:
    repo = team.project.repo
    if not repo:
        raise SystemExit("[project].repo is not set (and origin isn't on GitHub); autopilot works through pull requests.")
    lead_cfg = team.by_role("lead")
    team.by_role("builder")
    team.by_role("devops")
    log = files.Log(team.root, "autopilot", f"Autopilot{': ' + milestone if milestone else ''}")
    autopilot_run = usage.current_run()
    lead = agent.make(team, lead_cfg, "lead", file_format=files.FILE_FORMAT, label_suffix=" · autopilot")
    stuck_shifts, last_open = 0, None
    outcome = False

    def note(text: str) -> None:
        ui.heading(text)
        usage.set_run(autopilot_run)
        log.record("Autopilot", text)

    with schedule.lock(team.root, "autopilot"):
        for cycle in range(1, max_cycles + 1):
            github.git(team.root, "fetch", "-q", "origin", check=False)
            open_prs = team_prs(repo)
            if open_prs:
                state = {(p["number"], p["headRefOid"]) for p in open_prs}
                stuck_shifts = stuck_shifts + 1 if state == last_open else 0
                if stuck_shifts >= 2:
                    note(f"Stopped: the team's open PRs ({', '.join('#' + str(p['number']) for p in open_prs)}) "
                         "didn't move in two shifts. They need a person.")
                    break
                last_open = state
                note(f"Cycle {cycle}/{max_cycles}: a devops shift for {len(open_prs)} open PR(s)")
                with schedule.lock(team.root, "ship"):
                    ship.run(team, max_steps)
                continue

            if github.git(team.root, "status", "--porcelain", "--untracked-files=no").strip():
                note("Stopped: the working tree has uncommitted changes; commit or stash them first.")
                break
            main = default_branch(team.root)
            github.git(team.root, "checkout", "-q", main, check=False)
            github.git(team.root, "pull", "-q", "--ff-only", check=False)
            usage.set_run(autopilot_run)
            task, branch, done = pick_next(team, lead, milestone)
            if done:
                note(f"Done: {done}")
                outcome = True
                break
            if not task:
                note("Stopped: the lead didn't name a next task or say the milestone is done.")
                break
            branch = _free_branch(team.root, branch)
            note(f"Cycle {cycle}/{max_cycles}: building on {branch}: {task}")
            approved = build.run(team, task, rounds, branch=branch, open_pr=True)
            github.git(team.root, "checkout", "-q", main, check=False)
            if not approved:
                note(f"Stopped: the build on {branch} wasn't approved after {rounds} rounds. See .team/logs/build.md.")
                break
        else:
            note(f"Stopped after {max_cycles} cycles (--max-cycles). Run autopilot again to continue.")
    ui.say(f"Log: {log.path}")
    return outcome
