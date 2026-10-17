"""Team configuration, read from a project's `.team.toml`.

A team is a set of providers (how to reach a model) and agents (team members that use a
provider). Workflows look agents up by role, so adding a member is a config change only.
See examples/todo-py.team.toml for a complete file.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = ".team.toml"

# Roles the built-in workflows understand. Any other role is allowed: such agents can join
# discussions and sign off the paths they own, using their own prompt file.
KNOWN_ROLES = {"lead", "builder", "devops", "marketing", "factcheck", "reviewer", "security", "qa", "docs", "scout"}

# Tools that look inside other people's software (decompilers, disassemblers, debuggers, extractors).
# Members who write the project's code never get them, so nothing taken from third-party internals
# can reach a build; the scout may only observe from the outside.
REVERSE_TOOL = ("decompile", "disassemble", "function", "rizin", "cutter", "gdb", "lldb", "frida", "jeb", "jadx",
                "native", "extract", "recover", "reconstruct", "swift", "dart", "smali", "apk", "class", "method",
                "bytecode", "symbol", "xref", "patch", "annotate")
WRITES_CODE = ("builder", "qa", "docs")
SCOUT_TOOLS = {"capture_browser_scenario", "capture_web_screenshot", "inspect_web_page", "list_browser_targets",
               "compare_web_screenshots", "observe_web_session"}


def reverse_tool(name: str) -> bool:
    return any(word in name for word in REVERSE_TOOL)

# Filled by providers.register(); kinds are validated against it once providers are imported.
PROVIDER_KINDS: set[str] = set()


class ConfigError(ValueError):
    pass


@dataclass
class ProviderConfig:
    name: str
    kind: str                       # anthropic | ollama | openai | agent-http | any registered kind
    url: str = ""                   # base URL for ollama / openai / agent-http
    api_key_env: str = ""           # env var holding a key or token, never the value itself
    options: dict = field(default_factory=dict)


@dataclass
class AgentConfig:
    name: str
    role: str
    provider: str
    model: str = ""
    effort: str = "high"
    description: str = ""
    owns: list[str] = field(default_factory=list)   # path prefixes this agent must sign off
    prompt: str = ""                # optional path (relative to the project) to a custom prompt
    skills: list[str] = field(default_factory=list)   # Markdown files or skill folders added to the prompt
    escalate_to: str = ""           # a stronger member who takes over this member's work after failed rounds
    github_token_env: str = ""      # variable holding this member's own GitHub token (its bot account or app)
    mcp: list[str] = field(default_factory=list)   # [mcp] servers whose allowed tools this member may call
    color: str = ""


@dataclass
class ProjectConfig:
    name: str
    repo: str = ""                  # owner/name on GitHub
    test_command: str = ""
    test_count_pattern: str = r"Ran (\d+) tests?"   # regex with one group, matched in CI logs
    guarantees: list[str] = field(default_factory=list)
    context_skip: list[str] = field(default_factory=list)   # path prefixes hidden from prompts
    context_limit: int = 200_000    # max characters of project files sent in one prompt
    context: str = "auto"           # full | focused | auto (focused when the whole project is too big)
    release: str = "auto"           # auto: the devops shift releases on its own; ask: it proposes, you approve
    review: str = "tools"           # tools: reviewers read files and run tests themselves; snapshot: all files up front
    require_approval: list[str] = field(default_factory=list)   # paths whose changes need the owners' approval
    marketing: dict = field(default_factory=dict)


@dataclass
class LimitsConfig:
    per_run: float = 0.0            # US dollars; 0 means no limit
    per_day: float = 0.0            # US dollars, per UTC day, across every run in this project
    milestones: dict = field(default_factory=dict)   # milestone name -> US dollars autopilot may spend on it


@dataclass
class RoutingConfig:
    escalate_after: int = 1         # rejected rounds before a member's work goes to its escalate_to
    light_model: str = ""           # e.g. claude-haiku-5-5: used for sign-offs and fact-checks by Claude members


@dataclass
class NotifyConfig:
    webhook_env: str = ""           # the environment variable holding the webhook URL (never the URL itself)
    format: str = "slack"           # slack | json
    events: list[str] = field(default_factory=list)   # empty: every event


@dataclass
class SandboxConfig:
    mode: str = "off"               # off: tests run on this machine; container: in a throwaway container
    image: str = ""                 # default: chosen from the project's stack
    network: bool = False           # allow network inside the container (to download dependencies)
    engine: str = ""                # docker | podman; default: whichever is installed


@dataclass
class McpServerConfig:
    """A tool server the team can use over the Model Context Protocol (stdio)."""
    name: str
    command: str                    # the program that starts the server, e.g. "rea" or "npx"
    args: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)        # extra environment variables (plain values, never secrets)
    env_from: list[str] = field(default_factory=list)   # variables passed through from your environment or keys file
    tools: list[str] = field(default_factory=list)  # the only tools members are offered; the rest stay hidden
    timeout: int = 300              # seconds one tool call may take
    max_output: int = 20_000        # characters of one result a model sees


SCENARIO_KINDS = ("terminal", "browser", "electron", "api")
SCENARIOS_FILE = "team/behaviour.toml"   # scenarios the team writes and keeps, besides those in .team.toml


@dataclass
class BehaviourScenario:
    """A user journey (or an API surface) checked on the base version and on the team's work."""
    name: str
    kind: str = "terminal"          # terminal: a command line; browser: a web page; electron: a desktop app;
                                    # api: a library's public API
    prepare: str = ""               # run first in $PROJECT, not captured (e.g. a build), so the run itself is quick
    # terminal
    run: str = ""                   # shell commands; $PROJECT is the version under test; runs in an empty folder
    input: list[str] = field(default_factory=list)   # lines typed into the program, one after another
    input_delay: float = 2.0        # seconds before the first line is typed
    input_every: float = 1.0        # seconds between lines
    watch: list[str] = field(default_factory=lambda: ["."])   # files (in that folder) compared after the run
    # browser
    serve: str = ""                 # starts the app in $PROJECT (e.g. "npm run preview -- --port 5173"); stopped after
    url: str = ""                   # where the browser starts, e.g. http://127.0.0.1:5173/
    steps: list[str] = field(default_factory=list)   # e.g. 'fill textbox "Project" with "client-a"', 'click button "Start"'
    step_timeout: int = 15          # seconds one step waits (e.g. for its element) before it fails
    # electron (steps too: 'click css "#save"', 'wait 500')
    app: str = ""                   # the Electron app, relative to $PROJECT: its folder (package.json) or main script
    electron: str = ""              # the Electron executable; default: the project's node_modules/electron
    electron_args: list[str] = field(default_factory=list)   # e.g. ["--no-sandbox"] on Linux without the SUID helper
    # api
    assembly: str = ""              # .NET: the built assembly, relative to $PROJECT, e.g. "out/Tally.dll"
    package: str = ""               # JavaScript: the package folder, relative to $PROJECT (its entry modules' exports)
    timeout: int = 120              # seconds
    source: str = ".team.toml"      # where it was defined (set when loading)


@dataclass
class BehaviourConfig:
    server: str = "rea"             # the [mcp] server that captures the runs
    browser: str = ""               # Chrome or Chromium for browser scenarios; default: found on this machine
    scenarios: list[BehaviourScenario] = field(default_factory=list)


@dataclass
class ResearchConfig:
    # public pages the scout observes before a discussion: a URL, or {url, steps} where the steps
    # (browser steps in plain words, e.g. 'click button "Accept all"') run before the page is read
    sites: list = field(default_factory=list)
    max_chars: int = 6000           # page text per site the scout reads

    def pages(self) -> list[tuple[str, list[str]]]:
        """(url, steps) for each site."""
        return [(s, []) if isinstance(s, str) else (s["url"], list(s.get("steps") or [])) for s in self.sites]


@dataclass
class Team:
    root: Path
    project: ProjectConfig
    providers: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    pricing: dict = field(default_factory=dict)   # model -> {input, output, cache_read?, cache_write?}
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    mcp: dict[str, McpServerConfig] = field(default_factory=dict)
    behaviour: BehaviourConfig = field(default_factory=BehaviourConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)

    def by_role(self, role: str, required: bool = True) -> AgentConfig | None:
        found = [a for a in self.agents.values() if a.role == role]
        if not found and required:
            raise ConfigError(f"no agent with role {role!r} in {CONFIG_NAME}")
        return found[0] if found else None

    def all_by_role(self, role: str) -> list[AgentConfig]:
        return [a for a in self.agents.values() if a.role == role]

    def get(self, name: str) -> AgentConfig:
        try:
            return self.agents[name]
        except KeyError:
            raise ConfigError(f"no agent named {name!r}; known: {', '.join(self.agents)}") from None

    def owners_of(self, paths: list[str]) -> dict[str, list[str]]:
        """Agent name -> the given paths that agent owns (and so must sign off)."""
        out: dict[str, list[str]] = {}
        for agent in self.agents.values():
            hits = [p for p in paths if any(o == "*" or p == o or p.startswith(o) for o in agent.owns)]
            if hits:
                out[agent.name] = hits
        return out

    def secret(self, provider: ProviderConfig) -> str:
        return os.environ.get(provider.api_key_env, "") if provider.api_key_env else ""


def _take(table: dict, cls, where: str, **extra):
    allowed = set(cls.__dataclass_fields__)
    unknown = set(table) - allowed
    if unknown:
        raise ConfigError(f"{where}: unknown keys {sorted(unknown)}; allowed: {sorted(allowed)}")
    try:
        return cls(**table, **extra)
    except TypeError as e:
        raise ConfigError(f"{where}: {e}") from None


def scenario(table: dict, where: str, source: str = ".team.toml") -> BehaviourScenario:
    """One behaviour scenario, checked: what it needs depends on its kind."""
    table.pop("source", None)
    sc = _take(table, BehaviourScenario, where, source=source)
    label = f"{where} ({sc.name!r})" if isinstance(sc.name, str) and sc.name else where
    if not isinstance(sc.name, str) or not sc.name.strip():
        raise ConfigError(f"{where}: needs a name")
    if sc.kind not in SCENARIO_KINDS:
        raise ConfigError(f"{label}: kind is {', '.join(SCENARIO_KINDS)}, not {sc.kind!r}")
    texts = [sc.prepare, sc.run, sc.serve, sc.url, sc.assembly, sc.package, sc.app, sc.electron]
    lists = [sc.input, sc.watch, sc.steps, sc.electron_args]
    if not all(isinstance(x, str) for x in texts) or not all(isinstance(l, list) and all(isinstance(x, str) for x in l)
                                                             for l in lists):
        raise ConfigError(f"{label}: run, prepare, serve, url, assembly, package, app and electron are text; input, "
                          f"watch, steps and electron_args are lists of text")
    if not isinstance(sc.timeout, int) or sc.timeout < 1:
        raise ConfigError(f"{label}: timeout is seconds (1 or more)")
    if not isinstance(sc.step_timeout, int) or sc.step_timeout < 1:
        raise ConfigError(f"{label}: step_timeout is seconds (1 or more)")
    if not all(isinstance(x, (int, float)) and x >= 0 for x in (sc.input_delay, sc.input_every)):
        raise ConfigError(f"{label}: input_delay and input_every are seconds")
    if any(w.startswith("/") or ".." in w.split("/") for w in sc.watch):
        raise ConfigError(f"{label}: watch paths are inside the run's folder (relative)")
    if sc.kind == "terminal" and not sc.run.strip():
        raise ConfigError(f"{label}: a terminal scenario needs run (the commands)")
    if sc.kind == "browser":
        if not sc.url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
            raise ConfigError(f"{label}: url is the app on this machine, e.g. http://127.0.0.1:5173/ (behaviour checks "
                              f"don't visit other sites)")
        from .steps import StepError, parse_steps
        try:
            parse_steps(sc.steps)
        except StepError as e:
            raise ConfigError(f"{label}: {e}") from None
    if sc.kind == "electron":
        if sc.app.startswith("/") or ".." in sc.app.split("/"):
            raise ConfigError(f"{label}: app is the Electron app inside the project (relative), e.g. \".\" or \"main.js\"")
        from .steps import StepError, parse_electron_steps
        try:
            parse_electron_steps(sc.steps)
        except StepError as e:
            raise ConfigError(f"{label}: {e}") from None
    if sc.kind == "api":
        target = sc.assembly or sc.package
        if bool(sc.assembly) == bool(sc.package) or target.startswith("/") or ".." in target.split("/"):
            raise ConfigError(f"{label}: an api scenario names either assembly (a built .NET .dll, e.g. \"out/App.dll\") "
                              f"or package (a JavaScript package folder, e.g. \".\"), relative to the project")
    return sc


def _check_sites(sites) -> None:
    """[research].sites: web addresses, or tables with url and the steps to take before reading."""
    if not isinstance(sites, list):
        raise ConfigError("[research].sites is a list of web addresses (https://...)")
    from .steps import StepError, parse_steps
    for i, site in enumerate(sites):
        where = f"[research].sites #{i + 1}"
        if isinstance(site, dict):
            unknown = set(site) - {"url", "steps"}
            if unknown:
                raise ConfigError(f"{where}: unknown keys {sorted(unknown)}; a site is {{ url = \"https://...\", "
                                  f"steps = [...] }}")
            url, steps = site.get("url"), site.get("steps", [])
            if not isinstance(steps, list) or not all(isinstance(x, str) for x in steps):
                raise ConfigError(f"{where}: steps are a list of text, e.g. ['click button \"Accept all\"']")
            try:
                parse_steps(steps)
            except StepError as e:
                raise ConfigError(f"{where}: {e}") from None
        else:
            url = site
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            raise ConfigError(f"{where}: sites are web addresses (https://...), or {{ url = \"https://...\", "
                              f"steps = [...] }}")


def scenarios_file(root: Path) -> list[BehaviourScenario]:
    """The scenarios in team/behaviour.toml: the ones the team writes and keeps up to date."""
    path = Path(root) / SCENARIOS_FILE
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{SCENARIOS_FILE}: {e}") from None
    unknown = set(data) - {"scenarios"}
    if unknown:
        raise ConfigError(f"{SCENARIOS_FILE}: only [[scenarios]] tables go here; found {sorted(unknown)}")
    return [scenario(dict(t), f"{SCENARIOS_FILE} [[scenarios]] #{i + 1}", SCENARIOS_FILE)
            for i, t in enumerate(data.get("scenarios") or [])]


def find_config(start: Path) -> Path:
    for folder in [start, *start.parents]:
        if (folder / CONFIG_NAME).exists():
            return folder / CONFIG_NAME
    raise ConfigError(f"no {CONFIG_NAME} found in {start} or its parents; run `agent-team init`")


def load(path: str | Path) -> Team:
    path = Path(path)
    if path.is_dir():
        path = find_config(path)
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from None
    team = parse(data, path.parent)
    if not team.project.repo:
        # Not set yet (the repo was created after init): use origin when it's on GitHub.
        from .workflows.init import github_repo
        team.project.repo = github_repo(team.root)
    return team


def parse(data: dict, root: Path) -> Team:
    from . import providers  # noqa: F401  (registers the built-in provider kinds for validation)
    if "project" not in data:
        raise ConfigError("missing [project] table")
    project = _take(dict(data["project"]), ProjectConfig, "[project]")
    if project.review not in ("tools", "snapshot"):
        raise ConfigError(f"[project].review: use tools or snapshot, not {project.review!r}")
    if project.release not in ("auto", "ask"):
        raise ConfigError(f"[project].release: use auto or ask, not {project.release!r}")
    if project.context not in ("full", "focused", "auto"):
        raise ConfigError(f"[project].context: use full, focused or auto, not {project.context!r}")

    providers = {}
    for name, table in (data.get("providers") or {}).items():
        p = _take(dict(table), ProviderConfig, f"[providers.{name}]", name=name)
        if PROVIDER_KINDS and p.kind not in PROVIDER_KINDS:
            raise ConfigError(f"[providers.{name}]: unknown kind {p.kind!r}; known: {sorted(PROVIDER_KINDS)}")
        if p.kind in {"openai", "agent-http"} and not p.url:
            raise ConfigError(f"[providers.{name}]: kind {p.kind!r} needs a url")
        providers[name] = p

    agents = {}
    for i, table in enumerate(data.get("agents") or []):
        a = _take(dict(table), AgentConfig, f"[[agents]] #{i + 1}")
        if a.name in agents:
            raise ConfigError(f"duplicate agent name {a.name!r}")
        if a.provider not in providers:
            raise ConfigError(f"agent {a.name!r} uses unknown provider {a.provider!r}")
        if not isinstance(a.skills, list) or not all(isinstance(s, str) and s.strip() for s in a.skills):
            raise ConfigError(f"agent {a.name!r}: skills is a list of file or folder paths")
        agents[a.name] = a
    if not agents:
        raise ConfigError("no [[agents]] defined")
    for a in agents.values():
        if a.escalate_to and a.escalate_to not in agents:
            raise ConfigError(f"agent {a.name!r}: escalate_to names {a.escalate_to!r}, who isn't on the team")
        if a.escalate_to == a.name:
            raise ConfigError(f"agent {a.name!r} can't escalate to itself")
    pricing = dict(data.get("pricing") or {})
    for model, table in pricing.items():
        bad = set(table) - {"input", "output", "cache_read", "cache_write"}
        if bad or not all(isinstance(v, (int, float)) for v in table.values()):
            raise ConfigError(f"[pricing.\"{model}\"]: use numeric input, output, cache_read, cache_write (USD per million tokens)")
    limits = _take(dict(data.get("limits") or {}), LimitsConfig, "[limits]")
    if not isinstance(limits.milestones, dict) or not all(
            isinstance(v, (int, float)) and v >= 0 for v in limits.milestones.values()):
        raise ConfigError("[limits.milestones]: milestone = US dollars, e.g. M2 = 10.0")
    if not all(isinstance(v, (int, float)) and v >= 0 for v in (limits.per_run, limits.per_day)):
        raise ConfigError("[limits]: per_run and per_day are US dollars (0 or more; 0 means no limit)")
    routing = _take(dict(data.get("routing") or {}), RoutingConfig, "[routing]")
    if not isinstance(routing.escalate_after, int) or routing.escalate_after < 1:
        raise ConfigError("[routing].escalate_after: a whole number of rejected rounds, 1 or more")
    notify = _take(dict(data.get("notify") or {}), NotifyConfig, "[notify]")
    if notify.format not in ("slack", "json"):
        raise ConfigError(f"[notify].format: use slack or json, not {notify.format!r}")
    from .notify import EVENTS
    unknown = sorted(set(notify.events) - set(EVENTS))
    if unknown:
        raise ConfigError(f"[notify].events: unknown {unknown}; known: {sorted(EVENTS)}")
    if notify.webhook_env.startswith(("http://", "https://")):
        raise ConfigError("[notify].webhook_env names the variable holding the URL; keep the URL itself out of .team.toml")
    sandbox = _take(dict(data.get("sandbox") or {}), SandboxConfig, "[sandbox]")
    if sandbox.mode not in ("off", "container"):
        raise ConfigError(f"[sandbox].mode: use off or container, not {sandbox.mode!r}")
    if sandbox.engine not in ("", "docker", "podman"):
        raise ConfigError(f"[sandbox].engine: use docker or podman, not {sandbox.engine!r}")
    mcp = {}
    for name, table in (data.get("mcp") or {}).items():
        s = _take(dict(table), McpServerConfig, f"[mcp.{name}]", name=name)
        if not isinstance(s.command, str) or not s.command.strip():
            raise ConfigError(f"[mcp.{name}]: command is the program that starts the server, e.g. \"rea\"")
        if not all(isinstance(x, str) for x in [*s.args, *s.tools, *s.env_from]):
            raise ConfigError(f"[mcp.{name}]: args, tools and env_from are lists of strings")
        if not isinstance(s.env, dict) or not all(isinstance(v, str) for v in s.env.values()):
            raise ConfigError(f"[mcp.{name}].env: names and plain string values (put secrets in env_from)")
        if not isinstance(s.timeout, int) or s.timeout < 1 or not isinstance(s.max_output, int) or s.max_output < 500:
            raise ConfigError(f"[mcp.{name}]: timeout is seconds (1 or more); max_output is characters (500 or more)")
        mcp[name] = s
    for a in agents.values():
        unknown = [m for m in a.mcp if m not in mcp]
        if unknown:
            raise ConfigError(f"agent {a.name!r}: mcp names {unknown}, which aren't [mcp] servers in {CONFIG_NAME}")
        empty = [m for m in a.mcp if not mcp[m].tools]
        if empty:
            raise ConfigError(f"agent {a.name!r} uses [mcp.{empty[0]}], which allows no tools yet: list the ones "
                              f"members may call in its tools")
    for a in agents.values():   # guardrails on what members may be given
        tools = [t for m in a.mcp for t in mcp[m].tools]
        if a.role in WRITES_CODE and any(reverse_tool(t) for t in tools):
            bad = next(t for t in tools if reverse_tool(t))
            raise ConfigError(f"agent {a.name!r} ({a.role}) writes the project's code, so it can't be given {bad!r}: "
                              f"tools that look inside other software never reach the members who build")
        if a.role == "scout" and any(t not in SCOUT_TOOLS for t in tools):
            bad = next(t for t in tools if t not in SCOUT_TOOLS)
            raise ConfigError(f"agent {a.name!r} is a scout: it observes from the outside, so {bad!r} isn't allowed "
                              f"(only {', '.join(sorted(SCOUT_TOOLS))})")
    research = _take(dict(data.get("research") or {}), ResearchConfig, "[research]")
    _check_sites(research.sites)
    btable = dict(data.get("behaviour") or {})
    scenarios = [scenario(dict(t), f"[[behaviour.scenarios]] #{i + 1}") for i, t in enumerate(btable.pop("scenarios", None) or [])]
    scenarios += scenarios_file(root)
    names = [s.name for s in scenarios]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ConfigError(f"behaviour scenarios share the name {dupes[0]!r} (in .team.toml and {SCENARIOS_FILE})")
    behaviour = _take(btable, BehaviourConfig, "[behaviour]", scenarios=scenarios)
    if scenarios and behaviour.server not in mcp:
        raise ConfigError(f"[behaviour].server is {behaviour.server!r}, but there's no [mcp.{behaviour.server}] to "
                          f"capture the runs with")
    return Team(root=root, project=project, providers=providers, agents=agents, pricing=pricing, limits=limits,
                routing=routing, notify=notify, sandbox=sandbox, mcp=mcp, behaviour=behaviour, research=research)
