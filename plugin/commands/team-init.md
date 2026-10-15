---
description: Set up an agent-team for this project (writes a starter .team.toml)
argument-hint: [--builder-provider local --builder-model qwen3.8:27b-mlx]
---

Set up an agent-team for this project. Options: $ARGUMENTS

1. Find the CLI (`agent-team`, else `~/.agent-team/venv/bin/agent-team`, else `~/agent-team/.venv/bin/agent-team`). If there is none, tell
   the user to install it with the one-line installer in the agent-team README, and stop.
2. If `.team.toml` already exists, show its team (`agent-team agents`) and stop unless the user
   asked to start over.
3. Run `agent-team init` with the options given. It detects the test command and the GitHub repo,
   writes `.team.toml`, and adds `.team/` to `.gitignore`.
4. Read the project (README, main source files, existing tests and CI) and propose concrete
   `guarantees` for `[project]`: the rules a reviewer must hold every change to, specific to this
   codebase. Also propose `context_skip` entries for build output, vendored code and large assets.
   Show the user the proposed changes and apply them when they agree.
5. Ask whether the default team suits them (Atlas lead, Forge builder on a local model, Spark
   marketing, Harbor devops), or whether they want other members, models or machines. The file
   has commented-out optional members: Sentinel (security review of every build and sign-off of
   every PR), Probe (QA: tests first) and Quill (docs). Offer them, and offer spend limits
   (`[limits] per_run`, `per_day` in US dollars), and uncomment what the user wants.
6. Run `agent-team doctor` and report what's reachable. Remind them that `.team.toml` holds no
   secrets and can be committed, and suggest `/team-plan` as a first step.
