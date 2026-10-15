"""A team member at runtime: its config, its provider, and an append-only conversation."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from . import providers, ui, usage
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
        lines.append(f"- {a.name} ({a.role}, {place}).{desc}{owns}")
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
        self.messages.append({"role": "user", "content": content})
        reply = self.provider.complete(self.system, self.messages, model=self.cfg.model,
                                       effort=self.cfg.effort, label=self.label)
        self.messages.append({"role": "assistant", "content": reply.content})
        usage.record(self.team.root, self.cfg.name, self.provider.kind, self.cfg.model, reply.usage)
        return reply.text


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
    return Agent(team, cfg, _fill(template, values), label_suffix)


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
