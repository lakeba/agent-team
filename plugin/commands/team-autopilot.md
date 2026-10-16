---
description: Let the agent-team work through the roadmap on its own, a PR at a time, until a milestone is done
argument-hint: [milestone, e.g. M2] [--max-cycles N]
---

Run the project's agent-team on autopilot. Options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. Autopilot acts on GitHub by itself: it builds PRs, and each devops shift reviews, fixes and
   merges them (and releases, if `[project].release` is `auto`). Before starting, tell the user
   that, show the spend limits (`agent-team status`), and if `[limits]` has no `per_run`, ask
   whether to set one first. Start only when they agree.
2. The working tree must be clean and `ROADMAP.md` should exist (suggest `/team-plan` if not).
3. Run, where the user can watch: `agent-team autopilot` with `--milestone <name>` if given (and
   `--max-cycles`). Each cycle is one build or one devops shift. It stops when the lead says the
   milestone is done, when open PRs stop moving for two shifts, when a build isn't approved, at
   --max-cycles, or at a spend limit. It runs for a long time; in the background, follow it with
   `agent-team jobs log <id>` or start it as `/team-run autopilot <milestone>`.
4. When it stops, read `.team/logs/autopilot.md` for each cycle's decision and why it stopped, and
   check GitHub: which PRs merged, which are open and why, any release or release proposal.
5. Report: what got done, what it cost (`agent-team status`), why it stopped, and what needs a
   person (a PR stuck in review, a decision, a failing build).
