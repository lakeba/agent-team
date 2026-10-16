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


def print_checklist(checks) -> None:
    for c in checks:
        mark = "\033[32m✓\033[0m" if c.ok else "\033[31m✕\033[0m"
        need = f"  (needed for {c.needed_for})" if not c.ok and c.needed_for else ""
        ui.say(f"  {mark} {c.name}: {c.detail}{need}")
        if not c.ok and c.fix:
            ui.say(f"      fix: {c.fix}")


def cmd_ready(args) -> int:
    import json as _json
    from . import readiness
    checks = readiness.check(Path(args.project).resolve(), args.ollama_url)
    if args.json:
        print(_json.dumps(readiness.as_dicts(checks)))
    else:
        ui.heading("Readiness")
        print_checklist(checks)
    # Exit 0 even when something's missing: this is a report, not a failure. --strict for scripts.
    return 1 if args.strict and not all(c.ok for c in checks) else 0


def cmd_doctor(args) -> int:
    from . import readiness
    ui.heading("Readiness")
    print_checklist([c for c in readiness.check(Path(args.project).resolve())
                     if not c.name.startswith(("Ollama at", "model "))])   # members are checked below
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
    from . import skills
    for name, problem in skills.problems(team).items():
        failed += 1
        ui.say(f"  {name}: FAILED: {problem}")
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
    init.run(Path(args.project).resolve(), args.builder_provider, args.builder_model, args.force, args.ollama_url)
    return 0


def cmd_discuss(args) -> int:
    from .workflows import discuss
    members = [m.strip() for m in args.members.split(",")] if args.members else None
    return 0 if discuss.run(_team(args), args.topic, members, args.turns) else 2


def cmd_build(args) -> int:
    from .workflows import build
    skip = tuple(s.strip() for s in args.skip.split(",") if s.strip())
    bad = set(skip) - set(build.OPTIONAL)
    if bad:
        raise SystemExit(f"--skip takes {', '.join(build.OPTIONAL)}; not {', '.join(sorted(bad))}")
    ok = build.run(_team(args), args.task, args.rounds, args.lead, args.builder, args.branch, args.pr,
                   parallel=args.parallel, skip=skip)
    return 0 if ok else 2


def cmd_fix(args) -> int:
    from .workflows import fix
    return 0 if fix.run(_team(args), args.number, args.rounds, args.lead, args.builder) else 2


def cmd_autopilot(args) -> int:
    from . import schedule
    from .workflows import autopilot
    try:
        return 0 if autopilot.run(_team(args), args.milestone, args.max_cycles, args.rounds) else 2
    except schedule.AlreadyRunning as e:
        ui.warn(f"Not starting: {e}.")
        return 4


def cmd_market(args) -> int:
    from .workflows import market
    return 0 if market.run(_team(args), args.rounds, args.reuse_brief) else 2


def cmd_setup(args) -> int:
    from .workflows import setup
    return 0 if setup.run(_team(args), args.rounds, args.license) else 2


def cmd_ship(args) -> int:
    from . import schedule
    from .workflows import ship

    def once():
        with schedule.lock(Path(args.project).resolve(), "ship"):
            ship.run(_team(args), args.max_steps, args.release)
    if args.every:
        try:
            every = schedule.parse_every(args.every)
        except ValueError as e:
            raise SystemExit(str(e))
        schedule.loop(every, once)
        return 0
    try:
        once()
    except schedule.AlreadyRunning as e:
        ui.warn(f"Not starting: {e}.")
        return 4
    return 0


def cmd_schedule(args) -> int:
    from . import schedule
    root = _team(args).root
    if args.remove:
        ui.say("Removed the schedule." if schedule.remove(root, args.workflow) else "No schedule was installed.")
        return 0
    if not args.every:
        info = schedule.show(root, args.workflow)
        if not info:
            ui.say(f"No {args.workflow} schedule for this project. Add one with: agent-team schedule --every 6h")
        else:
            every = f"every {info['every'] // 60} minutes" if info.get("every") else "on a schedule"
            ui.say(f"{args.workflow} runs {every} ({info['where']}); output goes to .team/schedule.log")
        return 0
    try:
        every = schedule.parse_every(args.every)
    except ValueError as e:
        raise SystemExit(str(e))
    extra = ["--max-steps", str(args.max_steps)] if args.workflow == "ship" else []
    where = schedule.install(root, args.workflow, every, extra)
    ui.action(f"{args.workflow} will run every {args.every} via {where}; output in .team/schedule.log")
    ui.say("Runs never overlap, and [limits] in .team.toml caps what they spend. Remove with --remove.")
    return 0


def status_data(team: config.Team, with_health: bool = False, recent: int = 8) -> dict:
    """A compact snapshot for the Claude panel and scripts: team, recent runs, spend, optional health."""
    from . import budget, jobs, logs, memory, readiness, schedule, usage
    from .workflows import ship
    from .dashboard.server import health, team_info
    info = team_info(team)
    runs = logs.parse(team.root)
    spend = usage.summarize(usage.load(team.root), team.pricing)
    return {
        **{k: info[k] for k in ("version", "root", "project", "members", "missing_roles")},
        "runs": [{k: r[k] for k in ("workflow", "title", "started", "outcome")} for r in runs[:recent]],
        "run_count": len(runs),
        "spend": {"total": spend["total"], "by_agent": spend["by_agent"],
                  "today": budget.spent(team, run="")["today"],
                  "limits": {"per_run": team.limits.per_run, "per_day": team.limits.per_day}},
        "health": health(team)["members"] if with_health else None,
        "schedule": schedule.show(team.root),
        "release_policy": team.project.release,
        "lessons": len(memory.lessons(team.root)),
        "release_proposal": ship.release_proposal(team.root),
        "attention": [{"name": c.name, "detail": c.detail, "fix": c.fix}
                      for c in readiness.check(team.root) if not c.ok],
        "jobs": [{k: j.get(k) for k in ("id", "workflow", "status", "started", "params")} for j in jobs.list_jobs(team.root, 5)],
    }


def cmd_status(args) -> int:
    import json as _json
    team = _team(args)
    data = status_data(team, args.health)
    if args.json:
        print(_json.dumps(data, default=str))
        return 0
    ui.heading(f"{data['project']['name']} ({data['project']['repo'] or 'no GitHub repo'})")
    for m in data["members"]:
        h = data["health"] and data["health"].get(m["name"])
        mark = "" if h is None else (" ✓" if h["ok"] else " ✕ " + h["status"])
        cost = data["spend"]["by_agent"].get(m["name"], {}).get("cost", 0.0)
        ui.say(f"  {m['name']:<10} {m['role']:<10} {m['kind']}/{m['model'] or '-'}  ${cost:.2f}{mark}")
    sp = data["spend"]
    day_limit = f" of ${sp['limits']['per_day']:.2f}" if sp["limits"]["per_day"] else ""
    ui.say(f"\n  {data['run_count']} runs logged; estimated spend ${sp['total']['cost']:.2f} "
           f"(today ${sp['today']:.2f}{day_limit})")
    if data["release_proposal"]:
        v = data["release_proposal"]["version"]
        ui.say(f"\n  Release v{v} proposed by {data['release_proposal'].get('by', 'devops')}: "
               f"approve with  agent-team ship --release {v}")
    for r in data["runs"][:5]:
        ui.say(f"  - {r['workflow']:<8} {r['title'][:60]}  ({r['outcome'] or '—'})")
    return 0


def cmd_jobs(args) -> int:
    import json as _json
    from . import jobs
    root = _team(args).root
    try:
        if args.action == "start":
            if not args.target:
                raise jobs.JobError("say which workflow: doctor, build, discuss, market or ship")
            params = {k: v for k, v in {"task": args.task, "topic": args.topic, "branch": args.branch,
                                        "pr": args.pr, "parallel": args.parallel, "number": args.number,
                                        "release": args.release, "milestone": args.milestone}.items() if v}
            job = jobs.start(root, args.target, params)
            if args.json:
                print(_json.dumps(job))
            else:
                ui.action(f"started {job['id']}; follow it with: agent-team jobs log {job['id']}")
            return 0
        if args.action == "stop":
            job = jobs.stop(root, args.target)
            ui.say(f"{job['id']}: {job['status']}")
            return 0
        if args.action == "log":
            out = jobs.output(root, args.target)
            ui.say(out["text"], end="")
            ui.say(f"\n[{out['status']}]")
            return 0
    except jobs.JobError as e:
        raise SystemExit(str(e))
    listed = jobs.list_jobs(root)
    if args.json:
        print(_json.dumps(listed))
        return 0
    if not listed:
        ui.say("No background runs. Start one with: agent-team jobs start build --task \"...\"")
    for j in listed:
        what = j["params"].get("task") or j["params"].get("topic") or ""
        ui.say(f"  {j['id']:<34} {j['status']:<13} {what[:50]}")
    return 0


def cmd_keys(args) -> int:
    from . import keys
    if args.action == "list":
        values = keys.read()
        ui.say(f"Keys file: {keys.path()}" + ("" if values else " (empty or missing)"))
        names = sorted(set(values) | ({args.name} if args.name else set()))
        for name in names:
            ui.say(f"  {name:<28} {'set' if values.get(name) else 'not set'} in the file"
                   f"{'; also set in this environment' if name in values and keys.where(name) == 'environment' else ''}")
        if keys.loose_permissions():
            ui.warn(f"{keys.path()} can be read by other users: chmod 600 it")
        return 0
    if not args.name:
        raise SystemExit("say which variable, e.g. agent-team keys set ANTHROPIC_API_KEY")
    if args.action == "remove":
        ui.say(f"Removed {args.name}." if keys.remove(args.name) else f"{args.name} wasn't in the keys file.")
        return 0
    # set: the value comes from this terminal or this shell's environment, never from arguments,
    # so it stays out of shell history, process lists and chat transcripts.
    if args.from_env:
        import os
        value = os.environ.get(args.name, "")
        if not value:
            raise SystemExit(f"{args.name} isn't set in this shell; open the terminal where it is, or leave out --from-env")
    else:
        if not sys.stdin.isatty():
            raise SystemExit("Run this in your own terminal: it asks for the value without showing it.")
        import getpass
        value = getpass.getpass(f"{args.name} (input hidden): ")
    try:
        keys.set_key(args.name, value)
    except ValueError as e:
        raise SystemExit(str(e))
    ui.action(f"saved {args.name} to {keys.path()} (readable only by you)")
    return 0


def cmd_scoreboard(args) -> int:
    import json as _json
    from . import scoreboard
    team = _team(args)
    data = scoreboard.compute(team)
    if args.json:
        print(_json.dumps(data))
        return 0
    pct = lambda v: "—" if v is None else f"{v:.0%}"
    ui.heading("Builders")
    if not data["builders"]:
        ui.say("  No builds logged yet.")
    for name, s in sorted(data["builders"].items()):
        ui.say(f"  {name:<10} {data['models'].get(name, ''):<22} builds {s['builds']:>3}  approved {pct(s['approval_rate']):>4}  "
               f"first round {pct(s['first_round_rate']):>4}  avg rounds {s['avg_rounds'] or '—':>3}  "
               f"fixes {s['fixes_pushed']}/{s['fixes']}  cost ${s['cost']:.2f}")
    ui.heading("Reviewers")
    for name, s in sorted(data["reviewers"].items()):
        ui.say(f"  {name:<10} reviews {s['reviews']:>3}  sign-offs {s['signoffs']:>3}  asked for changes {pct(s['pushback_rate'])}")
    t = data["team"]
    per = f"${t['cost_per_merged_pr']:.2f}" if t["cost_per_merged_pr"] is not None else "—"
    ui.heading(f"Team: {t['merged_prs']} PRs merged, ${t['cost']:.2f} spent, {per} per merged PR")
    return 0


def cmd_memory(args) -> int:
    from . import memory
    root = _team(args).root
    if args.action == "add":
        if not args.text:
            raise SystemExit('say the lesson, e.g. agent-team memory add "Every API change needs a CHANGELOG entry"')
        added = memory.add(root, [args.text], "added by a person")
        ui.say("Added." if added else "Already known (or too short).")
        return 0
    if args.action == "forget":
        try:
            ui.say(f"Forgot: {memory.forget(root, int(args.text))}")
        except ValueError as e:
            raise SystemExit(f"forget takes a lesson number from the list: {e}")
        return 0
    items = memory.lessons(root)
    if not items:
        ui.say("No lessons yet. Reviewers add them (LESSON: lines) when they block for a general reason.")
    for n, i in enumerate(items, 1):
        ui.say(f"  {n:>2}. {i['text']}" + (f"  ({i['source']})" if i["source"] else ""))
    return 0


def cmd_ui(args) -> int:
    from .dashboard.server import serve as serve_ui
    try:
        serve_ui(Path(args.project).resolve(), args.port, not args.no_open)
    except config.ConfigError as e:
        raise SystemExit(f"Config error: {e}")
    except OSError as e:
        raise SystemExit(f"Could not start the dashboard on port {args.port}: {e}. Try --port.")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    serve(args.provider, args.model, args.host, args.port, args.url, args.token_env, args.api_key_env, args.node,
          announce=not args.no_announce)
    return 0


def cmd_discover(args) -> int:
    import json as _json
    from . import discovery
    nodes = discovery.discover(args.timeout)
    if args.json:
        print(_json.dumps(nodes))
        return 0
    if not nodes:
        ui.say("No agent-team nodes answered. Nodes answer when started with `agent-team serve --host 0.0.0.0` "
               "on this network (and a firewall allows UDP 8766).")
        return 1
    for n in nodes:
        ui.say(f"  {n['node']:<20} {n['url']:<28} {n['provider']}/{n['model']}  (agent-team {n['version']})")
    ui.say("\nAdd one with the dashboard's Add a machine, or a [providers.<name>] of kind \"agent-http\".")
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
    s.add_argument("--builder-provider", default="local", choices=["local", "ollama", "claude", "anthropic"],
                   help="local/ollama (an Ollama server) or claude/anthropic")
    s.add_argument("--builder-model", default="", help="default: chosen from the models the Ollama server has")
    s.add_argument("--ollama-url", default="", help="Ollama on another machine, e.g. http://192.168.64.1:11434")
    s.add_argument("--force", action="store_true")
    add("doctor", cmd_doctor, "check this machine is ready and every member is reachable")
    s = add("ready", cmd_ready, "checklist: git, GitHub, keys, Ollama, models (exit 0 unless --strict)")
    s.add_argument("--ollama-url", default="", help="also check an Ollama server before there's a team")
    s.add_argument("--json", action="store_true")
    s.add_argument("--strict", action="store_true", help="exit 1 if anything is missing")
    add("agents", cmd_agents, "list the team")
    s = add("discuss", cmd_discuss, "members discuss and agree a roadmap (writes ROADMAP.md)")
    s.add_argument("topic")
    s.add_argument("--members", default="", help="comma-separated agent names (default: lead + builder)")
    s.add_argument("--turns", type=int, default=12)
    s = add("build", cmd_build, "the lead plans a task, builders implement it, tests run, the lead reviews until approved")
    s.add_argument("task")
    s.add_argument("--rounds", type=int, default=3, help="most build-and-review rounds (default 3)")
    s.add_argument("--lead", default="", help="the member who plans and reviews (default: the lead)")
    s.add_argument("--builder", default="", help="use only this builder (default: every builder)")
    s.add_argument("--branch", default="", help="create this branch first")
    s.add_argument("--pr", action="store_true", help="commit, push and open a PR when approved")
    s.add_argument("--parallel", action="store_true", help="split the plan across every builder, working at once")
    s.add_argument("--skip", default="", help="comma-separated optional steps to leave out: qa,security,docs")
    s = add("fix", cmd_fix, "a builder addresses the review feedback on an open PR and pushes to its branch")
    s.add_argument("number", type=int, help="the pull request number")
    s.add_argument("--rounds", type=int, default=2)
    s.add_argument("--lead", default="")
    s.add_argument("--builder", default="")
    s = add("autopilot", cmd_autopilot, "work through the roadmap a PR at a time: build, review, fix, merge")
    s.add_argument("--milestone", default="", help='e.g. M2; stop when the lead says it is done')
    s.add_argument("--max-cycles", type=int, default=6, help="most builds plus shifts in this run (default 6)")
    s.add_argument("--rounds", type=int, default=3, help="most rounds per build")
    s = add("market", cmd_market, "brief, website and pitch deck, reviewed with screenshots")
    s.add_argument("--rounds", type=int, default=3)
    s.add_argument("--reuse-brief", action="store_true")
    s = add("setup", cmd_setup, "draft README, CONTRIBUTING, CI and other repository files")
    s.add_argument("--rounds", type=int, default=3)
    s.add_argument("--license", default="", help='e.g. "MIT, copyright 2026 Lakeba"')
    s = add("ship", cmd_ship, "run one devops shift: triage, sign-offs, reviews, merges, releases")
    s.add_argument("--max-steps", type=int, default=30)
    s.add_argument("--every", default="", help="keep running a shift this often, e.g. 6h (Ctrl-C stops)")
    s.add_argument("--release", default="", metavar="X.Y.Z",
                   help='approve releasing this version in this shift (for [project].release = "ask")')
    s = add("schedule", cmd_schedule, "run devops shifts on a schedule with the system scheduler")
    s.add_argument("--every", default="", help="how often, e.g. 30m, 6h, 1d (omit to show the schedule)")
    s.add_argument("--workflow", default="ship", choices=["ship", "doctor"])
    s.add_argument("--max-steps", type=int, default=30)
    s.add_argument("--remove", action="store_true", help="remove this project's schedule")
    s = add("status", cmd_status, "summarise the team, recent runs and spend (--json for scripts)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--health", action="store_true", help="also check every member is reachable")
    s = add("jobs", cmd_jobs, "background runs: list, start, stop or show the output of one")
    s.add_argument("action", nargs="?", default="list", choices=["list", "start", "stop", "log"])
    s.add_argument("target", nargs="?", default="", help="workflow to start, or the run id")
    s.add_argument("--task", default="", help="for build")
    s.add_argument("--topic", default="", help="for discuss")
    s.add_argument("--branch", default="", help="for build")
    s.add_argument("--pr", action="store_true", help="for build")
    s.add_argument("--parallel", action="store_true", help="for build")
    s.add_argument("--number", type=int, default=0, help="for fix: the pull request number")
    s.add_argument("--release", default="", help="for ship: approve releasing this version")
    s.add_argument("--milestone", default="", help="for autopilot")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("keys", help="API keys and tokens in agent-team's own keys file (values are never shown)")
    s.add_argument("action", nargs="?", default="list", choices=["list", "set", "remove"])
    s.add_argument("name", nargs="?", default="", help="e.g. ANTHROPIC_API_KEY")
    s.add_argument("--from-env", action="store_true", help="copy the value this shell already has")
    s.set_defaults(fn=cmd_keys)
    s = add("scoreboard", cmd_scoreboard, "how each member and model is doing: approvals, rounds, cost per merged PR")
    s.add_argument("--json", action="store_true")
    s = add("memory", cmd_memory, "what the team learned from its reviews: list, add or forget lessons")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add", "forget"])
    s.add_argument("text", nargs="?", default="", help="the lesson to add, or the number to forget")
    s = add("ui", cmd_ui, "open the dashboard: see and edit the team, start runs, follow costs")
    s.add_argument("--port", type=int, default=8790)
    s.add_argument("--no-open", action="store_true", help="don't open a browser")
    s = sub.add_parser("serve", help="serve a model on this machine as a remote team member")
    s.add_argument("--provider", required=True, choices=["anthropic", "ollama", "openai"])
    s.add_argument("--model", required=True)
    s.add_argument("--url", default="", help="provider base URL (ollama/openai)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--token-env", default="AGENT_TEAM_TOKEN")
    s.add_argument("--api-key-env", default="")
    s.add_argument("--node", default="", help="node name shown to callers (default: hostname)")
    s.add_argument("--no-announce", action="store_true", help="don't answer discovery probes on the network")
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("discover", help="find agent-team nodes on the local network")
    s.add_argument("--timeout", type=float, default=2.0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_discover)

    args = p.parse_args(argv)
    from . import keys
    keys.load_into_env()   # before anything reads a key: works the same from any shell, launchd or cron
    from .budget import SpendLimitError
    try:
        return args.fn(args)
    except SpendLimitError as e:
        ui.warn(f"Stopped: {e}. Raise or remove the limit in [limits] of .team.toml to continue.")
        return 3
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
