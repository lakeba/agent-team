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

## `[[agents]]`

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Unique name, used in prompts, logs and `--builder`/`--members`. |
| `role` | required | `lead`, `builder`, `devops`, `marketing`, `factcheck`, or any role of your own. |
| `provider` | required | A `[providers.*]` name. |
| `model` | `""` | Model id for the provider (a remote node chooses its own). |
| `effort` | `high` | Reasoning effort for providers that support it. |
| `description` | `""` | Shown to the team; also this member's perspective in discussions. |
| `owns` | `[]` | Path prefixes this member must sign off before a PR touching them can merge. |
| `prompt` | `""` | A Markdown file (relative to the project) replacing this member's role prompt. Placeholders such as `{name}`, `{project}`, `{roster}`, `{guarantees}` are filled in. |
| `color` | by role | Terminal colour: orange, cyan, pink, green, yellow, blue, magenta, red. |
