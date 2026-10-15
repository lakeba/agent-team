---
description: Have the agent-team discuss and agree a roadmap, then open a PR with ROADMAP.md
argument-hint: [topic, e.g. "next features"] [--members Atlas,Forge,...]
---

Have the project's agent-team discuss and agree a roadmap. Topic and options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. Use the topic given, or "next features" if none. If the user named members, pass them with
   `--members`; otherwise the CLI uses the lead and a builder. Mention that larger groups cost more.
2. Make sure the working tree is clean (if not, tell the user and stop), switch to the default
   branch, update it (`git pull --ff-only`), then create a branch `team/roadmap-<yyyymmdd>`.
3. Run, where the user can watch: `agent-team discuss "<topic>" [--members ...]`
4. When it finishes, read the end of `.team/logs/discuss.md` and `git diff -- ROADMAP.md`.
   Check the roadmap against reality before trusting it: is anything listed as "next" already
   shipped (look at the CHANGELOG, recent merged PRs and releases)? Did the members' agreement
   rest on facts you can confirm in the code? Point out anything stale or doubtful.
5. If `ROADMAP.md` changed, commit only that file, push the branch and open a PR titled
   "Roadmap: <topic>" whose body summarises the agreed milestones, the deferred items and any open
   questions. It then waits for `/team-ship` (the lead owns ROADMAP.md and signs it off).
6. Report: the PR link, the milestones in priority order with their reasons, what the members
   disagreed about and how it was settled, and anything you found stale.
