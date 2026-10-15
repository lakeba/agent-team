# Contributing

## Set up

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd tests && ../.venv/bin/python -m unittest -v
```

Tests never call a real model or GitHub: `tests/helpers.py` provides a scripted `fake` provider.

The Claude Code plugin has its own checks, run from the repository root with Claude Code installed:

```bash
claude plugin validate plugin
claude plugin test plugin
```

To try the dashboard on a project: `agent-team ui -C <project>`. Its pages are plain files in
`src/agent_team/dashboard/static/` with no build step; the page's Content-Security-Policy allows no
inline scripts or styles, so size things through the DOM, as `app.js` does.

For day-to-day development, link your working copy's CLI instead of using the installer:
`ln -s "$PWD/.venv/bin/agent-team" ~/.local/bin/agent-team`. The installer never replaces a link it
didn't create (unless given `--force`), so the two don't fight. To test the installer against
uncommitted work, commit locally and run it with `AGENT_TEAM_SOURCE=$PWD`, `AGENT_TEAM_HOME` and
`BIN_DIR` pointing at temporary folders.

## Rules

- All changes go through pull requests to `main`; CI must pass on Python 3.11–3.13.
- Guardrail code needs a test for every behaviour change: `workflows/ship.py` (`merge_blockers`,
  `is_changelog_rename`), `files.write_files`, `budget.check`, `schedule.lock`, `jobs.argv_for`
  (it turns form input into a command), the dashboard's write checks, and `build.parse_parts`.
- No secrets in the repository or in example configs: providers reference environment variables.
- Only the Python standard library plus `anthropic` (and optional `pillow`); a new dependency
  needs a reason in the PR.
- Prompts live in `src/agent_team/prompts/*.md`. Changing one changes every team's behaviour, so
  say what you observed and what you expect in the PR.

## This repository is run by its own team

`.team.toml` here describes the team that maintains agent-team. `agent-team ship` triages issues,
gets sign-offs and merges; `agent-team discuss` updates [ROADMAP.md](ROADMAP.md). Feature
requests go in issues and reach the roadmap through the devops digest.
