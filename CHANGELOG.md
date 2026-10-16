# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Release dates are filled in when a
release is cut; changes after the latest release go under `## [Unreleased]`.

## [Unreleased]

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
