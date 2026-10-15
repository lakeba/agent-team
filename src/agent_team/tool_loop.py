"""A tool-using conversation with any provider that supports tools, not only Claude.

The devops shift acts only through tools that enforce the team's rules. With Claude it runs on the
Anthropic SDK's tool runner; with any other member (Ollama, an OpenAI-compatible server, a remote
node) it runs here: ask the model, run the tools it calls, send back the results, repeat.
"""
from __future__ import annotations

import json
from typing import Callable

from . import budget, providers, ui, usage
from .config import AgentConfig, Team


def run(team: Team, cfg: AgentConfig, system: str, tools: list, first: str, max_steps: int = 30,
        on_text: Callable[[str], None] | None = None) -> str:
    """Run until the model answers without calling a tool, or `max_steps` model calls. `tools` are
    functions decorated with anthropic's `beta_tool` (they carry their own JSON schemas)."""
    pcfg = team.providers[cfg.provider]
    provider = providers.build(pcfg, team.secret(pcfg))
    if not provider.supports_tools:
        raise SystemExit(f"{cfg.name}'s provider ({pcfg.kind}) can't use tools.")
    schemas = [t.to_dict() for t in tools]
    by_name = {s["name"]: t for s, t in zip(schemas, tools)}
    label = ui.label(cfg.name, cfg.role, cfg.color)
    messages: list[dict] = [{"role": "user", "content": first}]
    text = ""
    for _ in range(max_steps):
        budget.check(team)
        reply = provider.complete_tools(system, messages, schemas, model=cfg.model, effort=cfg.effort, label=label)
        u = dict(reply.usage or {})
        usage.record(team.root, cfg.name, u.pop("kind", "") or provider.kind, u.pop("model", "") or cfg.model, u)
        text = reply.text or text
        if reply.text.strip() and on_text:
            on_text(reply.text)
        messages.append({"role": "assistant", "content": reply.text,
                         "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in reply.tool_calls]})
        if not reply.tool_calls:
            return reply.text
        for call in reply.tool_calls:
            messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                             "content": _call(by_name, call.name, call.arguments)})
    ui.warn(f"stopped after {max_steps} model calls")
    return text


def _call(by_name: dict, name: str, arguments: dict) -> str:
    tool = by_name.get(name)
    if tool is None:
        return f"error: there is no tool named {name!r}; the tools are {', '.join(by_name)}"
    if "_unparsed" in arguments:
        return f"error: the arguments were not valid JSON: {arguments['_unparsed'][:200]}"
    try:
        result = tool.call(arguments)
    except Exception as e:   # bad arguments or a failed action: tell the model, let it adjust
        return f"error: {type(e).__name__}: {e}"
    return result if isinstance(result, str) else json.dumps(result, default=str)
