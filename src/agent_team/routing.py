"""Picking the model by difficulty.

  * escalate_to: a member whose work the lead rejects `[routing].escalate_after` times hands it to
    a stronger member (Forge on a local model -> a Claude builder), who carries on from the files
    as they are and the lead's review.
  * light_model: routine checks (owners' sign-offs, fact-checks) by members on Claude use this
    cheaper model instead of their own.
"""
from __future__ import annotations

from dataclasses import replace

from .config import AgentConfig, Team


def light(team: Team, cfg: AgentConfig) -> AgentConfig:
    """The member as it should run a routine check: on the light model if one is set and it fits."""
    model = team.routing.light_model
    if model and team.providers[cfg.provider].kind == "anthropic" and model.startswith("claude-"):
        return replace(cfg, model=model)
    return cfg


def escalation(team: Team, cfg: AgentConfig, rejected: int) -> AgentConfig | None:
    """Who takes over after `rejected` rejected rounds, if anyone (one step per call)."""
    if cfg.escalate_to and rejected >= team.routing.escalate_after:
        return team.get(cfg.escalate_to)
    return None
