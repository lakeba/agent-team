# Roadmap

## Next

1. **First real projects.** Onboard a second codebase (for example a Next.js app) and fix what
   generalising from todo-py missed.
2. **Claude Code plugin.** Use it on that second project and refine the commands from what
   happens there.
3. **Smarter focused context.** Rank files with the project's RAG index instead of the lead
   reading a map, for codebases with thousands of files.

## Later

- Notifications (Slack, email, GitHub) when a PR is ready, a sign-off is needed or a member is down.
- Team memory: what each member learned from past reviews, carried into later prompts.
- A scoreboard: first-round approvals, cost and time per task, per member.

## Done

- Claude Code plugin, side panel and `/team-run`; editable dashboard with background runs.
- Per-member cost reporting, including remote nodes that run paid models.
- Spend limits per run and per day.
- Focused context for large codebases.
- Scheduled shifts with a lock so two never overlap.
- Parallel builders on separate parts of one plan.
- Security, QA and docs roles in `build`.
- Discovery of remote nodes on the local network.
- Tool use for non-Anthropic devops members.
