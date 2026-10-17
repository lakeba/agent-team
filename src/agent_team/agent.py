"""A team member at runtime: its config, its provider, and an append-only conversation."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from . import budget, providers, ui, usage
from .config import AgentConfig, Team


def role_prompt(team: Team, agent: AgentConfig, name: str | None = None) -> str:
    """The agent's prompt text: its own file if configured, else the packaged one for its role."""
    if agent.prompt and name is None:
        return (team.root / agent.prompt).read_text(encoding="utf-8")
    fname = f"{name or agent.role}.md"
    try:
        return resources.files("agent_team.prompts").joinpath(fname).read_text(encoding="utf-8")
    except FileNotFoundError:
        return resources.files("agent_team.prompts").joinpath("member.md").read_text(encoding="utf-8")


def team_roster(team: Team) -> str:
    lines = []
    for a in team.agents.values():
        where = team.providers[a.provider]
        place = f"remote node {where.url}" if where.kind == "agent-http" else f"{where.kind} model {a.model}"
        desc = f" {a.description}" if a.description else ""
        owns = f" Owns: {', '.join(a.owns)}." if a.owns else ""
        skills = f" Skills: {', '.join(_skill_names(team, a))}." if a.skills else ""
        lines.append(f"- {a.name} ({a.role}, {place}).{desc}{owns}{skills}")
    return "\n".join(lines)


class Agent:
    def __init__(self, team: Team, cfg: AgentConfig, system: str, label_suffix: str = ""):
        self.team, self.cfg, self.system = team, cfg, system
        pcfg = team.providers[cfg.provider]
        self.provider = providers.build(pcfg, team.secret(pcfg))
        self.label = ui.label(cfg.name, cfg.role + label_suffix, cfg.color)
        self.messages: list[dict] = []   # append-only, so provider-side reasoning stays valid

    @property
    def name(self) -> str:
        return self.cfg.name

    def turn(self, content) -> str:
        if not self.provider.supports_images and not isinstance(content, str):
            content = providers.base.to_text(content)
        if not self.messages and isinstance(content, str) and self.team.project.library:
            from . import library
            offer = library.index(self.team, content)
            if offer:
                content = f"{content}\n\n{offer}"
        text = self._ask(content)
        if self.team.project.library:
            from . import library
            for _ in range(library.MAX_ROUNDS):   # the member asked to read skills first
                wanted = library.requested(text)
                if not wanted:
                    break
                ui.action(f"{self.cfg.name} reads {', '.join(wanted)} from the library")
                text = self._ask(library.read(self.team, wanted))
        return text

    def _ask(self, content) -> str:
        budget.check(self.team)
        self.messages.append({"role": "user", "content": content})
        self._compact()
        reply = self.provider.complete(self.system, self.messages, model=self.cfg.model,
                                       effort=self.cfg.effort, label=self.label)
        self.messages.append({"role": "assistant", "content": reply.content})
        # A remote node reports the model it really ran, so its member is priced correctly.
        u = dict(reply.usage or {})
        kind, model = u.pop("kind", "") or self.provider.kind, u.pop("model", "") or self.cfg.model
        usage.record(self.team.root, self.cfg.name, kind, model, u)
        return reply.text

    def _compact(self) -> None:
        """Keep a long conversation under [project].history_limit: earlier messages of ours lose the
        copies of files they carried (the latest message always has the current ones)."""
        from . import files
        limit = self.team.project.history_limit
        size = lambda: sum(len(m["content"]) if isinstance(m["content"], str) else len(str(m["content"]))
                           for m in self.messages)
        if size() <= limit:
            return
        for m in self.messages[:-2]:
            if m["role"] == "user" and isinstance(m["content"], str) and "<file path=" in m["content"]:
                m["content"] = files.strip_files(m["content"])
                if size() <= limit:
                    break


def _skill_names(team: Team, cfg: AgentConfig) -> list[str]:
    from . import skills
    names = []
    for entry in cfg.skills:
        try:
            names.append(skills.load_one(team, entry).name)
        except Exception:
            names.append(entry)
    return names


def make(team: Team, cfg: AgentConfig, prompt_name: str | None = None, label_suffix: str = "",
         **fields) -> Agent:
    """Build an agent whose system prompt is its role prompt filled with team and project facts."""
    template = role_prompt(team, cfg, prompt_name)
    values = {
        "name": cfg.name, "role": cfg.role, "project": team.project.name, "repo": team.project.repo,
        "roster": team_roster(team), "owns": ", ".join(cfg.owns) or "nothing",
        "guarantees": "\n".join(f"- {g}" for g in team.project.guarantees) or "- (none listed)",
        "test_command": team.project.test_command or "(none configured)",
        **fields,
    }
    system = _fill(template, values)
    if team.project.rules:
        from . import rules
        system = f"{system.rstrip()}\n\n{rules.render(team)}"
    from . import memory
    learned = memory.for_prompt(team.root)
    if learned:
        system = f"{system.rstrip()}\n\n{learned}"
    if cfg.skills:
        from . import skills
        system = f"{system.rstrip()}\n\n{skills.render(skills.load(team, cfg))}"
    return Agent(team, cfg, system, label_suffix)


def _fill(template: str, values: dict) -> str:
    """str.format that leaves unknown {placeholders} and literal braces alone."""
    class Keep(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    try:
        return template.format_map(Keep(values))
    except (ValueError, IndexError):
        out = template
        for k, v in values.items():
            out = out.replace("{" + k + "}", str(v))
        return out


def prompt_path(team: Team, agent: AgentConfig) -> Path | None:
    return team.root / agent.prompt if agent.prompt else None
