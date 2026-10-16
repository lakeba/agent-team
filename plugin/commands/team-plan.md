---
description: Have the agent-team discuss and agree a roadmap, then open a PR with ROADMAP.md
argument-hint: [topic, e.g. "next features"] [--vision FILE] [--members Atlas,Forge,...]
---

Have the project's agent-team discuss and agree a roadmap. Topic and options: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. Use the topic given, or "next features" if none. If the user named members, pass them with
   `--members`; otherwise the CLI uses the lead and a builder. Mention that larger groups cost more.
   **The product vision:** the members plan towards `VISION.md` (every workflow reads it). If the
   user gave a vision file, pass it with `--vision FILE`. If the project has no `VISION.md` and the
   user hasn't described the product, ask them in one question what the product should be (who it's
   for, what problem it solves, what makes it worth using); write their answer, in their words, to
   `VISION.md` and commit it on the roadmap branch with `ROADMAP.md`. They can also skip: the
   members then propose a vision in their first draft.
2. Make sure the working tree is clean (if not, tell the user and stop), switch to the default
   branch, update it (`git pull --ff-only`), then create a branch `team/roadmap-<yyyymmdd>`.
3. Run, where the user can watch: `agent-team discuss "<topic>" [--vision FILE] [--members ...]`
   The members see Harbor's latest feedback digest (`.team/FEEDBACK.md`, written by `/team-ship`);
   if there isn't one yet, mention that a shift first would give the discussion real input.
4. When it finishes, read the end of `.team/logs/discuss.md` and `git diff -- ROADMAP.md`.
   Check the roadmap against reality before trusting it: is anything listed as "next" already
   shipped (look at the CHANGELOG, recent merged PRs and releases)? Did the members' agreement
   rest on facts you can confirm in the code? Point out anything stale or doubtful.
5. If `ROADMAP.md` changed, commit only that file (and `VISION.md` if it's new), push the branch and open a PR titled
   "Roadmap: <topic>" whose body summarises the agreed milestones, the deferred items and any open
   questions. It then waits for `/team-ship` (the lead owns ROADMAP.md and signs it off).
6. Report: the PR link, the milestones in priority order with their reasons, what the members
   disagreed about and how it was settled, and anything you found stale.
