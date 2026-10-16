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
   - No git identity (the checklist's "git identity"): commits would fail. Ask the user which name
     and email to use and offer `git config --global user.name ...` / `user.email ...`, or only for
     this repository without `--global`. Don't guess them.
   - No GitHub repository: offer to create one with `gh repo create <folder-name> --private --source . --push`
     (agent-team then reads the repo from `origin`; nothing to edit by hand).
     Private unless the user says otherwise. If `gh` isn't signed in, tell them to run
     `gh auth login` in their own terminal. Without a repo the team can't open pull requests;
     setup can continue and the repo can be added later.
   The Anthropic key is not a requirement here: the checklist shows it as optional (○). It only
   matters if the user chooses Claude in step 4.
4. **Ask for the product vision** (one free-text question; skipping is fine): what should this
   product be, who is it for, what problem does it solve. If the project already has `VISION.md`,
   show its first lines instead and don't ask. Pass the answer to `init` as `--vision "<text>"`;
   it's saved as `VISION.md`, which every workflow reads and `/team-plan` plans the roadmap from.
   Then **ask which models the team uses** (one question):
   - Claude leads and reviews, the builder on Ollama (the default team);
   - Everything on Ollama, on this machine or other machines: no Claude and no Anthropic key
     (`agent-team init --models ollama`). Mention that the devops member acts through tool calls, so
     its model should be good at them;
   - Everything on Claude (no local model needed).
   If Claude is used and the checklist found no key, tell the user to run
   `agent-team keys set ANTHROPIC_API_KEY` **in their own terminal** (it asks for the key without
   showing it and saves it where every agent-team command finds it, whatever the shell). Never ask
   them to paste a key into the chat. If it's already exported in their terminal,
   `agent-team keys set ANTHROPIC_API_KEY --from-env` copies it. They can also add the key later.
   Then, if Ollama is used, **ask where it runs** (one question). First run
   `agent-team discover --ollama --json`: it lists every Ollama server that answers on this
   machine, at `OLLAMA_HOST`, on the host of a VM or container, or at the gateway, with its models.
   Offer those, plus:
   - Ollama on another machine: ask for its address, then check it with
     `agent-team ready --ollama-url http://HOST:11434 --json`. If it isn't reachable, explain that
     Ollama on that machine must listen on the network (`OLLAMA_HOST=0.0.0.0`, then restart it) and
     that port 11434 must be open, and let the user choose again;
   For Ollama, `init` picks the builder's model from the models that server has pulled; mention
   which one it chose and the others, so the user can change it.
5. **Ask which optional members to add** (multi-select, "None" allowed): Sentinel (security review
   of every build and sign-off of every PR), Probe (QA: writes tests first) and Quill (docs).
   Ask how many builders (1 to 4; more than one lets `build --parallel` split a plan). Then ask
   whether to set spend limits (`[limits] per_run`, `per_day` in US dollars); "No limits" is a fine
   answer.
6. **Write the file:** `agent-team init --yes` with the answers as flags: `--models`
   (`mixed`, `ollama` or `claude`), `--vision`, `--ollama-url`, `--members` (comma-separated: `security`,
   `qa`, `docs`; `none` for none), `--builders N`, `--per-run` / `--per-day`, and `--builder-model`
   if the user picked a model. Always pass `--yes`: in Claude Code there is no terminal for `init`'s
   own questions. `init` checks the file it
   writes, so a successful run needs no repair. It detects the test command and the test-count pattern
   (Python, Jest, Vitest, Mocha, Node's built-in runner, Go, Cargo, .NET's `dotnet test`) and the
   test folder (`tests/`, or a .NET `App.Tests/` project), and adds `.team/` and `.team.toml.bak` to
   `.gitignore` (and `bin/`, `obj/` for .NET). The chosen members and limits are written by the flags.
7. **Make it specific to this project:** read the README, main source files, tests and CI, and
   propose concrete `guarantees` (the rules every change must keep) and `context_skip` entries
   (vendored code, large assets; files git ignores are never sent, so build output in `.gitignore`
   needs no entry). Check that `test_count_pattern` matches what the
   test command prints; fix it if not. CI logs put a timestamp before every line, so the pattern
   must not start with `^`. Show the changes and apply them when the user agrees.
8. **Behaviour checks:** if `agent-team rea status` says REA isn't installed, offer `agent-team rea
   setup` (it asks before installing, so run it where the user can answer, or with `--yes` once they
   agree). `init` already set REA up if it was installed. Then offer `agent-team behaviour suggest`,
   which has the lead write the first journeys from VISION.md.
9. **Confirm:** run `agent-team doctor` and report the checklist and each member. If anything is
   still missing, say exactly which command fixes it. Remind the user that `.team.toml` holds no
   secrets and can be committed, and suggest `/team-plan` as a first step once everything is ✓.
