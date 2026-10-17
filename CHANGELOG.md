# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Release dates are filled in when a
release is cut; changes after the latest release go under `## [Unreleased]`.

## [Unreleased]

## [0.8.0] - 2026-10-17

### Added

- REA, set up without hand configuration: `agent-team rea setup` finds REA (agent-team's own
  pinned copy, the PATH, or Claude Code's registration), installs REA 6.5.0 into agent-team's folder
  when asked, and writes `[mcp.rea]` and `[behaviour]`; `init` does it when REA is installed
  (`--no-rea` to skip); `rea status` includes REA's own doctor; `ready` offers it.
- The team writes the behaviour checks: journeys live in `team/behaviour.toml`; `build` has the QA
  member (or the lead) add the ones a task needs before the builders start, checked before they're
  kept (`--skip journeys`); `agent-team behaviour suggest|run|list`.
- Behaviour checks for web apps (`kind = "browser"`: serve the app, follow plain-words steps with
  REA's Playwright browser, compare the page's accessibility text, URL, errors and screenshot) and
  for libraries (`kind = "api"`: the public API of a built .NET assembly or a JavaScript package).
- Evidence: every check is kept under `.team/evidence/`; the dashboard's new Behaviour tab shows
  before and now side by side, with screenshots.
- Releases follow the evidence: with `api` scenarios the devops member gets `check_api_changes`,
  and a release smaller than the public API changes allow is refused.
- Security from the outside: after approval, the security member also reviews what the build
  ships (credentials, internal addresses and source maps in build output, and strings REA reads
  from built .NET assemblies).
- A scout (`role = "scout"`, `[research] sites`) observes other products from the outside before
  `discuss`; its brief goes to the discussion only.

### Changed

- With `[sandbox] mode = "container"`, behaviour checks run their prepare, run and serve commands in
  the container (they were skipped), and don't run at all if the container engine isn't ready.
- Guardrails in the team file: members who write code (builder, QA, docs) can't be given tools that
  look inside other software, and the scout may only use observation tools.

## [0.7.0] - 2026-10-17

### Added

- Tool servers over MCP: `[mcp.<name>]` starts a local Model Context Protocol server (stdio) and
  offers members only the tools its `tools` list allows. Members with `mcp = [...]` can call them
  in reviews and devops shifts, with any provider that can use tools. Servers start with a small
  environment (your API keys stay out), and results reach the models marked as untrusted and cut
  to `max_output`. `ready` checks each server is installed and `doctor` that it starts.
- Behaviour checks: `[[behaviour.scenarios]]` are user journeys (commands, typed input, files to
  watch) that `build` runs every round on the base version and with the team's changes, captured by
  [REA](https://github.com/morluto/rea) through MCP and compared as a user would see them (the final
  screen, the exit code, the files by content). The lead reviews with the screens and the first
  difference, the builders get them with requested changes, and the pull request lists the outcome.

## [0.6.1] - 2026-10-16

### Added

- The product vision: `VISION.md` tells the team what the product should be. Every workflow
  receives it with the README, and `discuss` gives it its own section, so the roadmap is planned
  towards it. `init` asks for it first (or `--vision TEXT|FILE`); `discuss --vision FILE` plans from
  a file anywhere and saves it as `VISION.md` when there's none. `/team-init` and `/team-plan` ask
  for it when it's missing.

### Changed

- `discuss` no longer needs a topic: the default is "next milestones".

## [0.6.0] - 2026-10-16

### Added

- `agent-team init` asks, in a terminal, where the models run (Claude with Ollama builders, only
  Ollama, or only Claude), which optional members to add, how many builders and any spend limits,
  then shows the team and asks before writing. Flags answer the same questions for scripts:
  `--models`, `--members`, `--builders`, `--per-run`, `--per-day`; `--yes` takes the defaults.
  `/team-init` passes the answers it collects as these flags.
- `init` finds Ollama by itself: on this machine, at `OLLAMA_HOST`, on the machine a VM or
  container runs on (Parallels, VirtualBox, UTM, Docker, Lima) or at the gateway.
  `agent-team discover --ollama` lists what it finds.
- The dashboard's Settings has a **Team composition** card with the same choices for an existing
  team, including **Find Ollama** and a model list from the chosen server, shown as a diff first.
- Tab completion for bash and zsh: commands, options, choices and the team's member names.
  The installer sets it up for bash; `agent-team completion install` does it for zsh.
- `install.sh --uninstall --purge` also deletes the saved keys and project list (asking first).

### Changed

- `install.sh --uninstall` says where your saved keys are kept, and warns when another copy (such
  as a pipx install) is still on the `PATH`. Its list of slash commands is complete.

- agent-team carries the Lakeba brand, as an open-source project Lakeba shares with its partners,
  clients and the developer community: the website, the dashboard and the README use the Lakeba
  mark and colours, with a "Conceive. Create. Commercialise." section, a "Shared by Lakeba"
  section, a favicon and a social preview image.

### Fixed

- `agent-team init --ollama-url URL` in a project that already has a team file now points that
  team's Ollama connection at URL (keeping the rest of the file) instead of refusing and leaving
  `ready` checking `localhost`.
- `init` picks pytest for a Python project only when the project uses it; otherwise it runs
  unittest discovery in the tests folder. It writes `python3`, since many Linux machines have no
  `python`.
- The website's "Get started" cards no longer overflow the page width on narrower screens.

## [0.5.1] - 2026-10-16

### Changed

- The Anthropic key is optional: the readiness checklist shows it as optional (○) until members
  use Claude, and only counts connections a member actually uses. The installer, README and
  `/team-init` no longer present it as a required step.

### Added

- `agent-team init --no-claude` puts every member on Ollama (this machine or another one), with
  no Claude connection and no key; the dashboard's Settings has a matching "Local only" template.

## [0.5.0] - 2026-10-16

The first release. agent-team is a configurable team of AI agents that plans, builds, reviews,
fixes, merges, releases and markets a software project through GitHub, with members on any
model and any machine. It grew out of the scripts that built todo-py v1.0.0 and v1.0.1.

### The team

- Teams are described in `.team.toml`: any number of members and roles, files owned per member,
  per-member skills (Markdown files or Claude Code skill folders), and team memory: reviewers'
  `LESSON:` lines are kept and shown to every member in later work.
- Members can be on Claude (`anthropic`), Ollama (local or another machine), any OpenAI-compatible
  server, or another machine running `agent-team serve` (token-protected; nodes can be found on the
  local network with `agent-team discover`). Every kind can call tools, so any member can run the
  devops shift.
- Roles the workflows use: lead, builder, devops, marketing, fact-check, and optional QA (writes
  tests first), security (reviews every approved build) and docs (updates the docs).

### Workflows

- `discuss` (a roadmap the members agree, reading the devops feedback digest), `build` (the lead
  plans, builders implement with search/replace edits, tests run, the lead reviews with tools to
  read files and run tests; `--parallel` splits a plan across builders), `ship` (one devops shift:
  triage, sign-offs, reviews, fixes, merges, releases), `fix` (apply a review to an open PR),
  `setup`, `market` and `autopilot` (work through a milestone a PR at a time).
- GitHub issues labelled `team:build` are the team's to-do list (`agent-team issues sync` creates
  them from the roadmap); autopilot builds them and its PRs close them.
- Scheduled shifts (`agent-team schedule --every 6h`, launchd or cron, never two at once) and
  background runs (`agent-team jobs`, the dashboard, the Claude panel).

### Guardrails

- Merges need green CI, the lead's approval and every owner's sign-off on the exact head commit;
  paths in `require_approval` also need the owners' approval of that commit
  (`agent-team approve <PR>`); `release = "ask"` makes releases proposals the owners approve.
- Re-reviews block only on points still open or problems the new commit introduces.
- Every push is checked for secrets first; text from outside the team reaches the models marked
  as untrusted; members can post as their own GitHub accounts (`github_token_env`) so their
  reviews are real GitHub reviews.
- `[sandbox] mode = "container"` runs the code the team writes in a throwaway container with no
  network and none of your keys.
- Guardrail scenario tests run whole shifts against a stand-in GitHub.

### Cost and models

- Every model call is recorded with its tokens and an estimated cost; spend limits per run, per
  day and per milestone stop a run before the next call; `agent-team estimate` predicts a run's
  cost from past runs; `agent-team scoreboard` shows approval rates, rounds and cost per member.
- Routing: a member hands its work to a stronger one after rejected rounds (`escalate_to`), and
  routine checks can use a cheaper model (`[routing].light_model`).
- Focused context for big projects: a ranked shortlist of relevant files and a map of the rest.
- `agent-team eval` runs fixed scenarios with your real models in a throwaway project.

### Dashboard and Claude Code

- `agent-team ui`: Overview, Team (edit everything, add a machine, review the diff before saving),
  Runs (start and follow runs), Costs (with the scoreboard), Activity (live charts), Settings (easy
  switches and team templates) and Projects (every project on this Mac).
- A Claude Code plugin: `/team-init`, `/team-doctor`, `/team-plan`, `/team-build`, `/team-fix`,
  `/team-ship`, `/team-autopilot`, `/team-issues`, `/team-schedule`, `/team-market`, `/team-ui`,
  `/team-run`, and a side panel (`/team-panel`) with the team, health, runs, spend and approvals.
- `[notify]` posts to Slack or any webhook when PRs open or merge, approvals or releases wait,
  autopilot stops, a spend limit is hit or a run fails.

### Setup

- `agent-team ready` lists what a machine and project still need, each with its fix; `init` detects
  Python, Node (Jest, Vitest, Mocha, `node --test`), Go, Rust and .NET projects, and Ollama on
  another machine; `agent-team keys set` keeps API keys where every command finds them.
- One-command installer for macOS and Linux (`scripts/install.sh`), and this release on PyPI
  (`pipx install agent-team`).
