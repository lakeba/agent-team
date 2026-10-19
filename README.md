<p align="center"><a href="https://lakeba.com"><img src="https://raw.githubusercontent.com/lakeba/agent-team/main/docs/assets/brand/lakeba-mark.svg" alt="Lakeba" width="72"></a></p>

<h1 align="center">Lakeba OS</h1>

<p align="center"><b>Have an idea? Build it with an AI team, then apply to co-found your company with Lakeba.</b><br>
Conceive · Create · Commercialise<br>
<a href="https://lakeba.github.io/agent-team/">Website</a> · <a href="https://lakeba.com/os/apply">Apply</a> · <a href="https://pypi.org/project/agent-team/">PyPI</a> · <a href="CHANGELOG.md">Changelog</a></p>

Describe your vision to Lakeba OS, and an AI team plans it, builds it, tests it and releases it as
a working MVP. Then apply to Lakeba to co-found your company, with Lakeba as investor and venture
studio behind you. agent-team is the engine: an open-source AI dev team that plans, builds,
reviews, merges and releases through GitHub, on Claude or local models.

## The program

From idea to founder, in four steps:

1. **Describe.** Tell Lakeba OS what you want to build, in plain language. No code needed.
2. **Build.** The AI team writes the plan, the code, the tests and the reviews, and gives you a
   working MVP. Hosted and free, coming soon.
3. **Apply.** Submit your MVP and a short pitch to Lakeba. Lakeba OS produces the positioning brief
   and pitch deck for you.
4. **Found.** If approved, you become founder and CEO of your own company. You hold 51%, Lakeba
   holds 49% as co-founder, investor and venture studio, and your first 12 months of salary are
   funded.

Not approved this time? Keep your MVP, keep building, apply again.
**[Apply with your MVP](https://lakeba.com/os/apply)**

If Lakeba co-founds your company, you get co-founding capital, your first 12 months of salary as
CEO funded, the Lakeba OS AI dev team for your product, Lakeba’s shared services (finance, legal,
people, marketing), and the Lakeba Group ecosystem, portfolio and network.

### Questions

**Do I need to know how to code?** No. You describe what you want and approve each step. The AI
team writes the code. Until the hosted service opens, you install it on your computer: on a Mac,
download it and double-click, and a guided setup does the rest.

**Is it really free?** Yes. agent-team is open source under MIT. The hosted Lakeba OS build service,
coming soon, will be free, with a fair-use build allowance per idea.

**Who owns my MVP?** You do. If Lakeba co-founds your company, the MVP is transferred into that
company, which you and Lakeba own together.

**Is funding guaranteed?** No. Lakeba reviews every application and funds a limited number of
ventures. Every applicant keeps their MVP whatever the outcome.

**Can I use agent-team without applying?** Yes. It is open source and runs on your machine with the
models you already have.

## agent-team, the engine

A configurable team of AI agents that works on a software project the way a small team would:
it plans a roadmap, builds features, reviews them, writes marketing material, and ships through
GitHub with pull requests, CI, sign-offs and releases.

Team members can run on any model and any machine: Claude through the Anthropic API, local
models through Ollama, any OpenAI-compatible server, or another machine running
`agent-team serve`. A team is described in a `.team.toml` file in each project, so adding a
member, a machine or a project is a configuration change.

It grew out of todo-py, a small command-line app this team planned, built, marketed and released
(v1.0.0 and v1.0.1); its team is in [examples/todo-py.team.toml](examples/todo-py.team.toml).

### How the team works

| Workflow | Command | What happens |
|---|---|---|
| Discuss | `agent-team discuss "next features"` | Members talk in turn until they all agree on how to reach the product's vision (`VISION.md`); the lead updates `ROADMAP.md`. |
| Build | `agent-team build "task" --branch x --pr` | The lead writes `PLAN.md`, builders implement it (in parallel with `--parallel`), tests run each round, the lead reviews until approved, then a PR opens. Optional QA, security and docs members write tests first, review the result and update the docs. |
| Autopilot | `agent-team autopilot --milestone M2` | Works through the roadmap a PR at a time: the lead picks the next task, the team builds it, each devops shift reviews, fixes and merges, until the lead says the milestone is done (or it gets stuck, or hits a spend limit). |
| Fix | `agent-team fix 12` | When the lead requests changes on a PR, a builder applies the review on that PR's branch, the lead confirms the blocking points are addressed, and it pushes; the next shift reviews the new commit. |
| Market | `agent-team market` | The marketing member writes a brief, a website and a pitch deck; a fact-checker checks claims and the lead reviews with screenshots. |
| Set up | `agent-team setup --license "MIT, copyright 2026 Lakeba"` | The devops member drafts README, CONTRIBUTING, CHANGELOG, CI and templates. |
| Ship | `agent-team ship` | One devops shift on GitHub: triage, owner sign-offs, lead review, merge, release (or, with `release = "ask"`, a release proposal you approve with `ship --release X.Y.Z`), feedback digest. `agent-team schedule --every 6h` runs shifts unattended, never two at once. |
| Dashboard | `agent-team ui` | Overview, Team, Runs, Costs, live Activity charts (spend, runs, merges, problems, latest events), Settings (easy switches and team templates, always previewed as a diff) and Projects (every project on this Mac). A page on this machine: the team and whether each member is reachable, every run with each member's verdicts, estimated costs per member, day and run, and the GitHub state. Edit members, connections, guarantees and prices there, add a machine with a guided wizard, and review the diff before saving. Start runs there and follow their output live. |

Guardrails are enforced in code, not left to the models. A PR merges only when CI is green, the
lead approved the exact head commit, and every member who owns a changed path signed off that
same commit (the lead's approval is its own sign-off). On a re-review, reviewers block only on
points still open or problems the new commit introduces, so a PR that fixes what was asked passes. Releases need green CI on `main` and a CHANGELOG entry. Text from outside the team
always reaches the models marked as untrusted. Spend limits in `.team.toml` stop any run before it
costs more than you allow, and large projects get a focused context instead of every file.

Builders change files with small search/replace edits instead of rewriting them, and an edit
that doesn't match is refused and sent back. Reviewers read files, search, see the diff and run
the tests themselves. When a reviewer blocks for a reason that will matter again, the lesson is
kept and every member sees it in later work.

With `[sandbox] mode = "container"`, the code the team writes is tested in a throwaway container
with no network and none of your keys. Every push is checked for secrets first (key and token formats, private keys, `.env` files, and
the values in your keys file). Paths you list in `require_approval` wait for your approval of the
exact commit. Weaker models hand work to a stronger member after rejected rounds (`escalate_to`),
and `[notify]` posts to Slack or any webhook when PRs open or merge, approvals or releases wait
for you, or autopilot stops.

### Without a terminal: the guided setup

On a Mac, download [Lakeba OS](https://lakeba.github.io/agent-team/downloads/Lakeba-OS-mac.zip), unzip
it and double-click **Lakeba OS** (the first time, right-click it and choose **Open**). It installs
agent-team and opens the dashboard in your browser, where a guided setup walks through seven short
steps:

1. **Your idea**: a name and a few sentences; it becomes the project's `VISION.md`.
2. **Where the AI runs**: free on this computer (Ollama, found for you, with a one-click model
   download), Claude (paste your key: it's saved only on this computer and checked at once), or both.
3. **Your team**: the members and what each does, optional QA, security and docs members, the
   number of builders and a daily spend limit.
4. The project is created for you in `~/LakebaOS/<name>`: git, `VISION.md`, `README.md`,
   `.team.toml`, the library template and a first save.
5. **GitHub** (optional): sign in on GitHub's own page and create a private repository.
6. **Ready check**: every requirement with a button to fix it where it can be fixed from the page.
7. **First version**: the lead reads the idea and suggests the first tasks; tick them and press Build.

The dashboard then opens on **My MVP**: what the team is doing right now in plain words ("Forge
is writing the code", "Tests: 12 passed", "Atlas approved it"), **Run my app** (a web app opens in
the browser; a command-line tool runs with what you type), **Keep this version** (a commit, pushed
when there's a GitHub repository), the next feature to build, and **Prepare my application** (the
marketing member's brief and pitch deck) with the link to apply to Lakeba. Every step writes exactly
what the command line would, so a project set up here works the same in a terminal.

The installer also adds **Lakeba OS** to your Applications folder (on Linux, the app menu) to come
back to the dashboard later; it opens your project directly when you have one. `agent-team ui` in a
folder without a team opens the same setup and offers to set up that folder: code already in it
stays as it is (agent-team only adds and commits its own files), and the projects you've started
are listed to open instead.

### Install

Requirements: macOS or Linux, Python 3.11+ (on Ubuntu/Debian also `python3-venv`) and git. Members
can run on Claude (an Anthropic API key), on [Ollama](https://ollama.com/) models on this machine or
others, or both; a team on Ollama alone needs no API key. Optional: [Ollama](https://ollama.com/)
for local models, on this machine or another. The workflows that work on GitHub (`build --pr`,
`ship`, `setup` and the plugin's PR steps) also need the [GitHub CLI](https://cli.github.com/)
signed in (`gh auth login`).

One command installs the CLI into its own environment under `~/.agent-team`, puts `agent-team` on
your `PATH` (`~/.local/bin`), and installs the Claude Code plugin if Claude Code is present. It gets
what's missing: on a Mac it asks macOS to install its developer tools (for git), and without Python
3.11+ it installs a private Python with [uv](https://docs.astral.sh/uv/). A first install ends by
opening the dashboard's guided setup (`--no-ui` to skip it) and adds the Lakeba OS app
(`--no-shortcut` to skip it):

```bash
curl -fsSL https://raw.githubusercontent.com/lakeba/agent-team/main/scripts/install.sh | bash
```

Run it again to update, then run `/reload-plugins` in any open Claude Code session (or start a new
one): an open session keeps the commands it started with. Options go after `bash -s --`, for example `| bash -s -- --ref v0.1.0`
for a specific version, `--no-plugin` to skip the plugin, or `--uninstall` to remove everything
it installed. `--uninstall` keeps your saved keys and project list in `~/.config/agent-team`; add
`--purge` to delete them too (it asks first). If you prefer pipx:
`pipx install git+https://github.com/lakeba/agent-team.git` (that installs the CLI only). Keep one
copy: two installs mean two versions, and the one first on your `PATH` wins.

Tab completes commands, options, choices and your members' names: the installer sets it up for
bash; for zsh, run `agent-team completion install` once (it asks before adding one line to
`~/.zshrc`).

### Try it first

```bash
agent-team try
```

A minute, in a throwaway folder: a two-member team (Atlas leads, Forge builds) adds a feature to a
small sample CLI, runs its tests and reviews the result. It uses Claude when a key is set, else a
local Ollama model, else a recorded run that calls no model at all, so it works on a fresh machine
(`--with claude|ollama|replay` to choose, `--keep` to keep the folder).

### Quick start

```bash
cd ~/code/my-project
agent-team ready      # checklist: git, GitHub, keys, Ollama, with the fix for anything missing
agent-team init       # asks where the models run (Claude, Ollama or both), which members, how many
                      # builders and any spend limits, then writes .team.toml
agent-team keys set ANTHROPIC_API_KEY    # only if members use Claude: asks for the key (hidden)
agent-team doctor     # the checklist again, then checks every member can be reached
```

`init` finds Ollama on this machine, at `OLLAMA_HOST`, or on the machine a VM or container runs
on, and offers what it finds. To set up without questions (scripts, CI), give the choices as flags;
`--yes` takes the defaults for the rest:

```bash
agent-team init --yes --models ollama --ollama-url http://192.168.1.20:11434   # no Claude, no key
agent-team init --yes --models claude --members security,qa --builders 2 --per-day 20
```

`--models` is `mixed` (Claude leads, reviews, ships and markets; the builders run on Ollama; the
default), `ollama` or `claude`. `--members` adds the optional members (`security`, `qa`, `docs`,
`all`). With a `.team.toml` already there, `agent-team init --ollama-url URL` only changes the
team's Ollama address. The dashboard's **Settings → Team composition** offers the same choices for
an existing team, shown as a diff before anything is saved.

Keys live in `~/.config/agent-team/env`, readable only by you, so they work the same from any shell,
the dashboard, background runs and schedules (Ubuntu's `~/.bashrc`, for one, is skipped by
non-interactive shells). A variable already exported in your environment wins.

Then edit `.team.toml` (or open `agent-team ui` and use **Edit team**): set the project's
guarantees, adjust the team, give members skills (Markdown files or Claude Code skill folders added
to their prompts), set spend limits under `[limits]`, and run a workflow:

```bash
agent-team discuss "next features"                       # agree a roadmap
agent-team build "add an export command" --branch team/export --pr
agent-team ship                                          # one devops shift on GitHub
```

#### The product vision

Tell the team what the product should be in `VISION.md`: who it's for, what problem it solves,
what makes it worth using. `init` asks for it (or `init --vision "..."`), and every workflow
reads it, so plans, builds, reviews and marketing all work towards it. To start the roadmap
from a vision you've written elsewhere:

```bash
agent-team discuss --vision ~/notes/tipsplit-pitch.md    # saved as VISION.md if there's none yet
```

#### Behaviour checks with REA

Tests check what their authors thought of. A behaviour check uses the program the way a user
would, before and after the team's change, and shows the lead what changed: "after `stop`,
`status` still shows the timer running", with the screens as evidence. It works for command-line
programs, web apps (a browser follows plain-words steps like `click button "Start"`, each with its
own deadline, and the report names a step that failed), Electron desktop apps (their windows, the
IPC channels and external effects they attempt) and libraries (the public API of a .NET assembly or
a JavaScript package).

```bash
agent-team rea setup          # installs REA (https://rea.tools) if needed and sets it up
agent-team behaviour suggest  # the lead writes the first journeys from VISION.md
```

From then on, `build` has the QA member (or the lead) add the journeys each task needs and runs them
every round; the dashboard's **Behaviour** tab shows before and after side by side. Releases follow
the evidence (removing a public member needs a major version), the security member also reviews
what the build ships, and an optional scout looks at other products from the outside before the
team plans (a site can have steps first, such as accepting a cookie dialog). REA is one of the tool servers the team can use over MCP: any `[mcp.*]` server's allowed
tools can be given to members (`mcp = ["rea"]`). See [configuration](docs/configuration.md#behaviour-and-behaviour-scenarios).

#### Other commands

| Command | What it does |
|---|---|
| `agent-team status [--json] [--health]` | The team, spend per member and today, recent and background runs, the schedule. |
| `agent-team ui` | The dashboard: see and edit the team, start runs, follow costs. |
| `agent-team jobs [start <workflow> \| stop <id> \| log <id>]` | Runs in the background, as the dashboard and the Claude panel start them. |
| `agent-team schedule --every 6h` | Run devops shifts on a schedule (launchd on macOS, cron elsewhere); `--remove` to stop. |
| `agent-team serve ...` | Serve a model on this machine as a team member for a team elsewhere. |
| `agent-team discover [--local]` | Find agent-team nodes on the local network; `--local` finds model servers instead: Ollama, mlx_lm, LM Studio and llama.cpp, here, on a VM's host or gateway, and on the other computers of the local networks (`--nearby` skips that scan). |
| `agent-team ready [--json]` | What this machine and project still need (git, GitHub, keys, Ollama, models), each with its fix. |
| `agent-team keys [set NAME \| remove NAME]` | API keys and tokens in agent-team's own keys file; values are never shown. |
| `agent-team issues [sync --milestone M2 --yes]` | The team's to-do list: `team:build` issues, created from the roadmap by the lead (shown first, created with `--yes`). Autopilot builds them and its PRs close them. |
| `agent-team approve [PR]` | Approve a PR's current commit when it changes paths in `require_approval`; with no number, list what's waiting. |
| `agent-team notify` | Send a test message to the `[notify]` webhook. |
| `agent-team eval [--only feature,bug]` | Runs fixed scenarios with your real models in a throwaway project (no GitHub): pass/fail, rounds and cost. Asks before spending. |
| `agent-team estimate build` | Predicts a run's cost from this project's past runs. |
| `agent-team projects` | Every project you use agent-team in: spend, runs, what waits for you. |
| `agent-team scoreboard` | Each builder's approval and first-round rate, average rounds and cost; each reviewer's pushback; cost per merged PR. |
| `agent-team memory [add TEXT \| forget N \| promote N \| export \| import FILE]` | The lessons the team learned from its reviews, each with a confidence; every member sees them in later work, and one the team keeps relearning can become a project rule. |
| `agent-team sessions [show N]` | What each build and fix did: task, outcome, rounds, files and cost. The lead's next plan starts from the latest ones. |
| `agent-team audit [--json]` | The team's own setup as an attack surface: prompts, skills, agent files, tool servers, permissions and secrets, with a grade. |
| `agent-team library ...` | The built-in specialists, skills, playbooks and rules (see below). |
| `agent-team playbook [list \| run NAME "what for"]` | A written procedure a member follows: code review, feature plan, bug fix, security review, ... |
| `agent-team templates [apply]` | A starting set of the library for your language. |
| `agent-team try` | A one-minute demo in a throwaway folder, no setup needed. |
| `agent-team mcp [install \| config]` | The team as tools for Claude Code, Codex, Cursor and other coding agents. |
| `agent-team agents`, `agent-team doctor` | List the team; check every member can be reached. |

`build` takes `--parallel` (split the plan across every builder), `--skip qa,security,docs`,
`--rounds`, `--builder` and `--lead`. Every command takes `-C <project>`; `--help` lists the rest.

#### The built-in library

agent-team ships with its own library, so a team can start with know-how instead of a blank page:

| | What's in it | How the team uses it |
|---|---|---|
| Specialists | 26: architect, planner, security, performance, accessibility, database, API, test strategy, refactoring, build fixing, docs, releases, dependencies, UX, incidents, and a reviewer for each of nine languages | `agent-team library hire architect` adds one as a member; `library give security-reviewer --to Sentinel` gives its know-how to a member you have |
| Skills | 46: test-first development, API design, migrations, error handling, observability, security, performance, accessibility, CI, containers, caching, concurrency, debugging, and patterns and testing for nine languages | given to a member, or the whole library on demand (`library on`): each member sees the skills that match its task and reads only the ones it asks for |
| Playbooks | 21: code-review, plan-feature, tdd, fix-bug, fix-build, refactor, test-coverage, security-review, api-review, architecture-review, release-check, changelog, postmortem, ... | `agent-team playbook run code-review "src/export"`: a member follows it and reports, or (for build playbooks) the team does it as a build; also MCP prompts for coding agents |
| Rules | common rules and rules for 12 languages | `library add-rules` (common and your language): standards every member follows on every call |

```bash
agent-team templates apply              # for your language: a reviewer, skills, rules, the library on
agent-team library skills testing       # search; also agents, playbooks, rules
agent-team playbook list                # the procedures a member can follow
```

**Templates.** `agent-team templates` lists ten (python, react, typescript, dotnet, go, rust, kotlin,
java, swift, general). `apply` gives the lead the language's reviewer, the builders its patterns
skill, QA its testing skill, the security member the security reviewer and the docs member the docs
writer; adds the common and language rules; turns the library on; and adds the project's own lint
and type checks when it has them. Pieces are copied into `team/skills/` and `team/rules/` and named
in `.team.toml`, so you review, edit and commit them like any other file. Skills and rules go with
every call, so each command shows how many characters it adds first; the library costs nothing until
a member asks for a skill. Your own playbooks go in `team/playbooks/`, your own skills in any folder
listed in `[project].library`.

**Quality gates.** `[project].checks` (for example `["ruff check .", "mypy ."]`) run every round
after the tests, and the lead reviews with their results. Each round's new lines are also read for
debug leftovers (`print`, `console.log`, `debugger`, breakpoints, focused or skipped tests).

**Guards.** Members can't weaken an existing linter or formatter config to make a check pass (unless
the task names the file), and a change to a sensitive file (CI, migrations, authentication, payment,
secrets, deployment) waits until the member writes a `WHY path: ...` line with the facts it rests
on. A held-back change keeps the build open. `[project].protect_config` and `gate_sensitive` turn
them off.

#### Use it from any coding agent (MCP)

`agent-team mcp` serves the team over the Model Context Protocol, so Claude Code, Codex, Cursor and
other agents can see the team and start its runs ("have the team build the export command as a
PR"):

```bash
agent-team mcp install --client claude     # or codex, cursor; asks first
agent-team mcp config                      # the snippets, to add by hand
```

The tools: `team_status`, `team_ready`, `team_start_run` (build, fix, discuss, ship, autopilot,
market, doctor, in the background), `team_run_output`, `team_runs`, `team_stop_run` and
`team_behaviour`. Runs keep the same spend limits and guardrails. Approving pull requests and
releases isn't offered: that stays with you.

#### Use it from Claude Code

The installer adds the plugin. To add it by hand, at the prompt of a Claude Code session:

```
/plugin install agent-team --marketplace lakeba/agent-team
```

Then, in any project: `/team-init`, `/team-doctor`, `/team-plan`, `/team-build <task>`,
`/team-ship`, `/team-fix <PR>`, `/team-schedule <6h>`, `/team-market` and `/team-ui`. Claude runs the workflow where you can watch it, checks the
result, and reports back. In projects with a `.team.toml`, the plugin also opens an agent-team side
panel (or run `/team-panel`): the team, each member's health, recent runs and spend, with buttons to
refresh, check health, start a devops shift and start the dashboard, plus background runs you can
stop. `/team-run build <task>` (or `fix <PR>`, `discuss <topic>`, `ship`, `market`, `doctor`) starts a run in
the background and the panel follows it. The commands need the `agent-team` CLI on your `PATH`.

### Documentation

- [Architecture](docs/architecture.md): providers, agents, workflows and how they fit.
- [Configuration](docs/configuration.md): every `.team.toml` setting.
- [Extending](docs/extending.md): add a team member, a role, a provider or a workflow.
- [Remote agents](docs/remote-agents.md): let another machine join the team.
- [Examples](examples/): the todo-py team, and a larger team across four machines with security,
  QA and docs members, parallel builders and spend limits.
- [Changelog](CHANGELOG.md) and [roadmap](ROADMAP.md).

### Licence

MIT, see [LICENSE](LICENSE).

Lakeba OS is a program of Lakeba Group. agent-team is MIT licensed.

### Status

Released on [PyPI](https://pypi.org/project/agent-team/) and [GitHub](https://github.com/lakeba/agent-team/releases);
see the [CHANGELOG](CHANGELOG.md) for what each version changed, [ROADMAP.md](ROADMAP.md) for what's
next and [CONTRIBUTING.md](CONTRIBUTING.md) to help.
