"""build: the lead plans a task, a builder implements it, tests run, the lead reviews until approved.

With --branch/--pr it also creates the branch, commits only the files the team wrote, pushes,
and opens the pull request for the devops shift to review.
"""
from __future__ import annotations

import subprocess

from .. import agent, files, github, ui
from ..config import Team


def run_tests(team: Team) -> str:
    cmd = team.project.test_command
    if not cmd:
        return ""
    try:
        r = subprocess.run(cmd, shell=True, cwd=team.root, capture_output=True, text=True, timeout=600)
        out = (r.stdout + r.stderr)[-8000:]
        return f"\n\n## Test output (`{cmd}`, exit code {r.returncode})\n```\n{out}\n```"
    except subprocess.TimeoutExpired:
        return f"\n\n## Test output (`{cmd}`)\nTimed out after 600 seconds."


def run(team: Team, task: str, rounds: int = 3, lead: str = "", builder: str = "",
        branch: str = "", open_pr: bool = False) -> bool:
    lead_cfg = team.get(lead) if lead else team.by_role("lead")
    builder_cfg = team.get(builder) if builder else team.by_role("builder")
    skip, limit = tuple(team.project.context_skip), team.project.context_limit

    if branch:
        if github.git(team.root, "status", "--porcelain", "--untracked-files=no").strip():
            raise SystemExit("The working tree has uncommitted changes; commit or stash them first.")
        github.git(team.root, "checkout", "-b", branch)
        ui.action(f"created branch {branch}")

    planner = agent.make(team, lead_cfg, "lead", file_format=files.FILE_FORMAT)
    worker = agent.make(team, builder_cfg, "builder", file_format=files.FILE_FORMAT)
    log = files.Log(team.root, "build", f"Build: {task}")
    touched: set[str] = set()

    ui.heading(f"Build: {task}")
    current = files.snapshot(team.root, skip=skip, limit=limit)
    plan = planner.turn(f"Task: {task}\n\nWrite PLAN.md for {builder_cfg.name}.\n\n# Current project files\n\n{current}")
    written = files.write_files(team.root, plan, allowed=("PLAN.md",))
    if "PLAN.md" not in written:   # a plan sent as plain text instead of a <file> block
        (team.root / "PLAN.md").write_text(files.strip_files(plan).strip() + "\n", encoding="utf-8")
        written = ["PLAN.md"]
    touched.update(written)
    log.record(f"{lead_cfg.name}: plan", plan, written)

    note = f"Task: {task}\n\nStart building from PLAN.md."
    approved = False
    for rnd in range(1, rounds + 1):
        ui.heading(f"=========== Round {rnd}/{rounds} ===========")
        build = worker.turn(f"{note}\n\n# Current project files\n\n{files.snapshot(team.root, skip=skip, limit=limit)}")
        written = files.write_files(team.root, build)
        touched.update(written)
        log.record(f"{builder_cfg.name}: round {rnd}", build, written)
        tests = run_tests(team)
        if tests:
            ui.say(tests)
            log.record(f"Tests: round {rnd}", tests)

        review = planner.turn(
            f"# {builder_cfg.name}'s message (round {rnd})\n\n{files.strip_files(build)}"
            f"\n\nFiles written this round: {', '.join(written) or 'none'}"
            f"\n\n# Current project files\n\n{files.snapshot(team.root, skip=skip, limit=limit)}{tests}")
        plan_files = files.write_files(team.root, review, allowed=("PLAN.md",))
        touched.update(plan_files)
        log.record(f"{lead_cfg.name}: review {rnd}", review, plan_files)
        if files.last_marker(files.VERDICT_RE, review) == "APPROVED":
            approved = True
            ui.heading(f"{lead_cfg.name} approved after {rnd} round(s).")
            break
        note = f"# {lead_cfg.name}'s review\n\n{review}{tests}"
    else:
        ui.heading(f"Stopped after {rounds} rounds without approval.")

    if approved and open_pr:
        open_pull_request(team, task, sorted(touched), lead_cfg.name, builder_cfg.name)
    ui.say(f"Log: {log.path}")
    return approved


def open_pull_request(team: Team, task: str, paths: list[str], lead: str, builder: str) -> str:
    if not team.project.repo:
        raise SystemExit("[project].repo is not set, so no pull request can be opened.")
    branch = github.git(team.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch in ("main", "master"):
        raise SystemExit("Refusing to commit to the default branch; use --branch.")
    github.git(team.root, "add", "--", *paths)
    title = task if len(task) <= 70 else task[:67] + "..."
    github.git(team.root, "commit", "-q", "-m", title, "-m",
               f"Planned by {lead}, built by {builder} (agent-team).")
    github.git(team.root, "push", "-q", "-u", "origin", branch)
    body = (f"{task}\n\nPlanned by {lead}, built by {builder}; the lead approved the result and the "
            f"project's tests ran each round.\n\nFiles: {', '.join(f'`{p}`' for p in paths)}\n\n"
            "Opened by agent-team. The devops shift reviews, gets sign-offs and merges.")
    url = github.gh("pr", "create", "-R", team.project.repo, "--head", branch, "--title", title,
                    "--body", body).strip()
    ui.action(f"opened {url}")
    return url
