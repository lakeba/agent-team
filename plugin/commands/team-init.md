---
description: Set up an agent-team for this project (checks the machine first, then writes .team.toml)
argument-hint: [--ollama-url http://HOST:11434] [--builder-provider local|claude] [--builder-model NAME]
---

Set up an agent-team for this project. Options: $ARGUMENTS

Work in this order: check first, ask only what's still open, then write. Commands that look for
something missing must not fail: `agent-team ready` always exits 0 and reports what it found.

1. **Find the CLI** with `command -v agent-team || ls ~/.agent-team/venv/bin/agent-team ~/agent-team/.venv/bin/agent-team 2>/dev/null; true`.
   If there is none, tell the user to install it with the one-line installer in the agent-team
   README, and stop.
2. **Check readiness:** `agent-team ready --json` (add `--ollama-url` if given). Show the user one
   short checklist: git repository, GitHub CLI, GitHub repo, team file, Anthropic key, Ollama.
   If a `.team.toml` already exists, show its team (`agent-team agents`) and stop unless the user
   asked to start over (then pass `--force` below).
3. **Fix what's missing, with the user's go-ahead for each:**
   - No git repository: offer to run `git init -b main` and make a first commit of the current
     files (show which files; never commit secrets or `.env` files).
   - No GitHub repository: offer to create one with `gh repo create <folder-name> --private --source . --push`
     (agent-team then reads the repo from `origin`; nothing to edit by hand).
     Private unless the user says otherwise. If `gh` isn't signed in, tell them to run
     `gh auth login` in their own terminal. Without a repo the team can't open pull requests;
     setup can continue and the repo can be added later.
   - No Anthropic key: tell the user to run `agent-team keys set ANTHROPIC_API_KEY` **in their own
     terminal** (it asks for the key without showing it and saves it where every agent-team
     command finds it, whatever the shell). Never ask them to paste a key into the chat. If the
     key is already exported in their terminal, `agent-team keys set ANTHROPIC_API_KEY --from-env`
     copies it.
4. **Ask where the builder's model runs** (one question):
   - Ollama on this machine (only offer if the checklist found it reachable);
   - Ollama on another machine: ask for its address, then check it with
     `agent-team ready --ollama-url http://HOST:11434 --json`. If it isn't reachable, explain that
     Ollama on that machine must listen on the network (`OLLAMA_HOST=0.0.0.0`, then restart it) and
     that port 11434 must be open, and let the user choose again;
   - Claude (no local model needed).
   For Ollama, `init` picks the builder's model from the models that server has pulled; mention
   which one it chose and the others, so the user can change it.
5. **Ask which optional members to add** (multi-select, "None" allowed): Sentinel (security review
   of every build and sign-off of every PR), Probe (QA: writes tests first) and Quill (docs).
   Then ask whether to set spend limits (`[limits] per_run`, `per_day` in US dollars); "No limits"
   is a fine answer.
6. **Write the file:** `agent-team init` with `--ollama-url` and `--builder-provider` /
   `--builder-model` from the answers. It detects the test command and the test-count pattern
   (Python, Jest, Vitest, Mocha, Node's built-in runner) and the test folder, and adds `.team/` and
   `.team.toml.bak` to `.gitignore`. Uncomment the optional members chosen and add any limits.
7. **Make it specific to this project:** read the README, main source files, tests and CI, and
   propose concrete `guarantees` (the rules every change must keep) and `context_skip` entries
   (build output, vendored code, large assets). Check that `test_count_pattern` matches what the
   test command prints; fix it if not. Show the changes and apply them when the user agrees.
8. **Confirm:** run `agent-team doctor` and report the checklist and each member. If anything is
   still missing, say exactly which command fixes it. Remind the user that `.team.toml` holds no
   secrets and can be committed, and suggest `/team-plan` as a first step once everything is ✓.
