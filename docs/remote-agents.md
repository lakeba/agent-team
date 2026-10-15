# Remote agents: letting another machine join the team

Any machine with Python 3.11 and agent-team installed can serve a team member. The model, its
credentials and its hardware stay on that machine; the team only needs a URL and a token.

## On the machine that joins

Install agent-team (a node doesn't need the Claude Code plugin). The machine needs the GitHub CLI
signed in with read access to the repository:

```bash
gh api repos/lakeba/agent-team/contents/scripts/install.sh -H "Accept: application/vnd.github.raw" | bash -s -- --no-plugin
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

## On the team's side

```toml
[providers.studio]
kind = "agent-http"
url = "http://studio.tailnet:8765"
api_key_env = "STUDIO_NODE_TOKEN"   # set to the node's AGENT_TEAM_TOKEN

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
  → `{"text": str}`

Both need `Authorization: Bearer <token>`. Errors come back as JSON with a 4xx or 5xx status.
Bodies are limited to 8 MB.
