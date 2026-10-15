# Remote agents: letting another machine join the team

Any machine with Python 3.11 and agent-team installed can serve a team member. The model, its
credentials and its hardware stay on that machine; the team only needs a URL and a token.

## On the machine that joins

Install agent-team (a node doesn't need the Claude Code plugin):

```bash
curl -fsSL https://raw.githubusercontent.com/lakeba/agent-team/main/scripts/install.sh | bash -s -- --no-plugin
```

Then start the node:

```bash
export AGENT_TEAM_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
agent-team serve --provider ollama --model qwen3.8:27b-mlx --port 8765 --node studio
```

- `--provider` is `ollama`, `openai` (with `--url`) or `anthropic` (with `--api-key-env`).
- By default it listens on `127.0.0.1` only. To accept other machines use `--host 0.0.0.0`, and
  put it behind a VPN (Tailscale, WireGuard), an SSH tunnel or an HTTPS reverse proxy: the token
  travels in the request headers.
- Requests are handled one at a time, so a node never overloads its model.

## Finding nodes on the network

A node started with `--host 0.0.0.0` also answers discovery probes on UDP port 8766, saying only
its name, provider, model and port (calling it still needs the token). From the team's machine:

```bash
agent-team discover
```

lists the nodes that answer, and the dashboard's **Add a machine → agent-team node → Find nodes
on this network** fills in the URL for you. Start a node with `--no-announce` to keep it quiet.
Probes are broadcast, so they reach nodes on the same network segment (and through VPNs that
carry broadcasts); elsewhere, type the URL.

## On the team's side

```toml
[providers.studio]
kind = "agent-http"
url = "http://studio.tailnet:8765"
api_key_env = "STUDIO_NODE_TOKEN"   # the node's AGENT_TEAM_TOKEN: agent-team keys set STUDIO_NODE_TOKEN

[[agents]]
name = "Forge"
role = "builder"
provider = "studio"
```

`agent-team doctor` confirms the node answers and shows its model.

## Protocol

Stateless JSON over HTTP, so other implementations can join too:

- `GET /v1/info` → `{"node", "provider", "model", "version"}`
- `POST /v1/turn` with `{"system": str, "messages": [{"role": "user"|"assistant", "content": str}], "effort": str}`
  → `{"text": str, "tool_calls": [], "usage": {"input", "output", "kind", "model"}}`. `usage` names the
  model the node really ran, so the team prices that member correctly.
- With `"tools": [{"name", "description", "input_schema"}]` the same call is one step of a
  tool-using conversation (a devops member on the node): `messages` may also hold
  `{"role": "assistant", "content", "tool_calls": [{"id", "name", "arguments"}]}` and
  `{"role": "tool", "tool_call_id", "name", "content"}`, and the answer's `tool_calls` lists the
  calls the model made. The team runs the tools; the node only runs the model.

Both need `Authorization: Bearer <token>`. Errors come back as JSON with a 4xx or 5xx status.
Bodies are limited to 8 MB.
