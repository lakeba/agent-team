---
description: Have the agent-team write a positioning brief, website and pitch deck, reviewed with screenshots
argument-hint: [--reuse-brief] [--rounds N]
---

Have the project's agent-team make its marketing material. Options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. The team needs a `marketing` member. The paths come from `[project.marketing]` in
   `.team.toml` (defaults `BRIEF.md`, `site/index.html`, `deck/index.html`). Mention that this
   workflow sends many screenshots to the reviewing model and costs more than a build.
2. Make sure the working tree is clean (if not, tell the user and stop), switch to the default
   branch, update it (`git pull --ff-only`), then create a branch `team/marketing-<yyyymmdd>`.
3. Run, where the user can watch: `agent-team market` with the options given.
4. When it finishes, read the end of `.team/logs/market.md`. Look at the newest screenshots in
   `.team/shots/` yourself (desktop sections, phone sections, every slide) and check for layout
   problems and claims that don't match the code. Mention anything the reviewers missed.
5. If the lead approved, commit only the marketing files (the brief, the site folder, the deck
   folder), push the branch and open a PR. The marketing member owns those paths, so `/team-ship`
   will get its sign-off before merging. If the lead did not approve, report what was blocking
   and don't open a PR.
6. Report: the PR link, a short description of the positioning and the look, the reviewers'
   verdicts, and anything you'd still change.
