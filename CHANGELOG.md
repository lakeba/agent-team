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
- `scripts/install.sh`: one-command install and update into `~/.agent-team` (its own Python
  environment, `agent-team` on the `PATH`, the Claude Code plugin), with `--ref`, `--no-plugin`,
  `--force` and `--uninstall`. Works with the private repository through `gh`.
- MIT licence, and complete package metadata (licence, classifiers, project URLs).
- `agent-team ui` and `/team-ui`: a read-only dashboard on 127.0.0.1 with the team and each
  member's reachability, a timeline of runs with verdicts, sign-offs, files and GitHub actions,
  and estimated costs per member, model, day and run.
- Token usage per model call is recorded to `.team/usage.jsonl` (all providers, remote nodes and
  the devops tool loop), with cost estimates from a price table that `[pricing]` can override.
- Run logs carry timestamp markers, so headings inside agents' replies are never mistaken for
  structure.
