# Configuration: `.team.toml`

`agent-team init` writes a starter file from a few questions (or flags: `--models`, `--members`, `--builders`, `--per-run`, `--per-day`, `--yes`). The full set of settings:

## `[project]`

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Project name used in prompts. |
| `repo` | `""` | `owner/name` on GitHub. Needed by `build --pr` and `ship`. |
| `test_command` | `""` | Shell command run in the project after each build round. |
| `test_count_pattern` | `Ran (\d+) tests?` | Regex with one group, matched against CI log lines to read the test count. Empty disables it. `init` picks one for the test command it detects (pytest, Jest, Vitest, Mocha, `node --test`, Cargo, `dotnet test`). |
| `guarantees` | `[]` | Rules the lead enforces in every plan and review. |
| `context_skip` | `[]` | Path prefixes never sent to the models (vendored code, large assets). Files git ignores are never sent either, nor `bin/` and `obj/` next to a .NET project file, so build output listed in `.gitignore` needs no entry. |
| `context_limit` | `200000` | Maximum characters of project files in one prompt. Raising it costs tokens; prefer `context_skip`. |
| `review` | `tools` | How the lead reviews builds and fixes. `tools`: with tools to read files, search, see the diff and run the tests (needs a provider that can call tools; others fall back). `snapshot`: every file sent up front, as before. |
| `require_approval` | `[]` | Paths (prefixes or globs like `*.csproj`) whose changes need the owners' approval: such a PR merges only after `agent-team approve <PR>` (or the dashboard's or panel's Approve) for its exact head commit. |
| `release` | `auto` | Who decides when a version ships. `auto`: the devops shift releases on its own when merged changes are worth it. `ask`: it proposes a release (version and notes) and you approve it with `agent-team ship --release X.Y.Z`, the dashboard's Approve button or the panel's. `agent-team init` writes `ask`. |
| `context` | `auto` | What prompts include. `full`: every file, every time (fails when that's over `context_limit`). `focused`: the lead sees a map of the project and picks the files a task needs; members can ask for more with `FILE: path` lines. `auto`: full when it fits, focused when it doesn't. |

### `[project.marketing]`

`brief`, `site` and `deck` paths for the `market` workflow, and an optional `browser` path for
screenshots (otherwise Chrome, Edge, Chromium or Brave is found automatically).

## `[providers.<name>]`

| Key | Meaning |
|---|---|
| `kind` | `anthropic`, `ollama`, `openai`, `agent-http`, or any registered kind. |
| `url` | Base URL. Required for `openai` and `agent-http`; Ollama defaults to `http://localhost:11434`. |
| `api_key_env` | Name of the environment variable holding a key or token. Never put the value itself here. Set it in your environment or, so every command finds it, with `agent-team keys set NAME` (saved in `~/.config/agent-team/env`). |
| `options` | Kind-specific table, e.g. `{ num_ctx = 65536 }` for Ollama, `{ stall_seconds = 480 }` for Anthropic. |

## `[pricing."<model>"]`

Optional. Overrides the built-in price table the dashboard uses for cost estimates, in US dollars
per million tokens: `input`, `output`, and optionally `cache_read` and `cache_write` (default 10%
and 125% of `input`). Local and self-hosted models count as free unless priced here.

```toml
[pricing."qwen3.8:27b-mlx"]   # e.g. to account for a rented GPU
input = 0.10
output = 0.40
```

## `[limits]`

Optional spend limits in US dollars, from the same estimates as the dashboard. A run checks them
before every model call and stops with exit code 3 once one is reached; a call already under way
finishes, so a run can go over by at most one reply.

```toml
[limits]
per_run = 5.0    # one workflow run
per_day = 20.0   # all runs in this project, per UTC day

[limits.milestones]
M2 = 10.0        # what autopilot may spend on milestone M2, across all its builds and shifts
```

`agent-team estimate build` (or `ship`, `autopilot --cycles 3` ...) predicts a run's cost from this
project's past runs, and the CLI and the dashboard show that estimate before a run starts.

## `[sandbox]`

Run the test command, which executes code the team just wrote, in a throwaway container instead
of on your machine. Optional; `off` by default.

```toml
[sandbox]
mode = "container"      # off | container
image = ""              # default: from the stack (python:3.12-slim, node:22-bookworm-slim, the .NET SDK ...)
network = false         # true if the tests download dependencies
engine = ""             # docker | podman; default: whichever is installed
```

Only the project folder is mounted; none of your environment variables or keys go in; memory,
CPU and processes are limited. If the engine is missing or not running, runs fail rather than
run unsandboxed (`agent-team ready` shows it).

## `[routing]`

Pick the model by difficulty. Optional.

```toml
[routing]
escalate_after = 1                 # rejected rounds before a member's work goes to its escalate_to
light_model = "claude-haiku-5-5"   # owners' sign-offs and fact-checks by Claude members use this
```

## `[notify]`

Messages when things happen, to a Slack incoming webhook or any URL that takes JSON. Optional.

```toml
[notify]
webhook_env = "AGENT_TEAM_WEBHOOK"   # the variable holding the URL: agent-team keys set AGENT_TEAM_WEBHOOK
format = "slack"                     # slack: {"text"}; json: {"event", "project", "text", "url"}
events = []                          # empty: all of pr_opened, pr_merged, fix_pushed, approval_needed,
                                     # release_proposed, released, autopilot_stopped, spend_limit, run_failed
```

The URL itself never goes in `.team.toml`. `agent-team notify` sends a test message.

## `[mcp.<name>]`

A tool server the team can use, over the Model Context Protocol (stdio). agent-team starts it
when a member or a behaviour check needs it, and stops it afterwards.

| Key | Default | Meaning |
|---|---|---|
| `command` | required | The program that starts the server, e.g. `"rea"` or `"npx"`. |
| `args` | `[]` | Its arguments, e.g. `["--mcp"]`. |
| `tools` | `[]` | The only tools members are offered. Servers can offer hundreds (REA has over 200, with megabytes of descriptions), so list the few a member's job needs. Behaviour checks call the tools they need whatever this says. |
| `env` | `{}` | Extra environment variables, as plain values. Never put secrets here. |
| `env_from` | `[]` | Variables passed through from your environment or keys file (for tokens a server needs). |
| `timeout` | `300` | Seconds one tool call may take. |
| `max_output` | `20000` | Characters of one result a model sees; the rest is cut, with a note. |

A server starts with a small environment (PATH, HOME, locale, terminal) plus `env` and `env_from`,
never everything agent-team has loaded, so your API keys don't reach the programs it runs.
Results reach the models marked as untrusted, like issue text from outside the team.

```toml
[mcp.rea]                     # REA: npm install --global rea-agents
command = "rea"
args = ["--mcp"]
tools = ["capture_process_scenario"]   # each allowed tool's description is sent on every call: this one is ~8,000 characters
```

## `[behaviour]` and behaviour scenarios

Behaviour checks use your program the way a user would, once on the version a build started from
and once with the team's changes, and compare what a user would notice. `build` runs them every
round, after the tests: the lead reviews with the results (screens and pages included), the builders
get them with any requested changes, and the pull request lists them. Every check's evidence is kept
under `.team/evidence/` and shown in the dashboard's **Behaviour** tab.

They're captured by [REA](https://rea.tools). `agent-team rea setup` installs REA (a pinned version,
in agent-team's own folder) if it isn't on your machine already, and adds `[mcp.rea]` and
`[behaviour]` to the team file; `agent-team init` does the same when REA is installed. REA you
installed yourself, or registered with Claude Code (`rea-agents setup`), is used as it is.

Scenarios live in `team/behaviour.toml` (as `[[scenarios]]`), which the team writes and keeps up to
date, and can also go in `.team.toml` (as `[[behaviour.scenarios]]`). `agent-team behaviour suggest`
has the lead write the first ones from `VISION.md`; during `build`, the QA member (or the lead) adds
the journeys a task needs before anyone builds it, the way QA writes tests first (`--skip journeys`
leaves this out). A file that doesn't parse is sent back and never kept.

```bash
agent-team rea setup          # install and configure REA
agent-team behaviour suggest  # the lead writes team/behaviour.toml from VISION.md
agent-team behaviour run      # compare HEAD with your working tree now
agent-team behaviour list
```

| Key | Default | Meaning |
|---|---|---|
| `[behaviour].server` | `rea` | The `[mcp.*]` server that captures the runs. |
| `[behaviour].browser` | found | Chrome or Chromium for browser scenarios. |
| `name` | required | A short name for the journey, shown in reviews and the PR. |
| `kind` | `terminal` | `terminal`, `browser`, `electron` or `api`. |
| `prepare` | `""` | Run first in `$PROJECT` and not captured, e.g. a build, so the run itself is quick. |
| `timeout` | `120` | Seconds the run may take. |

**terminal**: a command-line program. The final screen is compared line by line, then the exit code
and the files the run left (files whose content alone differs, such as ones storing times, are noted,
not counted).

| Key | Default | Meaning |
|---|---|---|
| `run` | required | Shell commands. They run in an empty folder; `$PROJECT` is the version under test. |
| `input` | `[]` | Lines typed into the program, one after another. |
| `input_delay`, `input_every` | `2.0`, `1.0` | Seconds before the first line, and between lines. |
| `watch` | `["."]` | Paths in the run's folder whose files are compared. |

**browser**: a web app. `serve` starts it, a browser follows the steps, and the page as a user (or a
screen reader) perceives it is compared, then the final URL, new console and page errors, and the
screenshot (2% of pixels or more counts as looking different).

| Key | Default | Meaning |
|---|---|---|
| `serve` | `""` | Starts the app in `$PROJECT`, e.g. `npm run preview -- --port 5173 --strictPort`; stopped after. |
| `url` | required | Where the browser starts. Only this machine (`http://127.0.0.1:...` or `localhost`). |
| `steps` | `[]` | What the user does, in plain words (below). |
| `step_timeout` | `15` | Seconds one step waits (for its element to appear, a page to load) before it fails; at most `timeout`. A pause (`wait 500`) is exactly its length. |

Steps name elements the way a screen reader does, a role and its name: `goto /about`,
`click button "Start"`, `fill textbox "Project" with "client-a"`, `press textbox "Project" Enter`,
`check checkbox "Remember me"` (or `uncheck`), `select combobox "Plan" option "Pro"`,
`wait for text "Running"` (or `wait for button "Stop"`), `wait 500`. Where a page has no good names,
`css "#start"` and `testid "start"` work too.

A step that fails (its element never appears) ends the run there, and REA captures nothing after it,
so the report shows that step instead of the page: `step step-2 (click button "Start") failed: ...`.

**electron**: a desktop app built with Electron. REA starts it, the steps click through it, and
what changed for its user is compared: its windows (title, the page each shows, hidden or
closed), the external effects it attempted (opening a link, a download, a permission: REA blocks
them and records them), the IPC channels it used between window and main process (the kinds of
values, never the values), whether every step worked, and errors. REA's Electron capture doesn't
record the window's text or a screenshot, so a change to what a window says, without a change to
its title, isn't noticed; cover that with tests or a `browser` journey of the same page.

| Key | Default | Meaning |
|---|---|---|
| `app` | `.` | The app, relative to the project: its folder (with `package.json`) or its main script. |
| `electron` | the project's | The Electron executable. By default the one npm installed in the project (`node_modules/electron`), so `prepare` is usually `npm ci`. |
| `electron_args` | `[]` | Extra arguments for Electron, e.g. `["--no-sandbox"]` on Linux when Electron's `chrome-sandbox` helper isn't installed as root (as after a plain `npm install`). |
| `steps` | `[]` | `click css "#save"` (or `click testid "save"`), `wait 500`, `reload`. REA's Electron capture clicks CSS selectors, so elements aren't named by role here. |

The app needs a display: on Linux, a desktop session or Xvfb, with `DISPLAY` set where agent-team
runs. REA passes Electron only a few variables (`HOME`, `PATH`, `DISPLAY`, `WAYLAND_DISPLAY`, ...),
not `XAUTHORITY`, so the X cookie has to be in `~/.Xauthority`. A click on something that never
appears waits until the scenario's `timeout` (plus a minute); each run has its own REA process, and
stopping it stops the app.

**api**: a library's public API, read from what was built (nothing runs). Removing or changing a
public member breaks callers; adding one doesn't.

| Key | Default | Meaning |
|---|---|---|
| `assembly` | `""` | .NET: the built assembly, relative to the project, e.g. `out/MyLib.dll` (with `prepare` building it). Public and protected types, methods and fields count. |
| `package` | `""` | JavaScript: the package folder, e.g. `.`. The exports of its entry modules (`exports`, `main`, `module` in package.json) count. |

```toml
# team/behaviour.toml
[[scenarios]]
name = "start and stop a timer"
prepare = "dotnet build -c Release -o out"
run = 'tally() { dotnet "$PROJECT/out/Tally.dll" "$@"; }; tally start client-a; tally stop; tally status'

[[scenarios]]
name = "add a todo"
kind = "browser"
prepare = "npm ci && npm run build"
serve = "npm run preview -- --port 5173 --strictPort"
url = "http://127.0.0.1:5173/"
steps = ['fill textbox "New todo" with "buy milk"', 'press textbox "New todo" Enter', 'wait for text "buy milk"']

[[scenarios]]
name = "count with the desktop app"
kind = "electron"
prepare = "npm ci"
app = "."
steps = ["wait 800", 'click css "#add"', "wait 300"]

[[scenarios]]
name = "public API"
kind = "api"
prepare = "dotnet build -c Release -o out"
assembly = "out/MyLib.dll"
```

**Releases.** With `api` scenarios, the devops member checks the public API since the last release
(`check_api_changes`) before choosing a version, and a release smaller than the changes allow is
refused: removed or changed members need a major version (a minor one while the project is 0.x),
added ones at least a minor one.

**Security from the outside.** After the lead approves, the security member also reviews what the
build ships: the output of the scenarios' `prepare` steps (`out/`, `dist/`, `publish/`, ...) is
searched for credentials, internal addresses (localhost, private networks, staging hosts) and
source maps, and so are the strings REA reads from built .NET assemblies.

**Where it runs.** The program runs with your user's permissions on this machine, as the tests do
when `[sandbox]` is off. With `[sandbox] mode = "container"`, `prepare`, `run` and `serve` run in
the container instead (a browser app is published on this machine's loopback only, so the browser
here can reach it); if the container engine isn't ready, behaviour checks don't run at all rather
than run outside it. `electron` journeys don't run in container mode: REA starts the app on this
machine. Behaviour checks need git: the base version is checked out in a temporary
worktree.

## `[research]` and the scout

A member with `role = "scout"` looks at other products from the outside before the team plans:
with `[research] sites = ["https://..."]`, `discuss` has REA open each page in a browser and read it
the way a visitor or a screen reader does, and the scout writes a short brief for the discussion
(kept under `.team/research/`). It never reaches the builders, and the scout may only be given
observation tools.

A cookie or consent dialog that covers a page hides the rest of it from the scout, as it does from
a screen reader. Give that site steps, in the same plain words as browser journeys (below), and
they run before the page is read:

```toml
[research]
sites = [
  "https://example.com/",
  { url = "https://rival.example/", steps = ['click button "Accept all"'] },
  { url = "https://other.example/", steps = ['click button "Reject all"', "goto /pricing"] },
]
```

Each step gives up after 15 seconds. If one fails (the dialog didn't come, or its button has
another name), the scout reads the page as it first loads, and its brief says the step didn't work.

| Key | Default | Meaning |
|---|---|---|
| `sites` | `[]` | Public pages the scout observes, up to five: a web address, or `{ url, steps }`. |
| `max_chars` | `6000` | Page text read per site, from the top. |

**Guardrails.** Tools that look inside other software (decompilers, disassemblers, debuggers,
extractors) are never given to members who write the project's code (`builder`, `qa`, `docs`), and
the scout may only use observation tools: the team file is refused otherwise.

## `[[agents]]`

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Unique name, used in prompts, logs and `--builder`/`--members`. |
| `role` | required | `lead`, `builder`, `devops`, `marketing`, `factcheck`, `security`, `qa`, `docs`, or any role of your own. |
| `provider` | required | A `[providers.*]` name. |
| `model` | `""` | Model id for the provider (a remote node chooses its own). |
| `effort` | `high` | Reasoning effort for providers that support it. |
| `description` | `""` | Shown to the team; also this member's perspective in discussions. |
| `owns` | `[]` | Path prefixes this member must sign off before a PR touching them can merge. `"*"` means every path. For `qa` and `docs` members it is also where they may write (defaults: test folders; README, `docs/`, CHANGELOG). |
| `prompt` | `""` | A Markdown file (relative to the project) replacing this member's role prompt. Placeholders such as `{name}`, `{project}`, `{roster}`, `{guarantees}` are filled in. |
| `github_token_env` | `""` | The variable holding this member's own GitHub token (a bot account or GitHub App installation). Its comments are posted as that account, and its sign-offs and the lead's verdicts become real GitHub reviews (approve or request changes), so branch protection can require them. |
| `escalate_to` | `""` | A stronger member who takes over this member's build or fix after `[routing].escalate_after` rejected rounds. |
| `mcp` | `[]` | `[mcp.*]` server names. In reviews (the lead) and devops shifts, this member may call those servers' allowed tools. |
| `skills` | `[]` | Markdown files, or folders holding a `SKILL.md` (a Claude Code skill works as it is), added to this member's prompt after its role prompt. Relative to the project; `~` is the home folder. See below. |
| `color` | by role | Terminal colour: orange, cyan, pink, green, yellow, blue, magenta, red. |

### Optional roles in `build`

When the team has them, `build` brings in:

- **`qa`**: writes tests for `PLAN.md` before the builders start, so they build to them.
- **`security`**: reviews the changed files once the lead approves. `SIGN-OFF: NO` sends the
  findings back to the builders for another round. With `owns = ["*"]` it must also sign off
  every pull request in `ship`.
- **`docs`**: updates the README, `docs/` and the changelog after approval.

Leave any out for one run with `--skip qa,security,docs`. With two or more `builder` members,
`build --parallel` has the lead split the plan into parts with separate paths, and the builders
work on them at the same time.

### Skills

Give a member extra knowledge or house rules without replacing its role prompt:

```toml
[[agents]]
name = "Sentinel"
role = "security"
provider = "claude"
model = "claude-sonnet-5-5"
skills = ["team/skills/owasp.md", "~/.claude/skills/security-review"]
```

- A skill is a Markdown file, or a folder with a `SKILL.md`. YAML front matter (`name`,
  `description`) titles it; the rest is the skill.
- Skills are added under "Your skills", after the role prompt, so the workflow's rules and reply
  formats (`VERDICT:`, `SIGN-OFF:`) still hold. `prompt` replaces the role prompt; `skills` add to it.
- They work with every provider, and the roster tells the other members who has which skill.
- They are sent with every call the member makes, so they cost tokens each time; one member's
  skills together are limited to 60,000 characters.
- `agent-team doctor` and the dashboard report a skill that is missing or too large; a run refuses
  to start with one.

