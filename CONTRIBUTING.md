# Contributing

## Set up

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd tests && ../.venv/bin/python -m unittest -v
```

Tests never call a real model or GitHub: `tests/helpers.py` provides a scripted `fake` provider.

For day-to-day development, link your working copy's CLI instead of using the installer:
`ln -s "$PWD/.venv/bin/agent-team" ~/.local/bin/agent-team`. The installer never replaces a link it
didn't create (unless given `--force`), so the two don't fight. To test the installer against
uncommitted work, commit locally and run it with `AGENT_TEAM_SOURCE=$PWD`, `AGENT_TEAM_HOME` and
`BIN_DIR` pointing at temporary folders.

## Rules

- All changes go through pull requests to `main`; CI must pass on Python 3.11–3.13.
- Guardrail code (`workflows/ship.py`: `merge_blockers`, `is_changelog_rename`; `files.write_files`)
  needs a test for every behaviour change.
- No secrets in the repository or in example configs: providers reference environment variables.
- Only the Python standard library plus `anthropic` (and optional `pillow`); a new dependency
  needs a reason in the PR.
- Prompts live in `src/agent_team/prompts/*.md`. Changing one changes every team's behaviour, so
  say what you observed and what you expect in the PR.

## This repository is run by its own team

`.team.toml` here describes the team that maintains agent-team. `agent-team ship` triages issues,
gets sign-offs and merges; `agent-team discuss` updates [ROADMAP.md](ROADMAP.md). Feature
requests go in issues and reach the roadmap through the devops digest.
