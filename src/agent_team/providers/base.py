"""The provider interface: one way to get a reply from one kind of model endpoint.

To add a new kind of endpoint, subclass Provider, implement `complete`, and decorate the class
with `@register("your-kind")`. See docs/extending.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import config
from ..config import ProviderConfig

_REGISTRY: dict[str, type["Provider"]] = {}


def register(kind: str):
    def wrap(cls):
        _REGISTRY[kind] = cls
        config.PROVIDER_KINDS.add(kind)
        cls.kind = kind
        return cls
    return wrap


def build(cfg: ProviderConfig, secret: str = "") -> "Provider":
    try:
        cls = _REGISTRY[cfg.kind]
    except KeyError:
        raise ValueError(f"unknown provider kind {cfg.kind!r}; known: {sorted(_REGISTRY)}") from None
    return cls(cfg, secret)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Reply:
    text: str
    content: Any        # what to append to the conversation as the assistant turn
    usage: dict | None = None   # tokens reported by the provider: input, output, cache_read, cache_write
    tool_calls: list[ToolCall] = field(default_factory=list)


class ProviderError(RuntimeError):
    pass


class Provider:
    kind = "base"
    supports_images = False

    def __init__(self, cfg: ProviderConfig, secret: str = ""):
        self.cfg, self.secret = cfg, secret

    def complete(self, system: str, messages: list[dict], *, model: str, effort: str,
                 label: str) -> Reply:
        raise NotImplementedError

    supports_tools = False

    def complete_tools(self, system: str, messages: list[dict], tools: list[dict], *, model: str,
                       effort: str, label: str) -> Reply:
        """One step of a tool-using conversation, for members that act through tools (devops).

        `tools` are {"name", "description", "input_schema"}. `messages` use one neutral shape:
        {"role": "user", "content"}, {"role": "assistant", "content", "tool_calls": [{"id", "name",
        "arguments"}]} and {"role": "tool", "tool_call_id", "name", "content"}.
        """
        raise ProviderError(f"{self.kind} providers can't use tools")

    def check(self, model: str) -> str:
        """Cheap reachability check for `agent-team doctor`. Returns a short status line."""
        return "no check implemented"


def to_text(content: Any) -> str:
    """Flatten Anthropic-style content blocks to plain text for text-only providers."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", "")
        if kind == "text":
            parts.append(block["text"] if isinstance(block, dict) else block.text)
        elif kind == "image":
            parts.append("[image omitted: this model cannot see images]")
    return "\n".join(parts)


def text_messages(messages: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": to_text(m["content"])} for m in messages]
