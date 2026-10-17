---
name: git-workflow
description: Branching, commits, pull requests and keeping history useful
---
# Git workflow

- Short-lived branches from main; merge or rebase often to avoid drift.
- Commits: one logical change each, message in the imperative explaining why. Squash fix-ups before merging.
- Pull requests: a title that says what changes, a description with why, how it was tested, and risks.
  Small enough to review in one sitting.
- Never force-push shared branches. Never commit secrets; if one slips in, rotate it, then clean history.
- Tag releases; keep the changelog in step.
