# Architecture

agent-team has four layers. Each one can grow without changes to the others.

```
 .team.toml ──► config.Team ──► workflows (discuss, build, market, setup, ship, fix, autopilot)
 team/behaviour.toml │                  │ find members by role       │ behaviour checks
                   ▼                    ▼                              ▼
               AgentConfig ──────► agent.Agent ──► providers.Provider ──► a model somewhere
               (name, role,        (prompt +       anthropic | ollama | openai | agent-http
                owns, model, mcp)   history)        | any kind you register
                   │
                   └──► mcp.Session ──► MCP tool servers (stdio), e.g. REA ──► terminal, browser, binaries
```

## 1. Configuration (`config.py`)

A project's `.team.toml` lists **providers** (how to reach a model) and **agents** (team members).
Agents have a free-form `role`; the built-in workflows look for `lead`, `builder`, `devops`,
`marketing`, and optionally `factcheck`, `qa`, `security` and `docs`. `[limits]` sets spend caps and
`[project].context` how much of the project a prompt includes. Any other role can still join discussions and own files.
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
against the registry, so a new kind needs no change anywhere else. Every built-in kind also
implements `complete_tools`, one step of a tool-using conversation, so any of them can be the
devops member.

## 3. Agents (`agent.py`, `prompts/`)

An agent joins its config, its provider and an append-only conversation (append-only keeps
provider-side reasoning valid between turns). Its system prompt comes from a Markdown template
for its role, filled with project facts: the roster, the guarantees, the test command and the
paths it owns. A project can replace any member's prompt with its own file (`prompt = "..."`), or
add to it with `skills` (`skills.py`): Markdown files or skill folders appended after the role
prompt, so the workflow's reply formats still hold.

## 4. Workflows (`workflows/`)

Each workflow is a plain function over a `Team`. Agents exchange files through `<file path="...">`
blocks, written by `files.write_files`, which refuses paths outside the project or the step's
allowed prefixes. Every run is logged to `.team/logs/<workflow>.md` in the project.

`ship` is different: the devops member drives it with tool use, and the tools are the only way it
can act. With Claude it runs on the Anthropic SDK's tool runner; with any other provider it runs
on `tool_loop.py`, which uses that provider's `complete_tools`. The rules that matter
(`merge_blockers`, `is_changelog_rename`) are small pure functions with their own tests.

Review rules: the lead's approval of a commit is also its sign-off on paths it owns, and a
re-review gets the reviewer's earlier review with the rule to block only on unresolved points or
problems the new commit introduces (`RE_REVIEW` in `ship.py`).

`fix` closes the review loop: when a shift's lead review requests changes on a team PR, a
builder applies that review (read from the team's own ship log; PR comments arrive as untrusted)
on the PR's branch, the lead confirms the blocking points, and only then is it pushed. Approvals
stay tied to commits, so the next shift reviews the new head before anything merges.

`build` brings in the optional members when the team has them: a `qa` member writes tests for the
plan first, a `security` member reviews the result once the lead approves (a NO sends it back),
and a `docs` member updates the documentation afterwards. With several builders and `--parallel`,
the lead splits the plan into parts with separate paths. With behaviour checks set up, the QA
member (or the lead) also writes the task's journeys into `team/behaviour.toml` before anyone
builds (`workflows/journeys.py`), and every round runs them after the tests (`behaviour.py`).

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
- MCP tool servers start with a small environment (no API keys), members see only the tools a
  server's allowlist names, and every result reaches the models as untrusted, cut to `max_output`.
  So does what behaviour checks capture: it's the output of code the team wrote.
- Members who write code (builder, QA, docs) can't be given tools that look inside other software,
  and the scout may only observe; `config.py` refuses the team file otherwise. The scout's brief
  goes to `discuss` only.

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

## Edits, tool reviews, memory and autopilot (0.3)

- `files.write_files` applies `<edit>` blocks (SEARCH/REPLACE pairs that must match once) as well
  as whole `<file>` blocks. A file whose edit doesn't apply is left unchanged, and the problem goes
  back to the builder and the lead (`Written.problems`, `files.problems_note`).
- `review_tools.py` gives reviewers read_file, list_files, search, diff and run_tests through
  `tool_loop`, for any provider that can call tools. `build` and `fix` use it for the lead's
  reviews unless `[project].review = "snapshot"`.
- `ship`'s `request_fix` runs `fix` inside the shift and waits for CI, so one shift can take a PR
  from "changes requested" to merged; approvals are still tied to the new commit.
- `workflows/autopilot.py` alternates shifts (while team PRs are open) and builds (the lead picks
  the next roadmap task), under its own lock and the spend limits.
- `memory.py` keeps reviewers' `LESSON:` lines in `.team/memory.md` and adds them to every member's
  prompt; `scoreboard.py` derives per-member results from the logs and usage records.

## To-do list, routing, gates and notifications (0.4)

- `issues.py`: `team:build` issues are the team's to-do list; autopilot builds the oldest open one
  (its body arrives as untrusted) and the PR closes it.
- `routing.py`: `escalate_to` hands a member's work to a stronger member after rejected rounds;
  `light_model` runs owners' sign-offs and fact-checks on a cheaper Claude model.
- `gates.py`: `require_approval` paths add a merge rule, the owners' approval of the exact head
  commit, recorded on this machine (never through GitHub, where the agents post as the same user).
- `secret_scan.py`: `build` and `fix` scan the staged changes and refuse to commit or push secrets.
- `notify.py`: webhook messages for the events above; a failed notification never stops a run.
- `tests/test_guardrails.py` runs whole devops shifts against a stand-in GitHub with a scripted devops
  member, so the merge rules are checked end to end, whatever a model asks for.

## Safety, proof and reach (0.5)

- `sandbox.py`: the test command runs through `docker`/`podman run --rm` with only the project
  mounted, no network unless allowed, no environment, and resource limits; `build`, `fix` and the
  reviewers' `run_tests` all go through it.
- `estimate.py` predicts run costs from past runs; `[limits.milestones]` budgets autopilot per
  milestone (usage entries carry the milestone).
- `rank.py`: BM25 over paths and contents gives the lead a ranked shortlist in focused context.
- Per-member `github_token_env` posts comments and real GitHub reviews as that member.
- `evals.py`: fixed scenarios with real models in a throwaway project, saved under `.team/evals/`.
- Dashboard: `metrics.py` (Activity), `templates.py` (Settings), `projects.py` (the control room,
  from `~/.config/agent-team/projects.json`).
- `.github/workflows/release.yml` publishes tagged versions to PyPI (trusted publishing) and GitHub
  Releases; `packaging/homebrew/` holds the tap formula; `docs/` is the GitHub Pages site.

## Setup, vision and tool servers (0.6, 0.7)

- `composition.py` describes a team (where the models run, which members, how many builders,
  spend limits) once: `init` writes a new team file from it, from questions in a terminal or from
  flags, and the dashboard's Team composition card applies it to an existing team as a diff.
  `readiness.find_ollama` looks for Ollama on this machine, at `OLLAMA_HOST`, on a VM's or a
  container's host and at the gateway.
- `VISION.md` is the owner's description of the product: every workflow receives it with the
  README (`context.ALWAYS`), and `discuss` gives it its own section.
- `completion.py`: Tab completion from the CLI's own parser, with the team's member names.
- `mcp.py` is a small MCP client (JSON-RPC over stdio). `Session` starts a member's servers for one
  task; `Tool` gives each allowed tool the shape the tool loop uses, so any provider that can call
  tools can call MCP tools; members' MCP tools are offered in reviews (`review_tools.review`) and
  devops shifts.

## Behaviour checks with REA (0.8)

- `behaviour.py` runs each scenario on the base commit (a temporary git worktree) and on the work,
  through REA's MCP tools: `capture_process_scenario` (terminal), `capture_browser_scenario` with
  steps from `steps.py` (browser), `inspect_managed_members` and `analyze_javascript_application`
  (api). It compares what a user would notice (the final screen, the page's accessibility text,
  URL, errors, a screenshot ratio, the public API) rather than raw bytes, keeps the evidence under
  `.team/evidence/`, and writes the report the lead reviews. With the container sandbox, prepare,
  run and serve go into the container through `sandbox.container`.
- `rea.py` finds REA (agent-team's pinned copy, the PATH, Claude Code's registration), installs it
  into agent-team's folder, and writes `[mcp.rea]` and `[behaviour]`.
- `release_check.py`: the public API since the last release tag sets the smallest allowed version,
  and `ship`'s `create_release` refuses smaller ones.
- `outside_in.py`: after approval, the security member also gets what the build ships (secrets,
  internal addresses and source maps in build output, and strings REA reads from .NET assemblies).
- `workflows/scout.py`: the scout observes `[research] sites` through REA's browser before `discuss`.
- The dashboard's Behaviour tab reads `.team/evidence/` (`/api/behaviour`, screenshots through
  `/api/evidence/<check>/<n>-base|work.png`).

