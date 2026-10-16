# Architecture

agent-team has four layers. Each one can grow without changes to the others.

```
 .team.toml ──► config.Team ──► workflows (discuss, build, market, setup, ship)
                   │                    │ find members by role
                   ▼                    ▼
               AgentConfig ──────► agent.Agent ──► providers.Provider ──► a model somewhere
               (name, role,        (prompt +       anthropic | ollama | openai | agent-http
                owns, model)        history)        | any kind you register
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
the lead splits the plan into parts with separate paths.

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

