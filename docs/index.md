# agent-team

A configurable team of AI agents that works on a software project the way a small team would: it
plans a roadmap, builds features as pull requests, reviews them, fixes what reviewers ask for,
merges, releases, and writes the marketing material. Members can run on Claude, on local models
through Ollama, on any OpenAI-compatible server, or on another machine.

```bash
pipx install agent-team          # or: curl -fsSL https://raw.githubusercontent.com/lakeba/agent-team/main/scripts/install.sh | bash
cd my-project
agent-team ready && agent-team init   # --no-claude: every member on Ollama, no API key needed
agent-team keys set ANTHROPIC_API_KEY  # only if members use Claude
agent-team ui                     # the dashboard: team, runs, costs, live activity, settings
```

In Claude Code: `/plugin marketplace add lakeba/agent-team`, then `/plugin install agent-team@lakeba-agent-team`,
and `/team-init` in your project.

## Guides

- [Architecture](architecture.md): how providers, members, workflows and the guardrails fit.
- [Configuration](configuration.md): every `.team.toml` setting.
- [Extending](extending.md): add members, roles, machines, providers and workflows.
- [Remote agents](remote-agents.md): let another machine join the team.
- [Publishing](publishing.md): how agent-team itself is released.

The code, issues and changelog are on [GitHub](https://github.com/lakeba/agent-team).
