---
name: agent-team
description: Work with the project's agent-team (an AI team defined in .team.toml with a lead, builders, marketing, devops and optional security, QA and docs members on any model or machine). Use when the user asks the team, or a team member by name (for example Atlas, Forge, Spark, Harbor or Sentinel), to plan a roadmap, build or fix something as a pull request, review and merge PRs, cut a release, triage issues, run shifts on a schedule, or write a brief, website or pitch deck; or asks to add a team member, a machine or a model to the team, or to set spend limits. Not for ordinary coding the user asked Claude itself to do.
---

# Working with an agent-team

The `agent-team` CLI runs a team of agents defined in the project's `.team.toml`. You are the
coordinator: you start the team's workflows, let the user watch, check the result yourself, and
report. The team does the work; you don't do it for them unless the user asks you to.

## Operating rules

1. **Find the CLI.** Use `agent-team` if `command -v agent-team` finds it, else
   `~/.agent-team/venv/bin/agent-team`, else `~/agent-team/.venv/bin/agent-team`. If none exists,
   tell the user to install it with the one-line installer in the agent-team README, and stop.
2. **Find the team.** The project needs a `.team.toml` (in the working directory or a parent).
   If there is none, suggest `/team-init` and stop.
3. **Check reachability first.** Run `agent-team doctor` before the first workflow in a session
   (`agent-team ready` gives the machine checklist alone and always exits 0). If a member shows
   `FAILED`, report which one and why, and stop. A missing Anthropic key means the user runs
   `agent-team keys set ANTHROPIC_API_KEY` in their own terminal; never ask them to paste a key.
4. **Let the user watch.** Workflows take minutes and stream each member's reasoning and replies.
   If a tool exists to run a command in the user's visible terminal panel, run the workflow there
   and link the tab; otherwise run it with Bash in the background. Wait for it to finish; don't
   poll in a tight loop, and don't start a second workflow on the same project meanwhile. Check
   `agent-team jobs` first: a run started from the dashboard, the panel or a schedule may already
   be going.
5. **Verify, then report.** Read the end of `.team/logs/<workflow>.md` and check the facts
   yourself (tests, `git diff`, the PR or release on GitHub). Report what changed, what the
   reviewers said, and what's left, with links. Say plainly if something failed or wasn't checked.
6. **Respect the guardrails.** Never merge, approve (`agent-team approve`), sign off or release on
   the team's or the user's behalf without the user's explicit yes for that PR or version, and
   never bypass a refusal from the `ship` tools (CI, lead approval, owner sign-offs). If the team
   is stuck in review loops, explain what's blocking and ask the user how to proceed.
7. **Costs.** Workflows call paid models with the project's files as context. Mention that a run
   costs money when starting a long or repeated one, and never loop workflows on your own.
   `[limits]` in `.team.toml` caps spend per run and per day; a run that reaches a limit stops
   with exit code 3. Report it and let the user decide; never raise or remove a limit yourself
   without being asked. `agent-team status` shows spend per member and today.

## Commands

- `/team-init`: write a starter `.team.toml` for this project.
- `/team-doctor`: check every member can be reached.
- `/team-plan [topic]`: members discuss and agree a roadmap; opens a PR with `ROADMAP.md`.
- `/team-build <task>`: the lead plans, builders implement, tests run, the lead reviews; QA,
  security and docs members join when the team has them; opens a PR.
- `/team-ship`: one devops shift: triage, sign-offs, lead review, merges, releases.
- `/team-autopilot [milestone]`: build, review, fix and merge PRs on its own until the milestone
  is done (ask the user first; it acts on GitHub).
- `/team-issues [milestone]`: the team's to-do list as `team:build` issues, created from the roadmap.
- `/team-fix <PR>`: a builder applies the lead's requested changes on that PR's branch and pushes;
  the next shift reviews the new commit.
- `/team-schedule [6h | --remove]`: run devops shifts on a schedule, never two at once.
- `/team-market`: brief, website and pitch deck, reviewed with screenshots; opens a PR.
- `/team-ui`: open the dashboard, where the team can also be edited.
- `/team-panel`: show the team, health, recent runs and spend in a side panel.
- `/team-run <autopilot [milestone] | build task | fix PR | discuss topic | ship | market | doctor>`: start a run in the
  background; the panel follows it. For runs the user wants to watch here, use the commands above.

## Checking the team

- `agent-team eval` tests the team's real models on fixed scenarios (it costs tokens: ask first).
- `agent-team estimate <workflow>` predicts a run's cost; mention it before long runs.
- `agent-team projects` lists every project using agent-team on this machine.

## Growing the team

Members, roles, owned paths and machines are all in `.team.toml`; see the agent-team docs
(`docs/configuration.md`, `docs/extending.md`, `docs/remote-agents.md`). When the user asks to add
a member or machine, edit `.team.toml` (or use the dashboard's Edit team), then run
`agent-team doctor` to confirm it's reachable. `agent-team discover` finds `agent-team serve` nodes
on the local network. Built-in roles: `lead`, `builder`, `devops`, `marketing`, `factcheck`,
`security`, `qa`, `docs`; `owns = ["*"]` makes a member sign off every PR. Large projects use
focused context automatically (`[project].context`). To give one member extra knowledge or house
rules, add `skills = ["path/to/skill.md", "~/.claude/skills/<name>"]` to it: Markdown files or skill
folders, added to its prompt after its role (`prompt` would replace the role prompt instead).
Secrets never go in `.team.toml`: a provider names the environment variable that holds them.
