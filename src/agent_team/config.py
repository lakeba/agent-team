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
KNOWN_ROLES = {"lead", "builder", "devops", "marketing", "factcheck", "reviewer", "security", "qa", "docs"}

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
    marketing: dict = field(default_factory=dict)


@dataclass
class LimitsConfig:
    per_run: float = 0.0            # US dollars; 0 means no limit
    per_day: float = 0.0            # US dollars, per UTC day, across every run in this project


@dataclass
class Team:
    root: Path
    project: ProjectConfig
    providers: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    pricing: dict = field(default_factory=dict)   # model -> {input, output, cache_read?, cache_write?}
    limits: LimitsConfig = field(default_factory=LimitsConfig)

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
    pricing = dict(data.get("pricing") or {})
    for model, table in pricing.items():
        bad = set(table) - {"input", "output", "cache_read", "cache_write"}
        if bad or not all(isinstance(v, (int, float)) for v in table.values()):
            raise ConfigError(f"[pricing.\"{model}\"]: use numeric input, output, cache_read, cache_write (USD per million tokens)")
    limits = _take(dict(data.get("limits") or {}), LimitsConfig, "[limits]")
    if not all(isinstance(v, (int, float)) and v >= 0 for v in (limits.per_run, limits.per_day)):
        raise ConfigError("[limits]: per_run and per_day are US dollars (0 or more; 0 means no limit)")
    return Team(root=root, project=project, providers=providers, agents=agents, pricing=pricing, limits=limits)
