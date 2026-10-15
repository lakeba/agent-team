---
description: Run the agent-team's devops shifts on a schedule (or show or remove the schedule)
argument-hint: [every, e.g. 6h | 30m | 1d] [--remove]
---

Set up scheduled devops shifts for the project's agent-team. Options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, verify, report, never bypass the guardrails).

1. Show the current schedule: `agent-team schedule`. If the user gave no interval and didn't ask
   to remove it, report the schedule and stop.
2. To remove it: `agent-team schedule --remove`, report, and stop.
3. Before installing one, check and tell the user:
   - `[project].repo` is set and there is a `devops` member;
   - `[limits]` is set. Unattended shifts spend money on their own, so if there is no `per_day`
     limit, recommend one and ask the user for an amount before going on;
   - each shift acts on GitHub (comments, labels, merges, releases) within the team's rules;
   - shifts run through the user's login shell, so the API keys in their shell profile are used.
4. With the user's go-ahead, run `agent-team schedule --every <interval>` (at least 5m; 6h is a
   sensible default). On macOS this installs a launchd agent in `~/Library/LaunchAgents`, elsewhere
   a crontab line. Two shifts never overlap: a shift that is due while one is running skips.
5. Report the schedule, where output goes (`.team/schedule.log`, plus `.team/logs/ship.md` for each
   shift) and how to stop it (`/team-schedule --remove`). The side panel shows the schedule too.
