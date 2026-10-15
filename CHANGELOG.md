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
- `agent-team ui` and `/team-ui`: a dashboard on 127.0.0.1 with the team and each
  member's reachability, a timeline of runs with verdicts, sign-offs, files and GitHub actions,
  and estimated costs per member, model, day and run.
- Per-member costs count remote nodes by the model they actually ran (a node serving Claude was
  previously counted as free). The panel and `agent-team status` show spend per member.
- Token usage per model call is recorded to `.team/usage.jsonl` (all providers, remote nodes and
  the devops tool loop), with cost estimates from a price table that `[pricing]` can override.
- The dashboard edits the team: members, connections (with a connection test), guarantees and
  prices; an "Add a machine" wizard with token generation and the commands for both machines.
  Every save shows a diff, is validated by reading it back, and backs up to `.team.toml.bak`.
  Writes need a per-session token and a same-origin request, and refuse a file changed on disk.
- `agent-team status [--json] [--health]`: the team, missing roles, recent runs and spend.
- A Claude Code side panel in the plugin (`/team-panel`, opened automatically in projects with a
  team): members with health marks, recent runs and spend, with Refresh, Check health and
  Start/Open dashboard buttons.
- Spend limits: `[limits] per_run` and `per_day` (US dollars) stop a run before the next model call
  once an estimate reaches them; shown and editable in the dashboard, shown in the panel.
- Focused context: `[project].context = "auto" | "focused" | "full"`. Large projects get a map of
  all files and the lead's chosen subset; `FILE:` / `NEED:` lines widen it during a run.
- `build --parallel`: the lead splits the plan into parts with separate paths and every builder
  works on its part at the same time.
- New roles used by `build`: `qa` (tests first), `security` (reviews approved changes; a NO sends
  them back) and `docs` (updates the docs after approval); `--skip` leaves any out. `owns = ["*"]`
  makes a member sign off every pull request.
- Scheduled shifts: `agent-team schedule --every 6h` (launchd on macOS, cron elsewhere) and
  `ship --every 6h`; a lock in `.team/` means two shifts never overlap.
- Background runs: `agent-team jobs` (start, stop, log), the dashboard's "Start a run" with live
  output, and the panel's "Start a shift" and `/team-run`.
- `/team-schedule` in the Claude Code plugin; the plugin's commands and skill cover the new roles,
  spend limits, background runs and any-provider devops shifts.
- Network discovery: nodes on `--host 0.0.0.0` answer UDP probes; `agent-team discover` and the
  dashboard's Add a machine list them.
- Tool use for every provider kind: Ollama, OpenAI-compatible servers and remote nodes can be the
  devops member; remote nodes pass tool calls through `/v1/turn`.
- Run logs carry timestamp markers, so headings inside agents' replies are never mistaken for
  structure.
