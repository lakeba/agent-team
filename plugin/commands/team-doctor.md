---
description: Check that every agent-team member can be reached (models, local and remote machines)
---

Check this project's agent-team.

1. Find the CLI (`agent-team`, else `~/.agent-team/venv/bin/agent-team`, else `~/agent-team/.venv/bin/agent-team`) and run `agent-team doctor`.
2. Report each member's role, model or machine, the paths it owns, and whether it's reachable.
3. For each failure, give the likely fix:
   - Anthropic: `ANTHROPIC_API_KEY` missing or invalid in the shell profile (never ask for the key).
   - Ollama: the app isn't running, or the model isn't pulled (`ollama pull <model>`).
   - A remote node: it isn't running `agent-team serve`, the URL is wrong, or the token variable
     named by `api_key_env` isn't set on this machine.
4. Also note any missing role a workflow needs (lead, builder, devops, marketing).
