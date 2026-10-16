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
  `--force` and `--uninstall`.
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
- 0.3.0:
  - Patch edits: builders send `<edit>` blocks with SEARCH/REPLACE pairs instead of whole files;
    an edit that doesn't match exactly once leaves the file unchanged and is reported back.
  - Reviews with tools: the lead reads files, searches, sees the diff and runs the tests during
    `build` and `fix` reviews (`[project].review`, default `tools`).
  - Fixes inside the shift: the devops member's `request_fix` tool has a builder apply the review
    on the PR's branch, waits for CI, then asks for the reviews again, all in one shift.
  - `agent-team autopilot [--milestone M2]` (and `/team-autopilot`, `/team-run autopilot`, the
    dashboard): build, review, fix and merge a PR at a time until the milestone is done.
  - Team memory: reviewers' `LESSON:` lines are kept in `.team/memory.md` and shown to every member;
    `agent-team memory` lists, adds and forgets them; the dashboard's Team tab shows them.
  - `agent-team scoreboard` and the dashboard's Costs tab: approval and first-round rates, average
    rounds and cost per builder, pushback per reviewer, cost per merged PR.
- 0.2.6: .NET out of the box. `init` detects a solution or project file (`*.sln`, `*.slnx`,
  `*.csproj`, also nested as `src/App/App.csproj`) and writes `dotnet test` with a test-count
  pattern for its summary line, finds an `App.Tests/` test project for the QA member, and adds
  `bin/` and `obj/` to `.gitignore`. Prompts never include files git ignores, nor `bin/` and
  `obj/` next to a .NET project file, so build output (`obj/`, Cargo's `target/`) no longer
  fills the context. The readiness checklist says when the test command's program isn't on the
  `PATH` (with a hint for a `dotnet-install` SDK in `~/.dotnet`).
- 0.2.5: `[project].release = "ask"` makes the devops shift propose releases instead of
  publishing them; approve with `agent-team ship --release X.Y.Z`, or the dashboard's or panel's
  Approve button (`init` writes `ask`). Build PRs are titled from the plan's heading, and the plan
  goes in the PR description instead of being committed as PLAN.md.
- 0.2.4: the devops shift creates a label that doesn't exist yet instead of failing on it, and
  gets the repository's clone URL as a verified fact. The lead's approval of a commit counts as
  its sign-off for paths it owns, so it never gives two verdicts on one commit. Re-reviews see
  the reviewer's earlier review and block only on points still open or problems the new commit
  introduces. `fix` also applies owners' refused sign-offs, not only the lead's review.
- 0.2.3: `discuss` reads the devops member's feedback digest (`.team/FEEDBACK.md`, marked as
  untrusted), so roadmap discussions answer what developers ask for. Before, the digest was
  written every shift but never reached the planning.
- 0.2.2: `agent-team fix <PR>` (and `/team-fix`, `/team-run fix`, the dashboard's "Fix a pull
  request"): a builder applies the lead's requested changes on an open PR's branch, the lead
  confirms, and it pushes; never to forks, nothing pushed without the lead's confirmation. The
  devops shift names it as the next step when the lead requests changes.
- 0.2.1, from the second VM run: `ready --ollama-url` checks that address even when a team file
  exists; `init --builder-provider` accepts `ollama`/`anthropic` and refuses to leave a file the
  CLI can't read; the checklist reports a missing git identity; Node's test-count pattern no
  longer starts with `^` (CI logs put a timestamp first); the dashboard says when a newer
  agent-team is installed than the one it runs.
- Version 0.2.0 for the CLI and the plugin. The installer updates an installed plugin and says
  to `/reload-plugins` open sessions (they keep the commands they started with); the panel warns
  when the plugin and the CLI versions differ.
- `[project].repo` falls back to `origin` when it's on GitHub, so a repo created after `init`
  needs no edit.
- First run on a new machine: `agent-team ready` lists what's missing (git, GitHub repo, `gh`
  sign-in, keys, Ollama, pulled models) with the exact fix; `doctor` shows it first, and the panel
  shows anything that needs attention.
- `agent-team keys set NAME`: keys saved in `~/.config/agent-team/env` (mode 600) and loaded by
  every command, so they work from any shell, launchd or cron; values are never printed or taken
  from arguments. A variable already in the environment wins.
- `init --ollama-url` for Ollama on another machine; the builder's model is chosen from what that
  server has pulled. Test-count patterns for Node's built-in runner, Vitest and Mocha; the QA
  member's folder follows the project (`test/`, `tests/`...); `.team.toml.bak` is git-ignored.
- `/team-init` checks the machine first, offers to `git init` and create a private GitHub repo,
  asks where Ollama runs, then writes the file.
- Skills per member: `skills = [...]` adds Markdown files or skill folders (a Claude Code
  `SKILL.md` works as it is) to a member's prompt, after its role prompt. Checked by `doctor`,
  editable and shown in the dashboard, shown in the panel and in every member's roster.
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
- The installer works without the GitHub CLI (the repository is public), and says how to fix a
  missing `python3-venv` on Ubuntu/Debian. The panel opens the dashboard with `xdg-open` on Linux.
- Network discovery: nodes on `--host 0.0.0.0` answer UDP probes; `agent-team discover` and the
  dashboard's Add a machine list them.
- Tool use for every provider kind: Ollama, OpenAI-compatible servers and remote nodes can be the
  devops member; remote nodes pass tool calls through `/v1/turn`.
- Run logs carry timestamp markers, so headings inside agents' replies are never mistaken for
  structure.
