# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Release dates are filled in when a
release is cut; changes after the latest release go under `## [Unreleased]`.

## [Unreleased]

### Fixed

- A member on a local model server with its model's short name (`Qwen2.5-Coder-7B-Instruct-4bit`
  where mlx_lm serves `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`) was only reported as
  unreachable. The check now says which name is served ("did you mean …?"), and the dashboard's
  member editor lists the models the connection's server serves, warns when the name typed isn't
  one of them, and fixes it with one click.

## [0.13.5] - 2026-10-19

### Added

- Add a machine finds the model servers on the network ("Find servers on this network": Ollama,
  mlx_lm, LM Studio, llama.cpp), fills in the address, the kind and an instruct model with one click,
  and suggests the server's models as you type.

### Fixed

- An address with a number missing (`http://192.168.141:8080`) was silently read as another machine
  (192.168.0.141) and failed with "connection refused". The dashboard, the guided setup, `init` and
  `.team.toml` now refuse it and suggest the full address (192.168.1.141).

## [0.13.4] - 2026-10-19

### Added

- In a VM, finding model servers also covers the host's home network: the usual ones (192.168.0.x,
  192.168.1.x, 10.0.0.x) whose router answers are scanned, a few addresses at a time, because the
  VM's address translation (Parallels at least) refuses every connection for a while after a burst.
  It takes about 20 seconds more; the guided setup does it in the background.

### Changed

- Model servers list only models people can pick: mlx_lm's entries that are file paths (its cache
  folders) are left out.

## [0.13.3] - 2026-10-19

### Added

- Model servers on other computers are found too: `discover --local`, the guided setup (in the
  background, while you choose), Settings → Find servers, and `init` when nothing answers nearby
  scan this machine's private local networks (the /24 around each address, at most three) on
  Ollama's, mlx_lm's and LM Studio's ports, in about five seconds. `discover --local --nearby` skips
  the scan. A server on another machine must listen on the network (Ollama: OLLAMA_HOST=0.0.0.0;
  mlx_lm: --host 0.0.0.0).

## [0.13.2] - 2026-10-19

### Added

- Local model servers besides Ollama are found and can run the local members: mlx_lm (port 8080),
  LM Studio (1234) and llama.cpp, on this machine, a VM's host or the gateway, recognised and
  labelled (`readiness.find_local`). `agent-team discover --local` lists them; `init` picks one when
  there's no Ollama, and `--ollama-url http://HOST:8080` sets up an `openai`-kind connection for an
  mlx_lm server; the guided setup and Settings → Team composition list every server with its type;
  the readiness checklist checks the server and that it serves the members' model.
- A model that tries a tool call the server can't read (mlx_lm logs "Failed to parse tool call")
  now gets a clear error suggesting a larger model or `review = "snapshot"`, instead of an empty reply.

## [0.13.1] - 2026-10-19

### Changed

- `agent-team ui` in a folder without a team no longer opens another project: the setup offers to
  set up that folder (its code is kept as it is; agent-team adds its own files and commits only
  those, and an edited vision) and lists the projects you've started. Only the Lakeba OS app (and
  the first-install launch) opens the one project directly (`ui --from-app`).

## [0.13.0] - 2026-10-19

### Added

- A guided setup in the dashboard for people who've never used a terminal. `agent-team ui` outside a
  project (and a first install) opens it: your idea (saved as VISION.md), where the AI runs (Ollama
  found for you with a one-click model download, or your Anthropic key pasted, saved only on this
  computer and checked), your team (members, optional QA/security/docs, builders, a daily limit),
  the project created in ~/LakebaOS/<name> with git, the template and a first save, GitHub sign-in
  on GitHub's own page and a private repository (optional), a ready check with fixes, and the lead's
  suggested first tasks to build. Settings → Run setup again starts another idea.
- My MVP, the dashboard's new first tab: what the team is doing right now in plain language, Run my
  app (web apps in the browser, command-line tools with the arguments you type), Keep this version
  (a commit, with the secret check, pushed to GitHub when there's a repository), the next feature,
  and Prepare my application (brief and pitch deck) with the link to apply to Lakeba.
- Plain-language progress for every run on the Runs tab, above the full output.
- `[project].run_command`: how Run my app starts the project (worked out when empty).
- The installer gets git (macOS developer tools) and Python 3.11+ (a private one through uv) when
  missing, opens the guided setup after a first install (`--no-ui`), and adds a Lakeba OS app to
  Applications on macOS or the app menu on Linux (`--no-shortcut`). A double-click Mac starter is on
  the website.
- A running dashboard is reused: `agent-team ui` (or the Lakeba OS app) opens it instead of failing
  on the busy port.

### Changed

- Builds find the test command themselves when `[project].test_command` is empty (a project that
  started empty has tests once the team writes them).

## [0.12.1] - 2026-10-19

### Changed

- The README, the website and the package description present Lakeba OS, the program agent-team is
  the engine of: describe an idea, an AI team builds the MVP, then apply to co-found a company with
  Lakeba. The tool, the CLI, the package and every command keep the name agent-team.

## [0.12.0] - 2026-10-17

### Added

- agent-team's own library, shipped in the package: 26 specialists (architect, planner, security,
  performance, accessibility, database, API, test strategy, refactoring, build fixing, docs,
  releases, dependencies, UX, data, incidents, and a reviewer for nine languages), 46 skills, 21
  playbooks and rules (common and 12 languages). Nothing is downloaded.
- `agent-team library`: search the library; `give` a skill or a specialist's know-how to a member,
  `hire` a specialist as a member, `add-rules`, `on`/`off` for skills on demand (`library = ["builtin"]`).
- `agent-team playbook list|show|run`: `report` playbooks run read-only with one member, `build`
  playbooks become a build; a project's own playbooks go in `team/playbooks/`. The MCP server offers
  every playbook as a prompt.
- Quality gates: `[project].checks` (linters, type checkers) run every build and fix round with the
  tests, and debug leftovers in a round's new lines (`print`, `console.log`, `debugger`,
  breakpoints, focused or skipped tests) are listed for the lead. Templates add the project's own
  checks when its tools are configured.

### Changed

- Templates, skills on demand, playbooks and rules use the built-in library instead of a third-party
  one: `agent-team ecc` is replaced by `agent-team library` and `agent-team playbook`, and pieces are
  copied to `team/skills/` and `team/rules/`. Projects that list `"ecc"` in `[project].library`
  should use `"builtin"`; files already copied stay where they are.

### Removed

- `agent-team ecc`, `templates --ecc` and `audit --agentshield`.

## [0.11.0] - 2026-10-17

### Added

- Behaviour checks for Electron desktop apps (`kind = "electron"`): REA starts the app (`app`,
  with the project's `node_modules/electron` or `electron`), clicks through it (`click css "#save"`,
  `wait 500`, `reload`) and agent-team compares what changed for its user: its windows (title, page,
  visible), the external effects it attempted (blocked by REA), the IPC channels it used, the steps
  and the errors. REA doesn't capture the window's text or pixels, so those aren't compared. Each
  run gets its own REA process, so a click on something that never appears ends at the timeout.
  Not run with `[sandbox] mode = "container"` (the app would start outside it).
- Scout sites with steps: a `[research] sites` entry can be `{ url = "...", steps = [...] }`, with
  the same plain-words steps as browser journeys (e.g. `click button "Accept all"` for a cookie
  dialog). Each step gives up after 15 seconds; if one fails, the scout reads the page as it first
  loads and says the step didn't work.
- Browser journeys give each step a deadline, `step_timeout` (15 seconds by default, at most the
  scenario's `timeout`). A step whose element never appears now fails on its own and the report
  names it (`step step-2 (click button "Start") failed: ...`) where the page would be, instead of
  the whole run waiting until the timeout and the report saying only that it took too long.

### Fixed

- The scout read the last 4000 characters of a page (often the footer and the cookie banner); it
  now reads from the top, up to `[research] max_chars`.

## [0.10.0] - 2026-10-17

### Added

- Everything ECC offers, mapped onto the team (pinned ECC v2.2.3, fetched once, MIT licence):
  - `agent-team ecc`: browse and search ECC's 68 agents, 293 skills, 94 commands and rules;
    `add-skill`, `add-member` (an ECC agent as a new member), `add-rules`, `library on|off`.
  - The skill library (`[project].library`): members see the skills that match a task and read
    up to three on demand (`SKILL: name`), so a large library costs nothing until it's used.
  - Playbooks: `agent-team ecc run COMMAND "what for"` has a member follow an ECC command and
    report without changing files; `--build` makes it a build task. The MCP server offers ECC's
    commands as prompts.
  - Project rules (`[project].rules`): standards every member follows; templates now add the
    language's rules too.
  - Guards, after ECC's hooks: config protection (`protect_config`) and facts first for sensitive
    files (`gate_sensitive`, a `WHY path:` line); a held-back change keeps the build open.
  - Session summaries after every build and fix (`agent-team sessions`); the lead's next plan
    starts from the latest ones.
  - Lessons with confidence, like ECC's instincts: relearned lessons gain confidence, members see
    the most confident first; `memory promote N` makes one a project rule; `memory export|import`.
  - Long conversations are trimmed (`[project].history_limit`).
  - `agent-team audit`, after AgentShield: prompts, skills, agent files, tool servers, Claude Code
    permissions and hooks, `.mcp.json` and tracked secrets, scored and graded; `--agentshield`
    runs ECC's scanner when installed; `doctor` shows the grade.

## [0.9.0] - 2026-10-17

### Added

- `agent-team mcp`: the team as an MCP server for any coding agent (Claude Code, Codex, Cursor and
  others), with tools to see the team, start runs in the background, follow and stop them, and read
  the behaviour checks. Approvals aren't offered. `agent-team mcp install --client claude|codex|cursor`
  registers it (asking first); `agent-team mcp config` prints the snippets.
- `agent-team try`: a one-minute demo in a throwaway folder: a two-member team adds a feature to a
  sample CLI, tests and reviews it. Uses Claude, else Ollama, else a recorded run (the new `replay`
  provider kind) that needs no model or key.
- `agent-team templates [list|show|apply]`: team templates for ten languages that give each member
  the matching agent or skill from [ECC](https://github.com/affaan-m/ECC) (MIT), copied from a
  pinned release into `team/skills/ecc/` with ECC's licence and named in members' `skills`.
- `python -m agent_team` runs the CLI.

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
