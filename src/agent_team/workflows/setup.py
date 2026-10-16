"""setup: the devops member drafts the files a well-run repository needs; a fact-checker checks
them against the code and the lead reviews until approved. Nothing is pushed."""
from __future__ import annotations

from .. import agent, context, files, routing, ui
from ..config import Team

ALLOWED = ("README.md", "LICENSE", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "CHANGELOG.md",
           ".gitignore", ".github/")


def task_text(team: Team, license_name: str) -> str:
    p = team.project
    return f"""Write or improve these repository files for {p.repo or p.name}, keeping anything already
correct (only output files you change):
- README.md: what it is, requirements, quick start, real usage examples, how to run the tests
  (`{p.test_command or 'see the project'}`), links to CONTRIBUTING.md and the licence.
- LICENSE: {license_name or 'leave any existing licence untouched; if none exists, do not add one'}.
- CONTRIBUTING.md: dev setup, tests, the branch/PR flow (all changes go through PRs; CI must pass;
  a maintainer reviews), the project's rules, and how feature requests reach ROADMAP.md.
- CODE_OF_CONDUCT.md (short and original) and SECURITY.md (private reporting).
- CHANGELOG.md in Keep a Changelog style with an `## [Unreleased]` heading at the top.
- .gitignore including `.team/` (the agent team's logs and screenshots).
- .github/workflows/ci.yml running `{p.test_command or 'the tests'}` on pull requests and pushes to
  main, with `permissions: contents: read`; plus short issue and PR templates.
Never invent maintainers, emails, URLs or badges. Everything must match the real code."""


def run(team: Team, rounds: int = 3, license_name: str = "") -> bool:
    devops_cfg, lead_cfg = team.by_role("devops"), team.by_role("lead")
    fc_cfg = team.by_role("factcheck", required=False) or team.by_role("builder")
    code = context.for_topic(team)
    task = task_text(team, license_name)
    writer = agent.make(team, devops_cfg, "builder", file_format=files.FILE_FORMAT)
    lead = agent.make(team, lead_cfg, "lead", file_format=files.FILE_FORMAT)
    checker = agent.make(team, routing.light(team, fc_cfg), "factcheck", files=code)
    log = files.Log(team.root, "setup", "Repository setup")

    msg = f"{task}\n\n# Project files\n\n{code}"
    for rnd in range(1, rounds + 1):
        ui.heading(f"=========== Repository setup, round {rnd}/{rounds} ===========")
        draft = writer.turn(msg)
        written = files.write_files(team.root, draft, allowed=ALLOWED)
        log.record(f"{devops_cfg.name}: draft {rnd}", draft, written)
        current = files.snapshot(team.root, only=ALLOWED, limit=team.project.context_limit)
        check = checker.turn(f"Fact-check these repository files (round {rnd}):\n\n{current}")
        log.record(f"{fc_cfg.name}: fact-check {rnd}", check)
        review = lead.turn(f"Review the repository files {devops_cfg.name} drafted for this task:\n{task}\n\n"
                           f"# Fact-check\n\n{check}\n\n# Current files\n\n{current}\n\n# Project code\n\n{code}")
        log.record(f"{lead_cfg.name}: review {rnd}", review)
        if files.last_marker(files.VERDICT_RE, review) == "APPROVED":
            ui.heading(f"{lead_cfg.name} approved after {rnd} round(s). Review the files, then commit them.")
            return True
        msg = f"# {lead_cfg.name}'s review\n\n{review}\n\n# Fact-check\n\n{check}\n\nRevise the files."
    ui.heading(f"Stopped after {rounds} rounds without approval. Log: {log.path}")
    return False
