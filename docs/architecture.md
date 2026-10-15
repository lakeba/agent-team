# Architecture

agent-team has four layers. Each one can grow without changes to the others.

```
 .team.toml ──► config.Team ──► workflows (discuss, build, market, setup, ship)
                   │                    │ find members by role
                   ▼                    ▼
               AgentConfig ──────► agent.Agent ──► providers.Provider ──► a model somewhere
               (name, role,        (prompt +       anthropic | ollama | openai | agent-http
                owns, model)        history)        | any kind you register
```

## 1. Configuration (`config.py`)

A project's `.team.toml` lists **providers** (how to reach a model) and **agents** (team members).
Agents have a free-form `role`; the built-in workflows look for `lead`, `builder`, `devops`,
`marketing` and optionally `factcheck`. Any other role can still join discussions and own files.
Unknown keys are rejected with a clear message, so typos don't silently change behaviour.

## 2. Providers (`providers/`)

A provider turns `(system prompt, conversation)` into a reply. Built in:

| Kind | Reaches | Notes |
|---|---|---|
| `anthropic` | Claude via the Anthropic API | Streams, shows summarised reasoning, retries dropped connections, cancels and retries a stalled reply, sees images. |
| `ollama` | Ollama, on this machine or another | Retries while the server restarts. |
| `openai` | Any OpenAI-compatible `/v1/chat/completions` server | vLLM, LM Studio, llama.cpp, gateways. |
| `agent-http` | Another machine running `agent-team serve` | That machine keeps its model and credentials; see [remote-agents.md](remote-agents.md). |

Providers register themselves by kind (`@register("kind")`), and configuration is validated
against the registry, so a new kind needs no change anywhere else.

## 3. Agents (`agent.py`, `prompts/`)

An agent joins its config, its provider and an append-only conversation (append-only keeps
provider-side reasoning valid between turns). Its system prompt comes from a Markdown template
for its role, filled with project facts: the roster, the guarantees, the test command and the
paths it owns. A project can replace any member's prompt with its own file (`prompt = "..."`).

## 4. Workflows (`workflows/`)

Each workflow is a plain function over a `Team`. Agents exchange files through `<file path="...">`
blocks, written by `files.write_files`, which refuses paths outside the project or the step's
allowed prefixes. Every run is logged to `.team/logs/<workflow>.md` in the project.

`ship` is different: the devops member drives it with tool use, and the tools are the only way it
can act. With Claude it runs on the Anthropic SDK's tool runner; with any other provider it runs on
`tool_loop.py`, which uses that provider's `complete_tools`. The rules that matter (`merge_blockers`, `is_changelog_rename`) are small pure functions
with their own tests.

## Records

Each workflow appends to `.team/logs/<workflow>.md`; every run and entry heading carries a
timestamp marker, so `logs.py` can rebuild the timeline (older logs without markers still parse).
Every model call appends a line to `.team/usage.jsonl` (member, model, tokens, run), which
`usage.py` turns into cost estimates. `agent-team ui` (`dashboard/`) serves both on 127.0.0.1 with
a strict Content-Security-Policy and a Host check, and never returns secret values. It can also
edit `.team.toml` through `config_io.py`, which renders the file, validates it by reading it back
as the CLI does, shows the diff, and saves atomically with a `.team.toml.bak` backup. Writes need
the page's session token and a same-origin request, and are refused if the file changed on disk.
`agent-team status --json` gives the same summary to the Claude Code side panel (`plugin/hooks/`).

## Trust model

- Facts the tooling verifies (CI status, test counts from CI logs, sign-offs tied to a commit) are
  passed to the models as verified. Claims in PR or issue text are not.
- All agents may share one GitHub account, so a comment that claims a sign-off proves nothing;
  only sign-offs recorded by the tooling for the current head commit count.
- Text from outside the team is wrapped in `<untrusted>` and the prompts say to treat it as data.
- Secrets never go into `.team.toml`: providers name the environment variable that holds them.
  `.env*` files and the config itself are never sent to a model.

## Cost, context and running unattended

- `budget.py` checks `[limits]` before every model call from the usage records, so no workflow
  can run past a spend limit. Remote nodes report the model they ran, so their cost is real.
- `context.py` decides what each prompt includes. Large projects get a map of all files and the
  lead's chosen subset instead of everything; `FILE:` lines widen it during a run.
- `build` runs builders in parallel threads when the plan has parts, each limited to its own
  paths; their streamed output is buffered per thread so it never interleaves.
- `schedule.py` runs shifts on the system scheduler (launchd or cron) behind a lock in `.team/`,
  so two shifts never overlap. `jobs.py` runs any workflow in the background for the dashboard
  and the Claude panel, with its output in `.team/jobs/`.
- `discovery.py` lets nodes answer UDP probes so teams can find them on the local network.

