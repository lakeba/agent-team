"""fix: a builder addresses the review feedback on an open pull request, on that PR's branch.

The devops shift asks the lead to review each PR, and a lead that requests changes leaves the PR
waiting. `fix` closes that loop:
  1. it checks out the PR's branch (never a fork's; the working tree must be clean);
  2. the builder gets the lead's latest review of the PR from the team's own ship log, plus the
     PR's comments marked as untrusted, and changes only what the blocking points need;
  3. tests run, and the lead checks that every blocking point is addressed (a few rounds at most);
  4. only then are the changed files committed and pushed to the same branch, with a comment on
     the PR. The next shift reviews the new head commit, since approvals are tied to a commit.
"""
from __future__ import annotations


from .. import agent, context, files, github, logs, ui
from ..config import Team
from .build import run_tests



def lead_review(team: Team, number: int, lead: str) -> tuple[str, str]:
    """(review text, commit) of the lead's latest review of this PR in the ship log, or ("", "")."""
    from .ship import earlier_review
    return earlier_review(team.root, number, lead, kinds=("review",))


def team_feedback(team: Team, number: int, lead: str, paths: list[str]) -> tuple[str, str]:
    """The lead's latest review and every owner's latest refused sign-off of this PR, as one text,
    with the commit the lead reviewed. Sign-offs that said YES leave nothing to fix."""
    from .ship import earlier_review
    text, lead_sha = earlier_review(team.root, number, lead, kinds=("review",))
    parts = [f"## {lead} (lead review)\n{text}"] if text else []
    for member in team.owners_of(paths):
        signoff, _ = earlier_review(team.root, number, member, kinds=("sign-off",))
        if signoff and files.last_marker(files.SIGNOFF_RE, signoff) == "NO":
            parts.append(f"## {member} (owner sign-off: NO)\n{signoff}")
    return "\n\n".join(parts), lead_sha


def pr_comments(repo: str, number: int) -> str:
    data = github.gh_json("pr", "view", str(number), "-R", repo, "--json", "comments,reviews")
    parts = [f"- {c['author']['login']}: {c['body']}" for c in data.get("comments") or []]
    parts += [f"- {r['author']['login']} (review, {r.get('state', '').lower()}): {r['body']}"
              for r in data.get("reviews") or [] if r.get("body")]
    return "\n".join(parts)


def _discard(team: Team, paths: set[str]) -> None:
    """Undo the builder's unpushed changes: restore tracked files, remove new ones."""
    tracked = set(github.git(team.root, "ls-files", "--", *paths).split()) if paths else set()
    if tracked:
        github.git(team.root, "checkout", "-q", "--", *sorted(tracked))
    for p in paths - tracked:
        (team.root / p).unlink(missing_ok=True)


def run(team: Team, number: int, rounds: int = 2, lead: str = "", builder: str = "") -> bool:
    repo = team.project.repo
    if not repo:
        raise SystemExit("[project].repo is not set (and origin isn't on GitHub), so there's no PR to fix.")
    lead_cfg = team.get(lead) if lead else team.by_role("lead")
    builder_cfg = team.get(builder) if builder else team.by_role("builder")

    info = github.gh_json("pr", "view", str(number), "-R", repo, "--json",
                          "title,body,state,headRefName,headRefOid,isCrossRepository,files")
    if info["state"] != "OPEN":
        raise SystemExit(f"PR #{number} is {info['state'].lower()}; only open PRs can be fixed.")
    if info["isCrossRepository"]:
        raise SystemExit(f"PR #{number} comes from a fork; the team can't push to it. Comment with the review instead.")
    review, reviewed_sha = team_feedback(team, number, lead_cfg.name, [f["path"] for f in info.get("files") or []])
    comments = pr_comments(repo, number)
    if not review and not comments:
        raise SystemExit(f"No review of PR #{number} yet: run a devops shift (agent-team ship) first.")
    if github.git(team.root, "status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit("The working tree has uncommitted changes; commit or stash them first.")

    branch, head = info["headRefName"], info["headRefOid"]
    start = github.git(team.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    github.git(team.root, "fetch", "-q", "origin", branch)
    github.git(team.root, "checkout", "-q", "-B", branch, f"origin/{branch}")
    ui.action(f"checked out {branch} at {head[:10]} (PR #{number})")
    stale = f"\n(This review was of commit {reviewed_sha[:10]}; the PR is now at {head[:10]}.)" if reviewed_sha and not head.startswith(reviewed_sha) else ""

    log = files.Log(team.root, "fix", f"Fix PR #{number}: {info['title']}")
    pr_paths = {f["path"] for f in info.get("files") or []}
    focus = context.Focus(team, None) if not context.needs_focus(team) else context.Focus(team, context.default_paths(team) | pr_paths)
    worker = agent.make(team, builder_cfg, "builder", file_format=files.FILE_FORMAT, label_suffix=f" · PR #{number}")
    checker = agent.make(team, lead_cfg, "lead", file_format=files.FILE_FORMAT, label_suffix=f" · PR #{number} fix")
    feedback = (f"# The team's latest review of this PR (from its own log){stale}\n\n{review or '(none in the log)'}"
                f"\n\n# Comments on the PR\n" + (github.untrusted(comments) if comments else "(none)"))
    task = (f"PR #{number} \"{info['title']}\" (branch {branch}) received review feedback. Address every "
            f"BLOCKING point; non-blocking notes only if trivial and safe. Change nothing else.\n\n{feedback}")

    ui.heading(f"Fix PR #{number}: {info['title']}")
    touched: set[str] = set()
    note, approved = task, False
    try:
        for rnd in range(1, rounds + 1):
            ui.heading(f"=========== Round {rnd}/{rounds} ===========")
            reply = worker.turn(f"{note}\n\n# Current files on the PR branch\n\n{focus.render()}")
            written = files.write_files(team.root, reply)
            touched.update(written)
            focus.add(written)
            focus.add_from_reply(reply)
            log.record(f"{builder_cfg.name}: fix {rnd}", reply, written)
            tests = run_tests(team)
            if tests:
                ui.say(tests)
                log.record(f"Tests: fix {rnd}", tests)
            check = checker.turn(
                f"{task}\n\n# {builder_cfg.name}'s message\n\n{files.strip_files(reply)}\n\nFiles changed: "
                f"{', '.join(written) or 'none'}\n\n# Current files on the PR branch\n\n{focus.render()}{tests}\n\n"
                "Check only whether every blocking point of your review is now addressed, without new problems. "
                "Don't write PLAN.md. End with VERDICT: APPROVED or VERDICT: CHANGES.")
            log.record(f"{lead_cfg.name}: check {rnd}", check)
            if files.last_marker(files.VERDICT_RE, check) == "APPROVED":
                approved = True
                break
            note = f"{task}\n\n# {lead_cfg.name}'s check of your last attempt\n\n{check}{tests}"

        if not approved or not touched:
            why = "the lead didn't confirm the fix" if not approved else "the builder changed no files"
            ui.heading(f"Not pushed: {why}. The branch is left as it was.")
            _discard(team, touched)
            return False

        paths = sorted(touched)
        github.git(team.root, "add", "--", *paths)
        github.git(team.root, "commit", "-q", "-m", f"Address review feedback on #{number}",
                   "-m", f"Fixed by {builder_cfg.name}, checked by {lead_cfg.name} (agent-team fix).")
        github.git(team.root, "push", "-q", "origin", f"HEAD:{branch}")
        new_head = github.git(team.root, "rev-parse", "HEAD").strip()
        github.gh("pr", "comment", str(number), "-R", repo, "--body",
                  f"Addressed the review feedback in {new_head[:10]}: {', '.join(f'`{p}`' for p in paths)}.\n\n"
                  f"{files.strip_files(reply).strip()[:1500]}\n\n— {builder_cfg.name} (builder agent, automated); "
                  f"{lead_cfg.name} confirmed the blocking points are addressed. The next devops shift reviews the new commit.")
        ui.action(f"pushed {new_head[:10]} to {branch} and commented on PR #{number}")
        log.record(f"{builder_cfg.name}: action", f"pushed {new_head[:10]} to {branch}")
        return True
    finally:
        if start and start != branch and start != "HEAD":
            github.git(team.root, "checkout", "-q", start, check=False)
        ui.say(f"Log: {log.path}")
