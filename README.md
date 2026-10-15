# agent-team

A configurable team of AI agents that works on a software project the way a small team would:
it plans a roadmap, builds features, reviews them, writes marketing material, and ships through
GitHub with pull requests, CI, sign-offs and releases.

Team members can run on any model and any machine: Claude through the Anthropic API, local
models through Ollama, any OpenAI-compatible server, or another machine running
`agent-team serve`. A team is described in a `.team.toml` file in each project, so adding a
member, a machine or a project is a configuration change.

It grew out of [lakeba/todo-py](https://github.com/lakeba/todo-py), which this team planned,
built, marketed and released (v1.0.0 and v1.0.1).

## How the team works

| Workflow | Command | What happens |
|---|---|---|
| Discuss | `agent-team discuss "next features"` | Members talk in turn until they all agree; the lead updates `ROADMAP.md`. |
| Build | `agent-team build "task" --branch x --pr` | The lead writes `PLAN.md`, builders implement it (in parallel with `--parallel`), tests run each round, the lead reviews until approved, then a PR opens. Optional QA, security and docs members write tests first, review the result and update the docs. |
| Market | `agent-team market` | The marketing member writes a brief, a website and a pitch deck; a fact-checker checks claims and the lead reviews with screenshots. |
| Set up | `agent-team setup --license "MIT, copyright 2026 Lakeba"` | The devops member drafts README, CONTRIBUTING, CHANGELOG, CI and templates. |
| Ship | `agent-team ship` | One devops shift on GitHub: triage, owner sign-offs, lead review, merge, release, feedback digest. `agent-team schedule --every 6h` runs shifts unattended, never two at once. |
| Dashboard | `agent-team ui` | A page on this machine: the team and whether each member is reachable, every run with each member's verdicts, estimated costs per member, day and run, and the GitHub state. Edit members, connections, guarantees and prices there, add a machine with a guided wizard, and review the diff before saving. Start runs there and follow their output live. |

Guardrails are enforced in code, not left to the models. A PR merges only when CI is green, the
lead approved the exact head commit, and every member who owns a changed path signed off that
same commit. Releases need green CI on `main` and a CHANGELOG entry. Text from outside the team
always reaches the models marked as untrusted. Spend limits in `.team.toml` stop any run before it
costs more than you allow, and large projects get a focused context instead of every file.

## Install

Requirements: macOS or Linux, Python 3.11+, git, the [GitHub CLI](https://cli.github.com/) signed in
(`gh auth login`), an Anthropic API key in `ANTHROPIC_API_KEY`, and optionally
[Ollama](https://ollama.com/) for local models.

One command installs the CLI into its own environment under `~/.agent-team`, puts `agent-team` on
your `PATH` (`~/.local/bin`), and installs the Claude Code plugin if Claude Code is present:

```bash
gh api repos/lakeba/agent-team/contents/scripts/install.sh -H "Accept: application/vnd.github.raw" | bash
```

Run it again to update. Options go after `bash -s --`, for example `| bash -s -- --ref v0.1.0`
for a specific version, `--no-plugin` to skip the plugin, or `--uninstall` to remove everything
it installed. If you prefer pipx: `pipx install git+https://github.com/lakeba/agent-team.git`
(that installs the CLI only).

## Quick start

```bash
cd ~/code/my-project
agent-team init       # writes .team.toml and ignores .team/
agent-team doctor     # checks every member can be reached
```

Then edit `.team.toml`: set the project's guarantees, adjust the team, and run a workflow.

### Use it from Claude Code

The installer adds the plugin. To add it by hand, at the prompt of a Claude Code session:

```
/plugin install agent-team --marketplace lakeba/agent-team
```

Then, in any project: `/team-init`, `/team-doctor`, `/team-plan`, `/team-build <task>`,
`/team-ship`, `/team-market` and `/team-ui`. Claude runs the workflow where you can watch it, checks the
result, and reports back. In projects with a `.team.toml`, the plugin also opens an agent-team side
panel (or run `/team-panel`): the team, each member's health, recent runs and spend, with buttons to
refresh, check health, start a devops shift and start the dashboard, plus background runs you can
stop. `/team-run build <task>` (or `discuss <topic>`, `ship`, `market`, `doctor`) starts a run in
the background and the panel follows it. The commands need the `agent-team` CLI on your `PATH`.

## Documentation

- [Architecture](docs/architecture.md): providers, agents, workflows and how they fit.
- [Configuration](docs/configuration.md): every `.team.toml` setting.
- [Extending](docs/extending.md): add a team member, a role, a provider or a workflow.
- [Remote agents](docs/remote-agents.md): let another machine join the team.
- [Examples](examples/): the todo-py team, and a six-member team across four machines.

## Licence

MIT, see [LICENSE](LICENSE).

## Status

Version 0.1.0. The workflows were proven on todo-py; see [ROADMAP.md](ROADMAP.md) for what's next
and [CONTRIBUTING.md](CONTRIBUTING.md) to help.
