# Configuration: `.team.toml`

`agent-team init` writes a starter file. The full set of settings:

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
```

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
| `escalate_to` | `""` | A stronger member who takes over this member's build or fix after `[routing].escalate_after` rejected rounds. |
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

