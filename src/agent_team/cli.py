"""The `agent-team` command."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config, providers, ui


def _team(args) -> config.Team:
    try:
        return config.load(Path(args.project).resolve())
    except config.ConfigError as e:
        raise SystemExit(f"Config error: {e}")


def cmd_doctor(args) -> int:
    team = _team(args)
    ui.heading(f"{team.project.name} ({team.project.repo or 'no GitHub repo'}), {len(team.agents)} agents")
    failed = 0
    for a in team.agents.values():
        pcfg = team.providers[a.provider]
        try:
            status = providers.build(pcfg, team.secret(pcfg)).check(a.model)
        except Exception as e:
            status = f"FAILED: {e}"
        failed += status.startswith("FAILED")
        owns = f" owns {', '.join(a.owns)}" if a.owns else ""
        ui.say(f"  {ui.label(a.name, a.role, a.color)}  {pcfg.kind}/{a.model or '-'}{owns}\n      {status}")
    for role in ("lead", "builder", "devops"):
        if not team.by_role(role, required=False):
            ui.warn(f"no {role!r} agent: the workflows that need one won't run")
    return 1 if failed else 0


def cmd_agents(args) -> int:
    team = _team(args)
    from .agent import team_roster
    ui.say(team_roster(team))
    return 0


def cmd_init(args) -> int:
    from .workflows import init
    init.run(Path(args.project).resolve(), args.builder_provider, args.builder_model, args.force)
    return 0


def cmd_discuss(args) -> int:
    from .workflows import discuss
    members = [m.strip() for m in args.members.split(",")] if args.members else None
    return 0 if discuss.run(_team(args), args.topic, members, args.turns) else 2


def cmd_build(args) -> int:
    from .workflows import build
    ok = build.run(_team(args), args.task, args.rounds, args.lead, args.builder, args.branch, args.pr)
    return 0 if ok else 2


def cmd_market(args) -> int:
    from .workflows import market
    return 0 if market.run(_team(args), args.rounds, args.reuse_brief) else 2


def cmd_setup(args) -> int:
    from .workflows import setup
    return 0 if setup.run(_team(args), args.rounds, args.license) else 2


def cmd_ship(args) -> int:
    from .workflows import ship
    ship.run(_team(args), args.max_steps)
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    serve(args.provider, args.model, args.host, args.port, args.url, args.token_env, args.api_key_env, args.node)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agent-team", description="A configurable team of AI agents for a project.")
    p.add_argument("--version", action="version", version=f"agent-team {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("-C", "--project", default=".", help="project folder (default: current)")
        s.set_defaults(fn=fn)
        return s

    s = add("init", cmd_init, "write a starter .team.toml for this project")
    s.add_argument("--builder-provider", default="local")
    s.add_argument("--builder-model", default="qwen3.8:27b-mlx")
    s.add_argument("--force", action="store_true")
    add("doctor", cmd_doctor, "check every agent's provider is reachable")
    add("agents", cmd_agents, "list the team")
    s = add("discuss", cmd_discuss, "members discuss and agree a roadmap (writes ROADMAP.md)")
    s.add_argument("topic")
    s.add_argument("--members", default="", help="comma-separated agent names (default: lead + builder)")
    s.add_argument("--turns", type=int, default=12)
    s = add("build", cmd_build, "the lead plans a task, a builder implements it, until approved")
    s.add_argument("task")
    s.add_argument("--rounds", type=int, default=3)
    s.add_argument("--lead", default="")
    s.add_argument("--builder", default="")
    s.add_argument("--branch", default="", help="create this branch first")
    s.add_argument("--pr", action="store_true", help="commit, push and open a PR when approved")
    s = add("market", cmd_market, "brief, website and pitch deck, reviewed with screenshots")
    s.add_argument("--rounds", type=int, default=3)
    s.add_argument("--reuse-brief", action="store_true")
    s = add("setup", cmd_setup, "draft README, CONTRIBUTING, CI and other repository files")
    s.add_argument("--rounds", type=int, default=3)
    s.add_argument("--license", default="", help='e.g. "MIT, copyright 2026 Lakeba"')
    s = add("ship", cmd_ship, "run one devops shift: triage, sign-offs, reviews, merges, releases")
    s.add_argument("--max-steps", type=int, default=30)
    s = sub.add_parser("serve", help="serve a model on this machine as a remote team member")
    s.add_argument("--provider", required=True, choices=["anthropic", "ollama", "openai"])
    s.add_argument("--model", required=True)
    s.add_argument("--url", default="", help="provider base URL (ollama/openai)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--token-env", default="AGENT_TEAM_TOKEN")
    s.add_argument("--api-key-env", default="")
    s.add_argument("--node", default="", help="node name shown to callers (default: hostname)")
    s.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
