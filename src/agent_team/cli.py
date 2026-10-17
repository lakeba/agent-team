"""The `agent-team` command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, config, providers, ui


def _team(args) -> config.Team:
    try:
        team = config.load(Path(args.project).resolve())
    except config.ConfigError as e:
        raise SystemExit(f"Config error: {e}")
    from . import projects
    projects.register(team.root)
    return team


def print_checklist(checks) -> None:
    for c in checks:
        mark = ("\033[32m✓\033[0m" if c.ok else "\033[2m○\033[0m" if getattr(c, "optional", False)
                else "\033[31m✕\033[0m")
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
    return 1 if args.strict and not all(c.ok or c.optional for c in checks) else 0


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
    from . import audit, rules
    problem = rules.problem(team)
    if problem:
        failed += 1
        ui.say(f"  [project].rules: FAILED: {problem}")
    from . import library
    problem = library.problem(team)
    if problem:
        failed += 1
        ui.say(f"  FAILED: {problem}")
    if team.project.rules or team.project.library:
        ui.say(f"  rules: {len(team.project.rules)} entries; library: {', '.join(team.project.library) or 'off'}")
    found = audit.run(team)
    serious = found["counts"]["critical"] + found["counts"]["high"]
    ui.say(f"  audit: {found['score']}/100, grade {found['grade']}" +
           (f" ({serious} critical or high findings: agent-team audit)" if serious else ""))
    if team.mcp:
        from . import mcp
        ui.heading("Tool servers (MCP)")
        for name in team.mcp:
            ok, detail = mcp.check(team, name)
            failed += not ok
            users = [a.name for a in team.agents.values() if name in a.mcp]
            role = (["behaviour checks"] if team.behaviour.scenarios and team.behaviour.server == name else []) + users
            ui.say(f"  {name}  ({', '.join(role) or 'not used yet'})\n      {'ok' if ok else 'FAILED'}: {detail}")
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
    extras = None
    if args.members is not None:
        extras = tuple(x.strip().lower() for x in args.members.split(",") if x.strip() and x.strip().lower() != "none")
        if "all" in extras:
            from .composition import EXTRAS
            extras = tuple(EXTRAS)
    # In a terminal, init asks about every choice the flags leave open; --yes (or a script) takes the defaults.
    interactive = not args.yes and sys.stdin.isatty() and sys.stdout.isatty()
    init.run(Path(args.project).resolve(), args.builder_provider, args.builder_model, args.force, args.ollama_url,
             args.no_claude, models=args.models, extras=extras, builders=args.builders,
             per_run=args.per_run, per_day=args.per_day,
             interactive=interactive, vision=args.vision, use_rea=False if args.no_rea else None)
    if args.no_claude or args.models == "ollama":
        ui.say("Every member runs on Ollama, so no Anthropic key is needed. The devops member acts through tool "
               "calls: pick a model that's good at them (see agent-team doctor).")
    return 0


def cmd_discuss(args) -> int:
    from .workflows import discuss
    members = [m.strip() for m in args.members.split(",")] if args.members else None
    team = _team(args)
    vision = discuss.adopt_vision(team, Path(args.vision)) if args.vision else ""
    return 0 if discuss.run(team, args.topic, members, args.turns, vision=vision) else 2


def cmd_build(args) -> int:
    from .workflows import build
    skip = tuple(s.strip() for s in args.skip.split(",") if s.strip())
    bad = set(skip) - set(build.OPTIONAL)
    if bad:
        raise SystemExit(f"--skip takes {', '.join(build.OPTIONAL)}; not {', '.join(sorted(bad))}")
    team = _team(args)
    print_estimate(team, "build")
    ok = build.run(team, args.task, args.rounds, args.lead, args.builder, args.branch, args.pr,
                   parallel=args.parallel, skip=skip)
    return 0 if ok else 2


def cmd_fix(args) -> int:
    from .workflows import fix
    return 0 if fix.run(_team(args), args.number, args.rounds, args.lead, args.builder) else 2


def cmd_autopilot(args) -> int:
    from . import schedule
    from .workflows import autopilot
    try:
        team = _team(args)
        print_estimate(team, "autopilot", args.max_cycles)
        return 0 if autopilot.run(team, args.milestone, args.max_cycles, args.rounds) else 2
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
    from . import budget, gates, jobs, logs, memory, readiness, schedule, usage
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
        "approval_requests": gates.requests(team.root),
        "attention": [{"name": c.name, "detail": c.detail, "fix": c.fix}
                      for c in readiness.check(team.root) if not c.ok and not c.optional],
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
    for r in data["approval_requests"]:
        ui.say(f"\n  PR #{r['number']} waits for your approval ({', '.join(r['paths'][:3])}): agent-team approve {r['number']}")
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


def print_estimate(team, workflow: str, cycles: int = 1) -> None:
    from . import estimate
    e = estimate.estimate(team, workflow, cycles)
    if e["typical"] is not None:
        ui.say(f"  Estimated cost: {e['note']}")
    if e["warning"]:
        ui.warn(e["warning"])


def cmd_estimate(args) -> int:
    import json as _json
    from . import estimate
    team = _team(args)
    e = estimate.estimate(team, args.workflow, args.cycles)
    if args.json:
        print(_json.dumps(e))
        return 0
    ui.say(e["note"])
    if e["warning"]:
        ui.warn(e["warning"])
    for m, cap in team.limits.milestones.items():
        from . import budget
        ui.say(f"  Milestone {m}: ${budget.milestone_spent(team, m):.2f} of ${cap:.2f} spent")
    return 0


def cmd_eval(args) -> int:
    from . import evals
    team = _team(args)
    names = [n.strip() for n in args.only.split(",") if n.strip()]
    known = {s[0] for s in evals.SCENARIOS}
    if set(names) - known:
        raise SystemExit(f"unknown scenarios {sorted(set(names) - known)}; known: {sorted(known)}")
    if not args.yes:
        ui.say(f"This runs {len(names) or len(known)} scenario(s) with your team's real models in a throwaway "
               "project (no GitHub). It costs real tokens: several builds' worth.")
        if not sys.stdin.isatty() or input("Run them? [y/N] ").strip().lower() != "y":
            ui.say("Not run. Add --yes to skip this question.")
            return 1
    report = evals.run(team, names or None, args.keep)
    ui.heading(f"Evals: {report['passed']}/{report['total']} passed · ${report['cost']:.2f} · lead {report['lead']}, "
               f"builders {', '.join(report['builders'])}")
    for r in report["results"]:
        mark = "\033[32m✓\033[0m" if r["passed"] else "\033[31m✕\033[0m"
        ui.say(f"  {mark} {r['scenario']:<13} {r['checks']}\n      {r['detail']} · {r['rounds']} round(s) · "
               f"{r['seconds']}s · ${r['cost']:.2f}")
    return 0 if report["passed"] == report["total"] else 2


def cmd_notify(args) -> int:
    from . import notify
    team = _team(args)
    if not team.notify.webhook_env:
        raise SystemExit('No [notify] section: add webhook_env = "AGENT_TEAM_WEBHOOK" to .team.toml and save the URL '
                         "with: agent-team keys set AGENT_TEAM_WEBHOOK")
    ok = notify.send(team, "pr_opened" if not team.notify.events else team.notify.events[0],
                     "Test notification from agent-team: notifications work.")
    ui.say("Sent." if ok else f"Not sent: check that {team.notify.webhook_env} holds the webhook URL (agent-team keys).")
    return 0 if ok else 1


def cmd_approve(args) -> int:
    from . import gates, github
    team = _team(args)
    if not team.project.repo:
        raise SystemExit("[project].repo is not set (and origin isn't on GitHub).")
    if args.number is None:
        reqs = gates.requests(team.root)
        if not reqs:
            ui.say("No pull request is waiting for your approval.")
        for r in reqs:
            ui.say(f"  #{r['number']:<5} {r['title']}  (commit {r['sha'][:10]}; changes {', '.join(r['paths'][:4])})")
        return 0
    info = github.gh_json("pr", "view", str(args.number), "-R", team.project.repo, "--json", "headRefOid,state,title")
    if info["state"] != "OPEN":
        raise SystemExit(f"PR #{args.number} is {info['state'].lower()}.")
    gates.approve(team.root, args.number, info["headRefOid"])
    ui.action(f"approved PR #{args.number} at {info['headRefOid'][:10]} ({info['title']}); the next shift may merge it")
    ui.say("A newer commit on that PR will need approving again.")
    return 0


def cmd_issues(args) -> int:
    from . import agent, files, issues
    team = _team(args)
    if not team.project.repo:
        raise SystemExit("[project].repo is not set (and origin isn't on GitHub).")
    if args.action == "sync":
        lead = agent.make(team, team.by_role("lead"), "lead", file_format=files.FILE_FORMAT, label_suffix=" · issues")
        proposed = issues.propose(team, lead, args.milestone)
        if not proposed:
            ui.say("Nothing to create: every open roadmap item already has an issue.")
            return 0
        ui.heading(f"{len(proposed)} issue(s) to create")
        for p in proposed:
            ui.say(f"  [{p['milestone']}] {p['title']}\n      {p['body'][:200]}")
        if not args.yes:
            ui.say("\nNothing created yet. Run again with --yes to create them on GitHub.")
            return 0
        for url in issues.create(team.project.repo, proposed):
            ui.action(f"created {url}")
        return 0
    found = issues.open_issues(team.project.repo, args.milestone)
    if not found:
        ui.say(f"No open {issues.LABEL} issues. Create them with: agent-team issues sync --milestone M2")
    for i in found:
        ui.say(f"  #{i['number']:<5} {i['title']}")
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
        added = memory.add(root, [args.text], "added by a person", memory.BY_PERSON)
        ui.say("Added." if added else "Already known (or too short).")
        return 0
    if args.action == "forget":
        try:
            ui.say(f"Forgot: {memory.forget(root, int(args.text))}")
        except ValueError as e:
            raise SystemExit(f"forget takes a lesson number from the list: {e}")
        return 0
    if args.action == "promote":
        from . import kit
        try:
            text = memory.promote(root, int(args.text))
        except ValueError as e:
            raise SystemExit(f"promote takes a lesson number from the list: {e}")
        path = root / ".team.toml"
        kit.save_team_file(root, kit.add_rule(path.read_text(encoding="utf-8"), memory.LEARNED_RULES))
        ui.say(f"Now a project rule ({memory.LEARNED_RULES}): {text}")
        return 0
    if args.action == "export":
        print(json.dumps(memory.export(root), indent=1))
        return 0
    if args.action == "import":
        source = Path(args.text) if args.text else None
        if not source or not source.is_file():
            raise SystemExit("import takes a file written by `agent-team memory export > lessons.json`")
        added = memory.import_(root, json.loads(source.read_text(encoding="utf-8")))
        ui.say(f"Imported {len(added)} new lessons.")
        return 0
    items = memory.lessons(root)
    if not items:
        ui.say("No lessons yet. Reviewers add them (LESSON: lines) when they block for a general reason.")
    for n, i in enumerate(items, 1):
        seen = f", seen {i['seen']}×" if i["seen"] > 1 else ""
        ui.say(f"  {n:>2}. [{i['confidence']:.2f}{seen}] {i['text']}" + (f"  ({i['source']})" if i["source"] else ""))
    ready = memory.promotable(root)
    if ready:
        ui.say(f"\nThe team keeps relearning {', '.join(map(str, ready))}: make one a project rule with "
               f"agent-team memory promote N")
    return 0


def cmd_projects(args) -> int:
    from . import projects
    if args.action == "forget":
        ui.say("Forgotten." if projects.forget(args.path or ".") else "That project wasn't remembered.")
        return 0
    rows = projects.all_summaries()
    if not rows:
        ui.say("No projects yet: they're remembered when you run agent-team in them.")
    for r in rows:
        if not r["ok"]:
            ui.say(f"  {r['name']:<20} {r['root']}  ({r['problem']})")
            continue
        last = r["last_run"]
        ui.say(f"  {r['name']:<20} {r['repo'] or '-':<28} today ${r['cost_today']:.2f}  total ${r['cost_total']:.2f}  "
               f"{'running ' + ', '.join(r['running']) if r['running'] else ''}"
               f"{'  waits for you: ' + '; '.join(r['waiting']) if r['waiting'] else ''}"
               f"\n      {r['root']}" + (f"  · last: {last['workflow']} ({last['outcome'] or '—'})" if last else ""))
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
    if args.ollama:   # Ollama servers: this machine, OLLAMA_HOST, a VM's or container's host, the gateway
        from .readiness import find_ollama
        servers = find_ollama(timeout=args.timeout)
        if args.json:
            print(_json.dumps([{"url": u, "models": m} for u, m in servers]))
            return 0
        if not servers:
            ui.say("No Ollama server answered on this machine, its host or the gateway. On another machine, "
                   "Ollama must listen on the network (OLLAMA_HOST=0.0.0.0) with port 11434 open.")
            return 1
        for u, m in servers:
            ui.say(f"  {u:<32} {len(m)} models: {', '.join(m)[:80]}")
        return 0
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


def build_parser() -> argparse.ArgumentParser:
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
    s.add_argument("--ollama-url", default="", help="Ollama on another machine, e.g. http://192.168.64.1:11434 "
                   "(with a team file already there, only its Ollama address is changed)")
    s.add_argument("--no-claude", action="store_true", help="every member on the Ollama server: no Anthropic key needed")
    s.add_argument("--models", choices=["mixed", "ollama", "claude"], default=None,
                   help="where the models run: mixed (Claude, with Ollama builders; the default), ollama or claude")
    s.add_argument("--members", default=None, metavar="LIST",
                   help="optional members to add: security, qa, docs, all or none (comma-separated)")
    s.add_argument("--builders", type=int, default=None, metavar="N", help="how many builders (1 to 4; default 1)")
    s.add_argument("--per-run", type=float, default=None, metavar="USD", help="spend limit per run")
    s.add_argument("--per-day", type=float, default=None, metavar="USD", help="spend limit per day")
    s.add_argument("--vision", default=None, metavar="TEXT|FILE",
                   help="what the product should be, saved as VISION.md (text, or a file holding it)")
    s.add_argument("-y", "--yes", action="store_true",
                   help="ask nothing: take the defaults for every choice the flags leave open")
    s.add_argument("--no-rea", action="store_true", help="don't set up behaviour checks with REA, even if it's installed")
    s.add_argument("--force", action="store_true", help="replace an existing .team.toml")
    add("doctor", cmd_doctor, "check this machine is ready and every member is reachable")
    s = add("ready", cmd_ready, "checklist: git, GitHub, keys, Ollama, models (exit 0 unless --strict)")
    s.add_argument("--ollama-url", default="", help="also check an Ollama server before there's a team")
    s.add_argument("--json", action="store_true")
    s.add_argument("--strict", action="store_true", help="exit 1 if anything is missing")
    add("agents", cmd_agents, "list the team")
    s = add("discuss", cmd_discuss, "members discuss and agree a roadmap (writes ROADMAP.md)")
    s.add_argument("topic", nargs="?", default="next milestones",
                   help='what to plan (default: "next milestones")')
    s.add_argument("--vision", default="", metavar="FILE",
                   help="the product vision to plan for (default: the project's VISION.md; "
                        "saved as VISION.md when the project has none)")
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
    s.add_argument("--skip", default="", help="comma-separated optional steps to leave out: qa,security,docs,journeys")
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
    s = add("eval", cmd_eval, "run scenarios with your real models in a throwaway project (costs tokens)")
    s.add_argument("--only", default="", help="comma-separated: feature,bug,edit,injection,fake-release")
    s.add_argument("--keep", action="store_true", help="keep the practice projects for inspection")
    s.add_argument("--yes", action="store_true", help="don't ask before spending")
    s = add("estimate", cmd_estimate, "estimate what a run will cost, from this project's past runs")
    s.add_argument("workflow", choices=["build", "fix", "ship", "discuss", "market", "setup", "autopilot"])
    s.add_argument("--cycles", type=int, default=3, help="for autopilot")
    s.add_argument("--json", action="store_true")
    add("notify", cmd_notify, "send a test notification to the [notify] webhook")
    s = add("approve", cmd_approve, "approve a PR's current commit for gated paths (no number: list what's waiting)")
    s.add_argument("number", nargs="?", type=int, default=None)
    s = add("issues", cmd_issues, "the team's to-do list on GitHub: list team:build issues, or sync them from the roadmap")
    s.add_argument("action", nargs="?", default="list", choices=["list", "sync"])
    s.add_argument("--milestone", default="", help="e.g. M2")
    s.add_argument("--yes", action="store_true", help="for sync: create the proposed issues")
    s = add("scoreboard", cmd_scoreboard, "how each member and model is doing: approvals, rounds, cost per merged PR")
    s.add_argument("--json", action="store_true")
    s = add("memory", cmd_memory, "what the team learned from its reviews: list, add, forget, promote, export, import")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add", "forget", "promote", "export", "import"])
    s.add_argument("text", nargs="?", default="", help="the lesson to add, a number to forget or promote, or a file to import")
    s = sub.add_parser("projects", help="every project you use agent-team in: spend, runs, what waits for you")
    s.add_argument("action", nargs="?", default="list", choices=["list", "forget"])
    s.add_argument("path", nargs="?", default="")
    s.set_defaults(fn=cmd_projects)
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
    s = sub.add_parser("discover", help="find agent-team nodes on the local network (--ollama: Ollama servers)")
    s.add_argument("--ollama", action="store_true",
                   help="find Ollama servers instead: this machine, OLLAMA_HOST, a VM's host, the gateway")
    s.add_argument("--timeout", type=float, default=2.0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_discover)
    s = add("rea", cmd_rea, "REA, the tool server behind behaviour checks: status, or setup (install and configure)")
    s.add_argument("action", nargs="?", default="status", choices=["status", "setup"])
    s.add_argument("--yes", action="store_true", help="for setup: install without asking")
    s = add("behaviour", cmd_behaviour, "behaviour checks: list the journeys, run them, or have the lead suggest them")
    s.add_argument("action", nargs="?", default="list", choices=["list", "run", "suggest"])
    s.add_argument("--base", default="", help="for run: the commit to compare against (default: HEAD)")
    s.add_argument("--target", default="", help="for run: a commit to check instead of the working tree")
    s.add_argument("--only", default="", help="for run: comma-separated journey names")
    s = add("templates", cmd_templates, "team templates: reviewers, skills and rules from the library for your language")
    s.add_argument("action", nargs="?", default="list", choices=["list", "show", "apply"])
    s.add_argument("name", nargs="?", default="", help="the template (default: the one that fits the project)")
    s.add_argument("--yes", action="store_true", help="for apply: don't ask first")
    s = add("library", cmd_library, "the built-in library: specialists, skills, playbooks and rules for the team")
    s.add_argument("action", nargs="?", default="status",
                   choices=["status", "agents", "skills", "playbooks", "rules", "show", "give", "hire", "add-rules",
                            "on", "off"])
    s.add_argument("args", nargs="*", help="a search, a name, or languages")
    s.add_argument("--to", default="", help="give: the member who gets it")
    s.add_argument("--name", default="", help="hire: the new member's name")
    s.add_argument("--role", default="", help="hire: its role (default: the specialist's own)")
    s.add_argument("--provider", default="", help="hire: its provider (default: the lead's)")
    s.add_argument("--model", default="", help="hire: its model (default: the lead's)")
    s.add_argument("--limit", type=int, default=0, help="lists: show at most this many")
    s.add_argument("--json", action="store_true", help="lists: as JSON")
    s.add_argument("--yes", action="store_true", help="don't ask first")
    s = add("playbook", cmd_playbook, "written procedures a member follows: code-review, plan-feature, fix-bug, ...")
    s.add_argument("action", nargs="?", default="list", choices=["list", "show", "run"])
    s.add_argument("args", nargs="*", help="the playbook, then what it's for")
    s.add_argument("--member", default="", help="run: who follows it (default: the lead)")
    s.add_argument("--report", action="store_true", help="run: report only, change no files")
    s.add_argument("--build", action="store_true", help="run: make it a build task (changes files)")
    s.add_argument("--branch", default="", help="run as a build: create this branch first")
    s.add_argument("--pr", action="store_true", help="run as a build: open a pull request when approved")
    s = add("audit", cmd_audit, "check the team's prompts, skills, tool servers, permissions and secrets")
    s.add_argument("--json", action="store_true")
    s = add("sessions", cmd_sessions, "what each build and fix did: task, outcome, files, cost")
    s.add_argument("action", nargs="?", default="list", choices=["list", "show"])
    s.add_argument("number", nargs="?", default="")
    s.add_argument("--limit", type=int, default=20)
    s = sub.add_parser("try", help="see the team build a feature in a sample project, in about a minute (no setup)")
    s.add_argument("--with", dest="with_", default="auto", choices=["auto", "claude", "ollama", "replay"],
                   help="the models: auto (Claude if your key is saved, else Ollama, else a replay)")
    s.add_argument("--keep", action="store_true", help="keep the sample project afterwards")
    s.add_argument("--folder", default="", help="put the sample here instead of a temporary folder")
    s.set_defaults(fn=cmd_try)
    s = add("mcp", cmd_mcp, "the team as an MCP server for any coding agent: serve, install it, or print its config")
    s.add_argument("action", nargs="?", default="serve", choices=["serve", "install", "config"])
    s.add_argument("--client", default="claude", choices=["claude", "codex", "cursor"], help="for install")
    s.add_argument("--scope", default="user", choices=["user", "project", "local"], help="for install with Claude Code")
    s.add_argument("--yes", action="store_true", help="for install: don't ask first")
    s = sub.add_parser("completion", help="Tab completion for bash and zsh: print the script, or install it")
    s.add_argument("action", nargs="?", default="install", choices=["install", "bash", "zsh"],
                   help="install (for your shell), or print the bash or zsh script")
    s.add_argument("--shell", default="", choices=["", "bash", "zsh"], help="for install: default, your $SHELL")
    s.add_argument("--yes", action="store_true", help="for install: add the line to ~/.zshrc without asking")
    s.set_defaults(fn=cmd_completion)
    return p


def cmd_rea(args) -> int:
    from . import rea
    root = Path(args.project).resolve()
    if args.action == "status":
        st = rea.status(root)
        if not st["command"]:
            ui.say(f"REA isn't installed. Install REA {rea.VERSION} for agent-team with: agent-team rea setup")
            return 1
        ui.say(f"REA {st['version'] or '?'} ({st['where']}): {st['command']} {' '.join(st['args'])}")
        ui.say(f"  tried with: {st['pinned']}" + ("" if st["version"] == st["pinned"] else "  (a different version works too, "
                                                  "but agent-team was tried with this one)"))
        ui.say(f"  registered with Claude Code: {'yes' if st['claude_code'] else 'no'}")
        ui.say(f"  this project: {'uses it ([mcp.rea])' if st['configured'] else 'not set up yet (agent-team rea setup)'}")
        ok, detail = rea.doctor(st["command"])
        ui.say(f"  rea doctor: {'ok' if ok else 'needs attention'}: {detail}")
        return 0 if ok else 1
    command, cargs, where = rea.find()
    if not command:
        command, cargs, where = rea.install(args.yes), ["--mcp"], "agent-team's copy"
    ui.action(f"REA: {command} ({where})")
    from .config import CONFIG_NAME
    if (root / CONFIG_NAME).exists():
        if rea.configure(root, command, cargs):
            ui.action(f"added [mcp.rea] and [behaviour] to {CONFIG_NAME}")
        else:
            ui.say(f"{CONFIG_NAME} already has [mcp.rea].")
        team = config.load(root)
        from . import mcp
        ok, detail = mcp.check(team, "rea")
        ui.say(f"  {'ok' if ok else 'FAILED'}: {detail}")
        if ok and not team.behaviour.scenarios:
            ui.say("Next: agent-team behaviour suggest   (the lead writes the first journeys from VISION.md)")
        return 0 if ok else 1
    ui.say(f"No {CONFIG_NAME} here: run agent-team init (it finds REA and sets it up).")
    return 0


def cmd_behaviour(args) -> int:
    from . import behaviour
    team = _team(args)
    if args.action == "list":
        if not team.behaviour.scenarios:
            ui.say("No journeys yet. agent-team behaviour suggest has the lead write them from VISION.md.")
            return 0
        for sc in team.behaviour.scenarios:
            ui.say(f"  {sc.name}  ({sc.kind}, in {sc.source})")
        return 0
    if args.action == "suggest":
        from .workflows import journeys
        if team.behaviour.server not in team.mcp:
            raise SystemExit("Set up REA first: agent-team rea setup")
        written = journeys.suggest(team)
        if written:
            ui.say(f"Review {written[0]}, then try them: agent-team behaviour run")
        return 0 if written else 1
    from . import github
    base = github.git(team.root, "rev-parse", args.base or "HEAD", check=False).strip()
    if not base:
        raise SystemExit("behaviour checks compare against a commit: this folder needs git and at least one commit")
    outcomes = behaviour.run(team, base, args.target or None, label="manual",
                             only=[n.strip() for n in args.only.split(",") if n.strip()] or None)
    if not outcomes:
        ui.say("Nothing to check: no journeys (agent-team behaviour suggest), or REA isn't set up (agent-team rea setup).")
        return 1
    ui.say(behaviour.report(outcomes, for_pr=True))
    return 2 if any(o.status == "failed" for o in outcomes) else 0


def cmd_mcp(args) -> int:
    if args.action == "serve":
        from . import mcp_server
        return mcp_server.serve(Path(args.project))
    from . import mcp_install
    if args.action == "config":
        ui.say(mcp_install.snippets())
        return 0
    return mcp_install.install(args.client, args.yes, args.scope)


def cmd_templates(args) -> int:
    from . import packs
    root = Path(args.project).resolve()
    fit = packs.detect(root)
    if args.action == "list":
        for p in packs.PACKS:
            ui.say(f"  {p.name:<11} {p.about}{'   <- fits this project' if p is fit else ''}")
        ui.say(f"\nApply one: agent-team templates apply {fit.name}   (copies the pieces into team/skills/ and team/rules/)")
        return 0
    name = args.name or fit.name
    if name not in packs.BY_NAME:
        raise SystemExit(f"no template {name!r}; there are {', '.join(packs.BY_NAME)}")
    pack = packs.BY_NAME[name]
    if args.action == "show":
        for role, ref in pack.pieces().items():
            ui.say(f"  {role:<10} {ref}")
        ui.say(f"  {'everyone':<10} rules: common, {', '.join(pack.rules) or '(none for the language)'}; the library on demand")
        return 0
    return packs.apply(_team(args), pack, args.yes)


def _confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        ui.say("Run again with --yes to do it.")
        return False
    return input(f"{question} [Y/n] ").strip().lower() in ("", "y", "yes")


def cmd_library(args) -> int:
    from . import kit
    words = args.args
    action = args.action
    if action == "status":
        counts = {k: len(kit.catalog(k)) for k in kit.KINDS}
        ui.say("The built-in library: " + ", ".join(f"{n} {k}" for k, n in counts.items()) +
               f" (rules for {len(kit.languages())} languages and common ones)")
        ui.say("  agent-team library skills testing     search; also agents, playbooks, rules\n"
               "  agent-team library give NAME --to M   a skill or a specialist's know-how for a member\n"
               "  agent-team library hire AGENT         a specialist as a new member\n"
               "  agent-team library add-rules [LANG]   standards every member follows\n"
               "  agent-team library on                 members read any skill when a task needs it")
        return 0
    if action in kit.KINDS:
        entries = kit.catalog(action)
        if action == "playbooks":
            from .workflows import playbook
            entries = playbook.catalog(Path(args.project).resolve())
        query = " ".join(words)
        if query:
            entries = kit.rank(entries, query)
        if args.json:
            print(json.dumps([{"name": e.name, "description": e.description, "path": e.ref, "chars": e.chars}
                              for e in entries], indent=1))
            return 0
        for e in entries[: args.limit or None]:
            ui.say(f"  {e.name:<26} {e.description[:110]}")
        ui.say(f"\n{len(entries)} {action}" + (f" matching {query!r}" if query else ""))
        return 0
    if action == "show":
        if len(words) != 2:
            raise SystemExit("show takes a kind and a name, e.g. agent-team library show skills api-design")
        print(kit.find(words[0], words[1]).text())
        return 0
    team = _team(args)
    root = team.root
    text = (root / config.CONFIG_NAME).read_text(encoding="utf-8")
    if action == "give":
        if len(words) != 1 or not args.to:
            raise SystemExit("give takes one skill or agent and --to MEMBER, e.g. "
                             "agent-team library give api-design --to Forge")
        name = words[0].split("/", 1)[-1].removesuffix(".md")
        kind = "skills" if (kit.HOME / "skills" / name).is_dir() else "agents"
        entry = kit.find(kind, name)
        member = team.get(args.to)
        ui.say(f"{member.name} gets {entry.name} ({entry.chars:,} characters, on every call): {entry.description[:120]}")
        if not _confirm("Give it?", args.yes):
            return 0
        kit.save_team_file(root, kit.add_skill(text, member.name, kit.copy(entry.ref, root)))
        ui.action(f"{member.name} has {entry.name}")
        return 0
    if action == "hire":
        if len(words) != 1:
            raise SystemExit("hire takes one specialist, e.g. agent-team library hire architect")
        entry = kit.find("agents", words[0])
        name = args.name or entry.name.replace("-", " ").title().replace(" ", "")
        if name in team.agents:
            raise SystemExit(f"there's already a member named {name!r}; choose another with --name")
        like = team.by_role("lead")
        provider, model = args.provider or like.provider, args.model or (like.model if not args.provider else "")
        role = args.role or entry.meta.get("role") or "reviewer"
        ui.say(f"New member {name} ({role}, {provider} {model}), the {entry.name}: {entry.description[:140]}")
        if role == "reviewer":
            ui.say("  As a reviewer it joins discussions and signs off the paths it owns (set owns in .team.toml).")
        if not _confirm("Add the member?", args.yes):
            return 0
        rel = kit.copy(entry.ref, root)
        kit.save_team_file(root, kit.add_member(text, name, role, provider, model, entry.description, rel))
        ui.action(f"{name} joined the team")
        return 0
    if action == "add-rules":
        langs = words
        if not langs:
            from . import packs
            langs = ["common", *packs.detect(root).rules]
        known = ["common", *kit.languages()]
        bad = [l for l in langs if l not in known]
        if bad:
            raise SystemExit(f"there are no rules for {', '.join(bad)}; there are {', '.join(known)}")
        refs = [e.ref for e in kit.catalog("rules") if e.ref.split("/")[1] in langs]
        size = sum((kit.HOME / r).stat().st_size for r in refs)
        ui.say(f"Rules for {', '.join(langs)}: {len(refs)} files, {size:,} characters that every member reads on every call.")
        if not _confirm("Add them to [project].rules?", args.yes):
            return 0
        for folder in sorted({str(Path(kit.copy(r, root)).parent) for r in refs}):
            text = kit.add_rule(text, folder)
        kit.save_team_file(root, text)
        ui.action(f"rules added: {', '.join(langs)} (in {kit.RULES_DIR}/)")
        return 0
    if action in ("on", "off"):
        change = kit.add_to_project if action == "on" else kit.remove_from_project
        kit.save_team_file(root, change(text, "library", "builtin"))
        ui.say(f"The library is {action}: " +
               ("members see the skills that match each task and read the ones they need."
                if action == "on" else "members get only the skills listed for them."))
        return 0
    raise SystemExit(f"unknown action {action!r}")


def cmd_playbook(args) -> int:
    from . import kit
    from .workflows import playbook
    root = Path(args.project).resolve()
    if args.action == "list":
        entries = playbook.catalog(root)
        query = " ".join(args.args)
        if query:
            entries = kit.rank(entries, query)
        for e in entries:
            ui.say(f"  {e.name:<22} {e.meta.get('mode', 'report'):<7} {e.description[:100]}")
        ui.say("\nreport: a member reports without changing files; build: a normal build. "
               "agent-team playbook run NAME \"what for\"")
        return 0
    if not args.args:
        raise SystemExit(f"{args.action} takes a playbook name, e.g. agent-team playbook run code-review \"src/export\"")
    if args.action == "show":
        print(playbook.find(args.args[0], root).text())
        return 0
    team = _team(args)
    mode = "build" if args.build else "report" if args.report else ""
    entry = playbook.find(args.args[0], team.root)
    if (mode or entry.meta.get("mode")) == "build":
        print_estimate(team, "build")
    ok = playbook.run(team, args.args[0], " ".join(args.args[1:]), args.member, mode,
                      **({"branch": args.branch, "open_pr": args.pr} if (mode or entry.meta.get("mode")) == "build" else {}))
    return 0 if ok else 2


def cmd_audit(args) -> int:
    from . import audit
    team = _team(args)
    result = audit.run(team)
    if args.json:
        print(json.dumps(result, indent=1))
        return 0 if result["grade"] in ("A", "B") else 1
    ui.heading(f"Audit: {result['score']}/100, grade {result['grade']} "
               f"({result['files_read']} instruction files read)")
    marks = {"critical": "✕", "high": "!", "medium": "·", "low": " "}
    for f in result["findings"]:
        ui.say(f"  {marks[f['severity']]} {f['severity']:<8} {f['where']}: {f['what']}")
        if f["fix"]:
            ui.say(f"             {f['fix']}")
    if not result["findings"]:
        ui.say("  Nothing found.")
    return 0 if result["grade"] in ("A", "B") else 1


def cmd_sessions(args) -> int:
    from . import sessions
    root = _team(args).root
    items = sessions.listing(root)
    if args.action == "show":
        try:
            print(items[int(args.number) - 1].read_text(encoding="utf-8"))
        except (ValueError, IndexError):
            raise SystemExit(f"show takes a number from the list (1 to {len(items)})")
        return 0
    if not items:
        ui.say("No sessions yet: build and fix write one when they finish.")
    for n, p in enumerate(items[: args.limit], 1):
        ui.say(f"  {n:>2}. {sessions.summary_line(p)}")
    return 0


def cmd_try(args) -> int:
    from .workflows import try_demo
    return try_demo.run(args.with_, args.keep, Path(args.folder) if args.folder else None)


def cmd_completion(args) -> int:
    from . import completion
    if args.action in ("bash", "zsh"):
        sys.stdout.write(completion.script(args.action))
        return 0
    return completion.install(args.shell, args.yes)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["__complete"]:   # called by the shell on Tab: print the candidates, one per line
        from . import completion
        return completion.main(build_parser(), argv[1:])
    p = build_parser()
    args = p.parse_args(argv)
    from . import keys
    keys.load_into_env()   # before anything reads a key: works the same from any shell, launchd or cron
    from .budget import SpendLimitError
    try:
        return args.fn(args)
    except SpendLimitError as e:
        ui.warn(f"Stopped: {e}. Raise or remove the limit in [limits] of .team.toml to continue.")
        try:
            from . import notify
            notify.send(_team(args), "spend_limit", f"A {args.cmd} run stopped: {e}.")
        except (SystemExit, Exception):
            pass
        return 3
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
