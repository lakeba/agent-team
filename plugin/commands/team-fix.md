---
description: Have the agent-team address the review feedback on an open pull request (a builder fixes it on the PR's branch)
argument-hint: <PR number>
---

Have the project's agent-team address the review feedback on pull request $ARGUMENTS.

Follow the agent-team operating rules (find the CLI, find `.team.toml`, run `agent-team doctor`
once, let the user watch, verify, report, never bypass the guardrails).

1. If no PR number was given, list the open PRs (`gh pr list`) and ask which one; stop.
2. Check that the PR is open, comes from a branch of this repository (not a fork), and has had a
   review: the lead's review is recorded by a devops shift (`/team-ship`). If there's no review
   yet, suggest running `/team-ship` first and stop. The working tree must be clean.
3. Run, where the user can watch: `agent-team fix <number>`. It checks out the PR's branch, the
   builder applies the lead's blocking points, tests run, and the lead confirms the points are
   addressed. Only then does it commit, push to the PR's branch and comment on the PR. It returns
   to the branch you were on.
4. When it finishes, read the end of `.team/logs/fix.md` and check the pushed commit
   (`gh pr view <number>`, `gh pr diff <number>`): does it address exactly the blocking points,
   and nothing else? Did CI start on the new commit?
5. Report what changed and why, the lead's check, and that the PR now waits for `/team-ship`,
   which reviews the new commit (approvals are tied to a commit) and merges it if approved. If the
   lead didn't confirm the fix, nothing was pushed: say what's still blocking.
