# Publishing agent-team

How a version of agent-team, the engine of Lakeba OS, reaches people. Each step that publishes something is done by a
maintainer on purpose; nothing here runs on its own.

## Release a version

1. Bump the version in `pyproject.toml`, `src/agent_team/__init__.py`, `plugin/.claude-plugin/plugin.json`
   and `PLUGIN_VERSION` in `plugin/hooks/register.tsx` (`tests/test_versions.py` checks they match),
   and turn `## [Unreleased]` in CHANGELOG.md into `## [X.Y.Z] - YYYY-MM-DD`.
2. Commit, then tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` checks the tag matches the version, runs the tests, builds the
   package, publishes it to PyPI and creates the GitHub release with that version's notes.

## One-time setup

- **PyPI trusted publishing.** On pypi.org, add a pending publisher for the project `agent-team`:
  owner `lakeba`, repository `agent-team`, workflow `release.yml`, environment `pypi`. In the GitHub
  repository, create the environment `pypi` (Settings → Environments). No token is stored anywhere.
- **Homebrew tap.** Create `lakeba/homebrew-tap` with `Formula/agent-team.rb` copied from
  `packaging/homebrew/agent-team.rb`. After each PyPI release, set its `url` and `sha256` and run
  `brew update-python-resources Formula/agent-team.rb`. Users then `brew install lakeba/tap/agent-team`.
- **Docs site.** Settings → Pages → Deploy from a branch → `main`, folder `/docs`. The site is
  `https://lakeba.github.io/agent-team/`.
- **Claude Code plugin.** The repository is its own marketplace (`.claude-plugin/marketplace.json`):
  `/plugin marketplace add lakeba/agent-team`. Submitting it to a public plugin directory follows that
  directory's own process.
