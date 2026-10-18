# Extending the team

How to grow the team that agent-team, the engine of Lakeba OS, runs: new members, roles, machines,
tools and providers.

## Add a team member (no code)

Add an `[[agents]]` entry to `.team.toml`:

```toml
[[agents]]
name = "Sentinel"
role = "reviewer"
provider = "claude"
model = "claude-sonnet-5-5"
description = "Security reviewer: authentication, secrets, input validation."
owns = ["src/auth/"]
```

Sentinel now appears in every prompt's roster, can join discussions
(`agent-team discuss "..." --members Atlas,Forge,Sentinel`), and must sign off any PR that touches
`src/auth/`. A second builder works the same way: `agent-team build "..." --builder Anvil`, or
`--parallel` to split one plan across every builder. The built-in `security`, `qa` and `docs` roles
join `build` automatically; see [configuration.md](configuration.md#optional-roles-in-build).

## Give a member skills (no code)

`skills = ["team/skills/api-style.md", "~/.claude/skills/security-review"]` on a member adds those
Markdown files (or skill folders with a `SKILL.md`) to its prompt, on top of its role. Use it for
checklists, conventions and domain knowledge one member needs; see
[configuration.md](configuration.md#skills).

### Start from a template, or take pieces from the library

`agent-team templates apply` gives each member the built-in reviewer or skill that fits its role and
the project's language, everyone the language's rules, and turns on the library. To pick pieces
yourself:

```bash
agent-team library skills testing             # search; also: agents, playbooks, rules
agent-team library give python-testing --to Probe
agent-team library hire architect             # a specialist as a new member (its own role by default)
agent-team library add-rules python           # common + python by default: the project's language
agent-team library on                         # every built-in skill, read only when a task needs it
```

Pieces are copied into `team/skills/` and `team/rules/`; edit or drop them like any other file. To add
your own skills to the on-demand library, put skill folders (each with a `SKILL.md`) or Markdown files
in a folder and list it in `[project].library`, e.g. `["builtin", "team/library", "~/.claude/skills"]`.

### Run a playbook, or write your own

A playbook is a written procedure. `agent-team playbook run NAME "what for"` has the lead (or
`--member`) follow it: `report` playbooks report without changing files, `build` playbooks become a
build (`--branch`, `--pr`); `--report` and `--build` override. Write your own in `team/playbooks/NAME.md`:

```markdown
---
name: release-notes
description: Draft release notes for the marketing site
mode: report
---
Draft release notes for $ARGUMENTS from the changelog, for customers, in our voice.
```

A project playbook with the same name as a built-in one replaces it. Coding agents connected with
`agent-team mcp` see every playbook as an MCP prompt.

## Add a role (no code)

Use any role name and give the member a prompt file:

```toml
[[agents]]
name = "Babel"
role = "localisation"
provider = "claude"
model = "claude-sonnet-5-5"
prompt = "team/babel.md"
owns = ["locales/"]
```

`team/babel.md` may use `{name}`, `{role}`, `{project}`, `{repo}`, `{roster}`, `{guarantees}`,
`{owns}` and `{test_command}`.

## Add a machine

- Another machine with Ollama: add a provider with `kind = "ollama"` and its `url`, for example
  `http://studio.local:11434`. Ollama listens only on its own machine by default: on the machine
  that runs it, set `OLLAMA_HOST=0.0.0.0` (on macOS: `launchctl setenv OLLAMA_HOST 0.0.0.0`, then
  restart the Ollama app; on Linux: `Environment="OLLAMA_HOST=0.0.0.0"` in its systemd service).
  Ollama has no authentication, so only do this on a network you trust.
- A GPU server with vLLM, LM Studio or llama.cpp: `kind = "openai"` and its `url`.
- Anything else, or a machine that should keep its own credentials: run `agent-team serve` there
  and add `kind = "agent-http"`. See [remote-agents.md](remote-agents.md); `agent-team discover`
  finds such nodes on the local network.

Every kind can be the devops member: Claude runs `ship` on the Anthropic tool runner, and Ollama,
OpenAI-compatible servers and remote nodes run it through the same tools with their own tool
calling (`tool_loop.py`). Pick a model that is good at tool use.

## Add a tool server (no code)

Any local MCP server (stdio) can give the team tools: REA, a browser, a database, your own. Add it
under `[mcp.<name>]` with the tools members may call, then list it on the members that use it:

```toml
[mcp.rea]
command = "rea"
args = ["--mcp"]
tools = ["capture_process_scenario"]   # only these are offered; servers can have hundreds

[[agents]]
name = "Atlas"
role = "lead"
mcp = ["rea"]                          # in its reviews (and a devops member's shifts)
```

The server starts with a small environment (put tokens it needs in `env_from`, never in the file),
results reach the models marked as untrusted and cut to `max_output`, and `agent-team doctor`
checks that it starts and offers its tools. Each allowed tool's description is sent with every
model call, so allow only what the member needs. Members who write code can't be given tools that
look inside other software, and a scout only observation tools.

## Add behaviour checks (no code)

`agent-team rea setup` installs and configures REA; `agent-team behaviour suggest` has the lead
write the first journeys into `team/behaviour.toml` from `VISION.md`. Edit them like any project
file, or let `build` add the ones each task needs (the QA member writes them, or the lead). A
journey is a command line (`run`, typed `input`), a web app (`serve`, `url`, `steps` such as
`click button "Start"`), an Electron app (`app`, steps such as `click css "#save"`) or a library's
public API (`assembly` for .NET, `package` for JavaScript).
`agent-team behaviour run` compares your working tree with HEAD right away. See
[configuration.md](configuration.md#behaviour-and-behaviour-scenarios).

## Add a scout (no code)

```toml
[research]
sites = ["https://a-competitor.example/features"]

[[agents]]
name = "Scout"
role = "scout"
provider = "claude"
model = "claude-sonnet-5-5"
```

Before each `discuss`, REA opens those pages in a browser and the scout briefs the team on what it
saw, from the outside only. The brief goes to the discussion, never to the builders.

## Add a provider kind (code)

```python
# src/agent_team/providers/my_provider.py
from .base import Provider, Reply, register, text_messages

@register("my-kind")
class MyProvider(Provider):
    def complete(self, system, messages, *, model, effort, label):
        text = call_my_service(system, text_messages(messages), model)
        return Reply(text=text, content=text)

    def check(self, model):
        return "ok"
```

Import it in `providers/__init__.py`, add a test, and `kind = "my-kind"` becomes valid in
`.team.toml`. Set `supports_images = True` only if the endpoint accepts Anthropic-style image
blocks.

## Add a workflow (code)

A workflow is a function `run(team: Team, ...)` in `workflows/`. Find members with
`team.by_role(...)` or `team.get(name)`, build them with `agent.make(team, cfg, "<prompt>")`,
exchange files with `files.write_files(..., allowed=...)`, and log with `files.Log`. Add the
command in `cli.py` and tests with the scripted provider in `tests/helpers.py`.
