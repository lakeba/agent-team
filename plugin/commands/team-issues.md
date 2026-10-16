---
description: Turn the roadmap into GitHub issues the agent-team builds (team:build), or list them
argument-hint: [milestone, e.g. M2]
---

Manage the agent-team's to-do list for this project. Milestone: $ARGUMENTS

1. List the open `team:build` issues: `agent-team issues --milestone <m>` (or without it).
2. To create issues for the roadmap's open items, run `agent-team issues sync --milestone <m>`.
   It shows the issues the lead proposes and creates nothing. Show them to the user; if they agree,
   run it again with `--yes`, which creates them on GitHub with the `team:build` and
   `milestone:<m>` labels.
3. Explain that autopilot (`/team-autopilot`) builds the oldest open `team:build` issue first, its PR
   closes the issue, and that anyone can add the `team:build` label to an issue to hand it to the team.
