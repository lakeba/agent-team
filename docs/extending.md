# Extending the team

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

- Another machine with Ollama: add a provider with `kind = "ollama"` and its `url`.
- A GPU server with vLLM, LM Studio or llama.cpp: `kind = "openai"` and its `url`.
- Anything else, or a machine that should keep its own credentials: run `agent-team serve` there
  and add `kind = "agent-http"`. See [remote-agents.md](remote-agents.md); `agent-team discover`
  finds such nodes on the local network.

Every kind can be the devops member: Claude runs `ship` on the Anthropic tool runner, and Ollama,
OpenAI-compatible servers and remote nodes run it through the same tools with their own tool
calling (`tool_loop.py`). Pick a model that is good at tool use.

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
