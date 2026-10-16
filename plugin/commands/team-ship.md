---
description: Run one agent-team devops shift (triage issues, sign-offs, lead review, merge, release)
argument-hint: [--max-steps N]
---

Run one devops shift for the project's agent-team. Options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. `.team.toml` must set `[project].repo` and the team must have a `devops` member; if not, say
   what's missing and stop. The devops member can be on any provider (Claude, Ollama, an
   OpenAI-compatible server or a remote node), but it acts through tool calls, so a model weak at
   tool use makes a poor shift: say so if it isn't Claude.
2. Note the current state first: `gh pr list`, `gh issue list` and `gh release list --limit 3`
   for the repo, so you can report what changed.
3. Run, where the user can watch: `agent-team ship` (pass `--max-steps` if given). A shift that
   cuts a release waits for CI and can take several minutes. If it says another shift is already
   running (a scheduled one, or one started from the dashboard or panel), don't start a second
   one: report it and stop.
4. When it finishes, read the shift summary at the end of `.team/logs/ship.md` and compare
   GitHub's state with step 2: which PRs merged, which got sign-offs or change requests, which
   issues were labelled, answered or closed, and whether a release was published.
5. Report: what the shift did, with links; anything refused by the guardrails and why; what is
   waiting on whom. If the same PR has gone round several shifts on non-blocking points, say so and
   ask the user how they want to proceed. Don't merge or edit anything yourself to get past a
   refusal.
6. If a PR waits for the owners' approval (paths in `require_approval`; `agent-team approve` lists
   them), show what it changes and ask the user. On a clear yes, run `agent-team approve <PR>`;
   never approve on your own. The next shift merges it.
7. If the project has `release = "ask"` and the shift proposed a release, show the proposed
   version and notes and ask the user whether to publish it. On a yes, run
   `agent-team ship --release <version>`; never pass `--release` without their explicit approval.
8. When the lead requests changes on a PR from the team's own branches, the shift fixes it
   itself (`request_fix`: a builder applies the review, the lead confirms, CI runs, and the PR is
   reviewed again). If a fix wasn't confirmed or CI failed, say so; `/team-fix <number>` retries it.
9. If the user wants shifts to run on their own, point them to `/team-schedule`.
