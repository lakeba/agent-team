---
description: Open the agent-team dashboard for this project (team, reachability, run history, costs)
argument-hint: [--port 8790]
---

Open the project's agent-team dashboard. Options: $ARGUMENTS

1. Find the CLI (`agent-team`, else `~/.agent-team/venv/bin/agent-team`, else
   `~/agent-team/.venv/bin/agent-team`) and make sure the project has a `.team.toml`; if not,
   suggest `/team-init` and stop.
2. Start it as a long-running process the user can stop: `agent-team ui --no-open` (add `--port`
   if given). If a tool exists to run commands in the user's visible terminal panel, use it;
   otherwise run it in the background. It prints the address, `http://127.0.0.1:<port>/`.
3. Open that address in the browser available to you (an in-app browser pane if there is one),
   or give the user the link.
4. Tell the user what it shows: the team and whether each member is reachable, the history of
   runs with each member's verdicts, estimated costs per member, day and run, and the GitHub state.
   **Edit team** changes members, connections, guarantees and prices; **Add a machine** walks
   through connecting an Ollama server, an OpenAI-compatible server or another agent-team node.
   Every save shows the diff first, is validated, and keeps the previous file as `.team.toml.bak`
   (comments in a hand-written file are not kept). Usage and timestamps exist only for runs made
   since the dashboard was added; older runs show without them.
5. Stop the dashboard when the user is done with it.
