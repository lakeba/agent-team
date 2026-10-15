---
description: Check that every agent-team member can be reached (models, local and remote machines)
---

Check this project's agent-team.

1. Find the CLI (`agent-team`, else `~/.agent-team/venv/bin/agent-team`, else `~/agent-team/.venv/bin/agent-team`) and run `agent-team doctor`.
2. Report the readiness checklist it prints first (git, GitHub, keys, Ollama), then each member's
   role, model or machine, the paths it owns, and whether it's reachable.
3. For each failure, give the likely fix:
   - Anthropic: the key is missing or invalid. The fix is `agent-team keys set ANTHROPIC_API_KEY`,
     run by the user in their own terminal (never ask for the key in chat). This works whatever
     the shell: on Ubuntu, `~/.bashrc` is skipped by non-interactive shells, so an `export` there
     doesn't reach agent-team.
   - Ollama: the app isn't running, or the model isn't pulled (`ollama pull <model>`). For Ollama
     on another machine: it must listen on the network (`OLLAMA_HOST=0.0.0.0`) with port 11434 open.
   - A remote node: it isn't running `agent-team serve`, the URL is wrong, or the token variable
     named by `api_key_env` isn't set on this machine. `agent-team discover` lists the nodes that
     answer on the local network, with their URLs.
4. Also note any missing role a workflow needs (lead, builder, devops, marketing), and which
   optional members `build` will use (qa, security, docs). Report any member whose skills are
   missing or too large (doctor lists them as FAILED). If `[limits]` isn't set, mention that
   spend limits are available.
