# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Release dates are filled in when a
release is cut; changes after the latest release go under `## [Unreleased]`.

## [Unreleased]

### Added

- Configurable teams in `.team.toml`: any number of members, any role, files owned per member.
- Providers: `anthropic`, `ollama` (local or remote), `openai` (any compatible server) and
  `agent-http` (another machine running `agent-team serve`), registered by kind.
- `agent-team serve`: a token-protected, stateless HTTP node so other machines can join a team.
- Workflows: `init`, `doctor`, `agents`, `discuss` (any number of members), `build` (with
  `--branch` and `--pr`), `market`, `setup` and `ship`.
- `ship` guardrails in code: CI green, lead approval and every owner's sign-off tied to the exact
  head commit; releases date the changelog through a verified one-line PR.
- Generalised from the scripts that built lakeba/todo-py v1.0.0 and v1.0.1.
- Claude Code plugin (`plugin/`, installable from this repository's marketplace): `/team-init`,
  `/team-doctor`, `/team-plan`, `/team-build`, `/team-ship` and `/team-market`, plus an
  `agent-team` skill so Claude knows when to involve the team. Claude runs each workflow where the
  user can watch, verifies the result and reports.
- `doctor` says explicitly when an Ollama model is pulled, and how to pull it when it isn't.
