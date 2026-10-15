---
description: Have the agent-team build a task as a pull request (lead plans, builder implements, tests run, lead reviews)
argument-hint: <what to build or fix>
---

Have the project's agent-team build this task and open a pull request: $ARGUMENTS

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. If no task was given, ask for one and stop.
2. Make sure the working tree has no uncommitted changes to tracked files (if it does, tell the
   user and stop), then switch to the default branch and update it (`git pull --ff-only`).
3. Pick a short branch name from the task, like `team/<slug>`, that doesn't exist yet.
4. Run, where the user can watch:
   `agent-team build "<task>" --branch <branch> --pr`
   Add `--builder <name>` only if the user named a builder.
5. When it finishes, check:
   - the end of `.team/logs/build.md`: did the lead approve, after how many rounds?
   - `git diff <default-branch>...<branch> --stat` and the actual diff for anything surprising;
   - the project's tests (`test_command` in `.team.toml`) pass on the branch;
   - the PR exists on GitHub (`gh pr view`) and CI has started.
6. Report: the PR link, what changed, the lead's verdict and any non-blocking notes, and that the
   PR now waits for `/team-ship` (owner sign-offs, lead review, merge). If the lead did not
   approve, say what was blocking and don't open a PR yourself.
