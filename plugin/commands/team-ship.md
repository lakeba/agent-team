---
description: Run one agent-team devops shift (triage issues, sign-offs, lead review, merge, release)
argument-hint: [--max-steps N]
---

Run one devops shift for the project's agent-team. Options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. `.team.toml` must set `[project].repo` and the team must have a `devops` member on an
   `anthropic` provider; if not, say what's missing and stop.
2. Note the current state first: `gh pr list`, `gh issue list` and `gh release list --limit 3`
   for the repo, so you can report what changed.
3. Run, where the user can watch: `agent-team ship` (pass `--max-steps` if given). A shift that
   cuts a release waits for CI and can take several minutes.
4. When it finishes, read the shift summary at the end of `.team/logs/ship.md` and compare
   GitHub's state with step 2: which PRs merged, which got sign-offs or change requests, which
   issues were labelled, answered or closed, and whether a release was published.
5. Report: what the shift did, with links; anything refused by the guardrails and why; what is
   waiting on whom. If the same PR has gone round several shifts on non-blocking points, say so and
   ask the user how they want to proceed. Don't merge or edit anything yourself to get past a
   refusal.
