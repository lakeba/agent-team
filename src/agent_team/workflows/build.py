"""build: the lead plans a task, builders implement it, tests run, the lead reviews until approved.

Optional members join in when the team has them (skip any with --skip):
  * qa: writes tests for the plan before anyone builds, so the builders work to them;
  * security: reviews the result once the lead approves; a NO sends it back for another round;
  * docs: updates the README, docs and changelog after approval.
With --parallel and more than one builder, the lead splits the plan into parts, each owned by
one builder, and the builders work on their parts at the same time.

With --branch/--pr it also creates the branch, commits only the files the team wrote, pushes,
and opens the pull request for the devops shift to review.
"""
from __future__ import annotations

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .. import agent, behaviour, context, files, github, guards, memory, quality, review_tools, routing, sessions, ui
from ..config import SCENARIOS_FILE, AgentConfig, Team

TEST_PREFIXES = ("tests/", "test/", "spec/", "__tests__/", "test_", "Tests/", "Test/")
DOC_PREFIXES = ("README", "docs/", "CHANGELOG.md", "CONTRIBUTING.md")
PART_RE = re.compile(r"^PART:\s*([^|\n]+?)\s*\|\s*([^|\n]*?)\s*\|\s*(.+?)\s*$", re.M)
OPTIONAL = ("qa", "security", "docs", "journeys")   # journeys: the behaviour checks the task needs

PARALLEL_NOTE = """
The team has {count} builders who will work at the same time: {names}. After PLAN.md, add one
line per builder assigning a part, with the path prefixes that builder alone may change:
PART: <builder name> | <path prefixes, comma-separated> | <what this builder does>
Parts must not share files. Shared files (for example a common module) belong to one part."""


@dataclass
class Part:
    builder: AgentConfig
    prefixes: tuple[str, ...] = ()       # empty: may change anything (a single builder)
    what: str = ""
    worker: agent.Agent | None = field(default=None, repr=False)


def run_tests(team: Team) -> str:
    from .init import test_command_for
    cmd = test_command_for(team.root, team.project.test_command)   # a project that started empty: once tests exist
    if not cmd:
        return ""
    from .. import sandbox
    where = "" if team.sandbox.mode != "container" else f", sandboxed: {sandbox.describe(team)}"
    try:
        code, out = sandbox.run(team, cmd)
        return f"\n\n## Test output (`{cmd}`{where}, exit code {code})\n```\n{out[-8000:]}\n```"
    except subprocess.TimeoutExpired:
        return f"\n\n## Test output (`{cmd}`{where})\nTimed out after 600 seconds."
    except sandbox.SandboxError as e:
        raise SystemExit(f"Can't run the tests: {e}. Install it, or set [sandbox].mode = \"off\".")


def parse_parts(team: Team, text: str, builders: list[AgentConfig]) -> list[Part]:
    """The PART lines of a plan, for builders that exist, with non-overlapping prefixes."""
    by_name = {b.name.lower(): b for b in builders}
    parts, claimed = [], set()
    for name, prefixes, what in PART_RE.findall(files.strip_files(text)):
        b = by_name.get(name.strip().lower())
        pre = tuple(p.strip().strip("`") for p in prefixes.split(",") if p.strip())
        if not b or not pre or b.name in claimed:
            continue
        if any(x.startswith(y) or y.startswith(x) for p in parts for x in p.prefixes for y in pre):
            ui.warn(f"part for {b.name} overlaps another part's paths; ignored")
            continue
        claimed.add(b.name)
        parts.append(Part(b, pre, what.strip()))
    return parts


def run(team: Team, task: str, rounds: int = 3, lead: str = "", builder: str = "",
        branch: str = "", open_pr: bool = False, parallel: bool = False, skip: tuple[str, ...] = (),
        closes: int = 0) -> bool:
    lead_cfg = team.get(lead) if lead else team.by_role("lead")
    builders = [team.get(builder)] if builder else team.all_by_role("builder")
    if not builders:
        team.by_role("builder")   # raises the standard "no agent with role" error
    parallel = parallel and len(builders) > 1
    extra = {r: ([] if r in skip else team.all_by_role(r)) for r in OPTIONAL if r != "journeys"}

    if branch:
        if github.git(team.root, "status", "--porcelain", "--untracked-files=no").strip():
            raise SystemExit("The working tree has uncommitted changes; commit or stash them first.")
        github.git(team.root, "checkout", "-b", branch)
        ui.action(f"created branch {branch}")

    planner = agent.make(team, lead_cfg, "lead", file_format=files.FILE_FORMAT)
    base = github.git(team.root, "rev-parse", "HEAD", check=False).strip() or None
    use_tools = review_tools.supported(team, lead_cfg)
    last_review = ""
    log = files.Log(team.root, "build", f"Build: {task}")
    guard = guards.make(team, task)
    touched: set[str] = set()

    ui.heading(f"Build: {task}")
    focus = context.choose(team, planner, task)
    if focus.focused:
        ui.action(f"focused context: {len(focus.paths)} files chosen by {lead_cfg.name}")
        log.record(f"{lead_cfg.name}: context", "Files chosen: " + ", ".join(sorted(focus.paths)))

    recent = sessions.for_prompt(team.root)
    ask = (f"{recent}\n\n" if recent else "") + f"Task: {task}\n\nWrite PLAN.md for {', '.join(b.name for b in builders) if parallel else builders[0].name}."
    if parallel:
        ask += PARALLEL_NOTE.format(count=len(builders), names=", ".join(b.name for b in builders))
    plan = planner.turn(f"{ask}\n\n# Current project files\n\n{focus.render()}")
    written = files.write_files(team.root, plan, allowed=("PLAN.md",))
    if "PLAN.md" not in written:   # a plan sent as plain text instead of a <file> block
        (team.root / "PLAN.md").write_text(files.strip_files(plan).strip() + "\n", encoding="utf-8")
        written = ["PLAN.md"]
    touched.update(written)
    focus.add(written)
    focus.add_from_reply(plan)
    log.record(f"{lead_cfg.name}: plan", plan, written)

    parts = parse_parts(team, plan, builders) if parallel else []
    if parallel and len(parts) < 2:
        ui.warn("the plan didn't split into parts for two or more builders; one builder will do it all")
        parts = []
    parts = parts or [Part(builders[0])]
    for part in parts:
        suffix = f" · part: {', '.join(part.prefixes)}" if part.prefixes else ""
        part.worker = agent.make(team, part.builder, "builder", file_format=files.FILE_FORMAT, label_suffix=suffix)
    if len(parts) > 1:
        ui.action("parts: " + "; ".join(f"{p.builder.name} → {', '.join(p.prefixes)}" for p in parts))

    for qa_cfg in extra["qa"]:
        allowed = tuple(qa_cfg.owns) or TEST_PREFIXES
        qa = agent.make(team, qa_cfg, "qa", file_format=files.FILE_FORMAT, test_paths=", ".join(allowed))
        reply = qa.turn(f"Task: {task}\n\nWrite the tests for PLAN.md before the builders start.\n\n"
                        f"# Current project files\n\n{focus.render()}")
        written = files.write_files(team.root, reply, allowed=allowed, guard=guard)
        touched.update(written)
        focus.add(written)
        log.record(f"{qa_cfg.name}: tests first", reply, written)

    if "journeys" not in skip and team.behaviour.server in team.mcp and base:
        # Behaviour checks first, like tests first: the journeys that show this task working for a user.
        from . import journeys
        from ..config import load
        writer = (extra["qa"] or [lead_cfg])[0]
        plan_text = (team.root / "PLAN.md").read_text(encoding="utf-8") if (team.root / "PLAN.md").exists() else ""
        written = journeys.for_task(team, writer, task, plan_text, log)
        if written:
            touched.update(written)
            team.behaviour.scenarios = load(team.root).behaviour.scenarios

    note = f"Task: {task}\n\nStart building from PLAN.md."
    approved, rejected = False, 0
    checks: list = []
    learned: list[str] = []
    rnd = 0
    for rnd in range(1, rounds + 1):
        ui.heading(f"=========== Round {rnd}/{rounds} ===========")
        results = _build_round(team, parts, note, focus, guard)
        round_written: list[str] = []
        problems = "".join(files.problems_note(w) for _, w in results)
        for part, (reply, written) in zip(parts, results):
            touched.update(written)
            focus.add(written)
            focus.add_from_reply(reply)
            round_written += written
            log.record(f"{part.builder.name}: round {rnd}", reply, written)
        tests = run_tests(team) + quality.report(team, base)
        if tests:
            ui.say(tests)
            log.record(f"Tests: round {rnd}", tests)
        if SCENARIOS_FILE in round_written:   # the journeys changed this round: check the new ones, not the old
            from ..config import ConfigError, load
            try:
                team.behaviour.scenarios = load(team.root).behaviour.scenarios
            except ConfigError as e:
                ui.warn(f"{SCENARIOS_FILE} couldn't be read again, so the earlier journeys are checked: {e}")
        checks = behaviour.run(team, base)
        if checks:
            evidence = behaviour.report(checks)
            log.record(f"Behaviour checks: round {rnd}", evidence)
            ui.say(behaviour.report(checks, for_pr=True))
            tests += f"\n\n{evidence}"

        messages = "\n\n".join(f"# {p.builder.name}'s message (round {rnd})\n\n{files.strip_files(r)}"
                               for p, (r, _) in zip(parts, results))
        if use_tools:
            plan_text = (team.root / "PLAN.md").read_text(encoding="utf-8") if (team.root / "PLAN.md").exists() else ""
            earlier = f"\n\n# Your previous review\n\n{last_review}" if last_review else ""
            review = review_tools.review(team, lead_cfg, planner.system, (
                f"Review round {rnd} of the task: {task}\n\n# PLAN.md\n\n{plan_text}{earlier}\n\n{messages}"
                f"\n\nFiles written this round: {', '.join(round_written) or 'none'}{problems}{tests}\n\n"
                "Review the work against PLAN.md. Use the tools to inspect the changes (start with diff). "
                "To change the plan, include PLAN.md in full in a <file> block."), base, touched)
        else:
            review = planner.turn(
                f"{messages}\n\nFiles written this round: {', '.join(round_written) or 'none'}{problems}"
                f"\n\n# Current project files\n\n{focus.render()}{tests}")
        last_review = review
        learned += memory.learn(team, review, lead_cfg.name)
        plan_files = files.write_files(team.root, review, allowed=("PLAN.md",))
        touched.update(plan_files)
        focus.add_from_reply(review)
        log.record(f"{lead_cfg.name}: review {rnd}", review, plan_files)
        held = [p for _, w in results for p in getattr(w, "held", [])]
        verdict = files.last_marker(files.VERDICT_RE, review)
        if verdict == "APPROVED" and held:   # the task isn't done while part of it waits on a guard
            ui.action(f"not approved yet: {', '.join(held)} held back; the builders resend it")
            review += f"\n\n(agent-team: not approved yet, because these changes were held back: {', '.join(held)})"
            verdict = "CHANGES"
        if verdict != "APPROVED":
            note = f"# {lead_cfg.name}'s review\n\n{review}{tests}{problems}"
            rejected += 1
            for part in parts:
                stronger = routing.escalation(team, part.builder, rejected)
                if stronger:
                    ui.action(f"{part.builder.name} → {stronger.name}: escalated after {rejected} rejected round(s)")
                    log.record(f"{lead_cfg.name}: escalation", f"{part.builder.name}'s work goes to {stronger.name} "
                                                                f"after {rejected} rejected round(s).")
                    suffix = f" · part: {', '.join(part.prefixes)}" if part.prefixes else ""
                    part.builder = stronger
                    part.worker = agent.make(team, stronger, "builder", file_format=files.FILE_FORMAT, label_suffix=suffix)
                    note = (f"You're taking over this task from a teammate whose work the lead rejected. The files "
                            f"below are as they left them.\n\nTask: {task}\n\n{note}")
                    rejected = 0
            continue

        findings = _security_review(team, extra["security"], task, touched, log, checks)
        if findings:
            ui.heading(f"{lead_cfg.name} approved, but the security review found problems.")
            note = f"# Security review (the lead had approved; fix these)\n\n{findings}{tests}"
            continue
        approved = True
        ui.heading(f"{lead_cfg.name} approved after {rnd} round(s).")
        break
    else:
        ui.heading(f"Stopped after {rounds} rounds without approval.")

    if approved:
        for docs_cfg in extra["docs"]:
            allowed = tuple(docs_cfg.owns) or DOC_PREFIXES
            writer = agent.make(team, docs_cfg, "docs", file_format=files.FILE_FORMAT, doc_paths=", ".join(allowed))
            changed = files.snapshot(team.root, paths=set(touched), limit=team.project.context_limit)
            docs = context.for_topic(team, {rel for rel, _ in files.project_files(team.root, only=allowed)})
            reply = writer.turn(f"Task that was just built and approved: {task}\n\n# Files the team changed\n\n"
                                f"{changed}\n\n# Current documentation\n\n{docs}")
            written = files.write_files(team.root, reply, allowed=allowed)
            touched.update(written)
            log.record(f"{docs_cfg.name}: docs", reply, written)

    sessions.save(team, "build", task, "approved" if approved else "not approved", rnd, touched, learned)
    if approved and open_pr:
        names = ", ".join(p.builder.name for p in parts)
        open_pull_request(team, task, sorted(touched), lead_cfg.name, names, closes,
                          behaviour.report(checks, for_pr=True))
    ui.say(f"Log: {log.path}")
    return approved


def _build_round(team: Team, parts: list[Part], note: str, focus: context.Focus,
                 guard=None) -> list[tuple[str, list[str]]]:
    current = focus.render()

    def one(part: Part) -> tuple[str, list[str]]:
        scope = (f"\n\nYour part: {part.what}\nYou may change only paths starting with: "
                 f"{', '.join(part.prefixes)}. Other builders are working on the rest at the same time."
                 if part.prefixes else "")
        reply = part.worker.turn(f"{note}{scope}\n\n# Current project files\n\n{current}")
        return reply, files.write_files(team.root, reply, allowed=part.prefixes or None, guard=guard)

    if len(parts) == 1:
        return [one(parts[0])]

    def buffered(part: Part):
        with ui.buffered():
            return one(part)
    with ThreadPoolExecutor(max_workers=len(parts)) as pool:
        return list(pool.map(buffered, parts))


def _security_review(team: Team, members: list[AgentConfig], task: str, touched: set[str], log,
                     checks: list | None = None) -> str:
    """Each security member checks the changed files and what the build ships; returns the findings
    of any NO, else ""."""
    if not members or not touched:
        return ""
    changed = files.snapshot(team.root, paths=set(touched), limit=team.project.context_limit)
    from .. import outside_in
    shipped = outside_in.scan(team, checks)
    if shipped:
        log.record("What the build ships", shipped)
        changed += "\n\n" + github.untrusted(shipped)
    found = []
    for cfg in members:
        reviewer = agent.make(team, cfg, "security")
        reply = reviewer.turn(f"Task: {task}\n\nThe lead has approved these changes. Review them.\n\n"
                              f"# Files changed in this build\n\n{changed}")
        yes = files.last_marker(files.SIGNOFF_RE, reply) == "YES"
        memory.learn(team, reply, cfg.name)
        log.record(f"{cfg.name}: security review", reply)
        ui.action(f"{cfg.name} {'signed off' if yes else 'found problems'}")
        if not yes:
            found.append(f"## {cfg.name}\n{reply}")
    return "\n\n".join(found)


def plan_title(plan: str, task: str) -> str:
    """A short PR title: PLAN.md's first heading, without a "Plan:" prefix; else the task."""
    for line in plan.splitlines():
        m = re.match(r"^#{1,3}\s+(.+?)\s*#*\s*$", line)
        if m:
            title = re.sub(r"^(?:PLAN(?:\.md)?|Plan)\s*[:\-–—]\s*", "", m.group(1)).strip(" `*")
            if title and title.lower() not in ("plan", "plan.md"):
                return title if len(title) <= 72 else title[:69] + "..."
    return task if len(task) <= 72 else task[:69] + "..."


def open_pull_request(team: Team, task: str, paths: list[str], lead: str, builder: str, closes: int = 0,
                      checks: str = "") -> str:
    if not team.project.repo:
        raise SystemExit("[project].repo is not set, so no pull request can be opened.")
    branch = github.git(team.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch in ("main", "master"):
        raise SystemExit("Refusing to commit to the default branch; use --branch.")
    plan_path = team.root / "PLAN.md"
    plan = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    # PLAN.md is the team's working note: it goes in the PR description, not into the project,
    # unless the project already keeps a PLAN.md under version control.
    if "PLAN.md" in paths and not github.git(team.root, "ls-files", "--", "PLAN.md").strip():
        paths = [p for p in paths if p != "PLAN.md"]
    if not paths:
        raise SystemExit("The build changed no project files, so there is nothing to open a PR with.")
    github.git(team.root, "add", "--", *paths)
    from .. import secret_scan
    secret_scan.guard(team.root)
    title = plan_title(plan, task)
    github.git(team.root, "commit", "-q", "-m", title, "-m",
               f"{task}\n\nPlanned by {lead}, built by {builder} (agent-team).")
    github.git(team.root, "push", "-q", "-u", "origin", branch)
    plan_section = (f"\n\n<details><summary>The plan ({lead})</summary>\n\n{plan.strip()[:50_000]}\n\n</details>"
                    if plan.strip() else "")
    closing = f"Closes #{closes}.\n\n" if closes else ""
    body = (f"{closing}{task}\n\nPlanned by {lead}, built by {builder}; the lead approved the result and the "
            f"project's tests ran each round.\n\nFiles: {', '.join(f'`{p}`' for p in paths)}"
            f"{chr(10) * 2 + checks if checks else ''}{plan_section}\n\n"
            "Opened by agent-team. The devops shift reviews, gets sign-offs and merges.")
    url = github.gh("pr", "create", "-R", team.project.repo, "--head", branch, "--title", title,
                    "--body", body).strip()
    ui.action(f"opened {url}")
    from .. import notify
    notify.send(team, "pr_opened", f"Opened a PR: {title} (planned by {lead}, built by {builder})", url)
    return url
