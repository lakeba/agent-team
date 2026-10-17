# Roadmap

## Next

1. **First real projects.** Onboard a second codebase (for example a Next.js app) and fix what
   generalising from todo-py missed.
2. **Claude Code plugin.** Use it on that second project and refine the commands from what
   happens there.

## Next release

- Behaviour checks for Electron apps, steps for scout sites, and a deadline for each browser step
  (merged, not yet released).

## Later

- Evidence in every PR: the failing test before the change, the passing run after, and the
  behaviour checks, as one bundle a reviewer can follow.
- A public leaderboard of models as team members, from `agent-team eval`.
- Translations of the README and the site.
- A hosted option (a GitHub App) for teams that don't want to run shifts on their own machines.

## Done

- 0.10: everything ECC offers for the team: its agents, skills (on demand), commands as playbooks
  and rules; guards after its hooks; session summaries; lessons with confidence; `agent-team audit`.
- 0.9: `agent-team mcp` for any coding agent, `agent-team try`, ECC templates.
- 0.8: REA, deeper: zero setup, team-written journeys, browser and API checks, evidence,
  release checks, outside-in security, the scout.
- 0.7: MCP tool servers for members, REA behaviour checks in reviews.
- 0.6: setup questions, Tab completion, `--purge`, `VISION.md`.
- 0.4: notifications to Slack or any webhook.

- 0.5: sandboxed tests, cost estimates and milestone budgets, ranked context, per-member GitHub identities, real-model evals, dashboard Activity/Settings/Projects, release workflow.

- Patch edits, reviews with tools, fixes inside the shift, autopilot, team memory and a scoreboard (0.3).

- Claude Code plugin, side panel and `/team-run`; editable dashboard with background runs.
- Per-member cost reporting, including remote nodes that run paid models.
- Spend limits per run and per day.
- Focused context for large codebases.
- Scheduled shifts with a lock so two never overlap.
- Parallel builders on separate parts of one plan.
- Security, QA and docs roles in `build`.
- Discovery of remote nodes on the local network.
- Tool use for non-Anthropic devops members.
