---
description: Have the agent-team build a task as a pull request (lead plans, builders implement, tests run, lead reviews; optional QA, security and docs members)
argument-hint: <what to build or fix> [--parallel] [--skip qa,security,docs]
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
   Add `--builder <name>` only if the user named a builder. Add `--parallel` if the user asked for
   it and the team has two or more builders (the lead then splits the plan into parts with
   separate paths). Pass `--skip` if the user asked to leave out the QA, security or docs step.
   If the team has `qa`, `security` or `docs` members they take part automatically: say so before
   starting, since each adds model calls. If `[limits]` is set, mention the per-run limit; a run
   that reaches it stops with exit code 3.
5. When it finishes, check:
   - the end of `.team/logs/build.md`: did the lead approve, after how many rounds? If a security
     member took part, did it sign off, and were its findings fixed? Did QA's tests pass at the
     end? Did the docs member change anything? With focused context, which files did the lead
     choose (the "context" entry)?
   - `git diff <default-branch>...<branch> --stat` and the actual diff for anything surprising;
   - the project's tests (`test_command` in `.team.toml`) pass on the branch;
   - the PR exists on GitHub (`gh pr view`) and CI has started. Its title comes from the plan's
     heading, and the plan is in its description, not committed (unless the project already
     tracks a PLAN.md).
6. Report: the PR link, what changed, the lead's verdict and any non-blocking notes, and that the
   PR now waits for `/team-ship` (owner sign-offs, lead review, merge). If the lead did not
   approve, say what was blocking and don't open a PR yourself. If it stopped on a spend limit,
   say how much it spent (`agent-team status`) and let the user decide whether to raise the limit.
