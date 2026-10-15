# Configuration: `.team.toml`

`agent-team init` writes a starter file. The full set of settings:

## `[project]`

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Project name used in prompts. |
| `repo` | `""` | `owner/name` on GitHub. Needed by `build --pr` and `ship`. |
| `test_command` | `""` | Shell command run in the project after each build round. |
| `test_count_pattern` | `Ran (\d+) tests?` | Regex with one group, matched against CI log lines to read the test count. Empty disables it. |
| `guarantees` | `[]` | Rules the lead enforces in every plan and review. |
| `context_skip` | `[]` | Path prefixes never sent to the models (build output, vendored code, large assets). |
| `context_limit` | `200000` | Maximum characters of project files in one prompt. Raising it costs tokens; prefer `context_skip`. |
| `context` | `auto` | What prompts include. `full`: every file, every time (fails when that's over `context_limit`). `focused`: the lead sees a map of the project and picks the files a task needs; members can ask for more with `FILE: path` lines. `auto`: full when it fits, focused when it doesn't. |

### `[project.marketing]`

`brief`, `site` and `deck` paths for the `market` workflow, and an optional `browser` path for
screenshots (otherwise Chrome, Edge, Chromium or Brave is found automatically).

## `[providers.<name>]`

| Key | Meaning |
|---|---|
| `kind` | `anthropic`, `ollama`, `openai`, `agent-http`, or any registered kind. |
| `url` | Base URL. Required for `openai` and `agent-http`; Ollama defaults to `http://localhost:11434`. |
| `api_key_env` | Name of the environment variable holding a key or token. Never put the value itself here. |
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
