"""Providers that talk plain HTTP: Ollama, OpenAI-compatible servers, and remote agent-team nodes.

All of them can point at another machine (`url = "http://gpu-box:11434"`), which is how
external machines join the team. Only the standard library is used.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .. import ui
from .base import Provider, ProviderError, Reply, register, text_messages


def _post(url: str, payload: dict, headers: dict, timeout: int = 3600, attempts: int = 24):
    """POST with a retry window for a server that is (re)starting. Returns the open response."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    for i in range(attempts):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:500]
            raise ProviderError(f"{url}: HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            if not isinstance(e.reason, (ConnectionRefusedError, TimeoutError)) or i == attempts - 1:
                raise ProviderError(f"can't reach {url}: {e.reason}") from e
            if i == 0:
                ui.warn(f"{url} isn't answering; retrying for up to {attempts * 5 // 60} minutes...")
            time.sleep(5)


def _get_json(url: str, headers: dict | None = None, timeout: int = 10):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


@register("ollama")
class OllamaProvider(Provider):
    """A model served by Ollama, on this machine or another one."""

    def __init__(self, cfg, secret=""):
        super().__init__(cfg, secret)
        self.url = (cfg.url or "http://localhost:11434").rstrip("/")

    def complete(self, system, messages, *, model, effort, label):
        ui.say(f"\n--- {label} ({model}) is writing...")
        payload = {"model": model, "stream": True,
                   "messages": [{"role": "system", "content": system}] + text_messages(messages),
                   "options": {"num_ctx": int(self.cfg.options.get("num_ctx", 65536))}}
        if "think" in self.cfg.options:
            payload["think"] = self.cfg.options["think"]
        parts = []
        with _post(f"{self.url}/api/chat", payload, {}) as r:
            for line in r:
                chunk = json.loads(line)
                if "error" in chunk:
                    raise ProviderError(f"Ollama: {chunk['error']}")
                piece = chunk.get("message", {}).get("content", "")
                parts.append(piece)
                ui.say(piece, end="")
        ui.say()
        text = "".join(parts)
        return Reply(text=text, content=text)

    def check(self, model):
        try:
            names = [m["name"] for m in _get_json(f"{self.url}/api/tags")["models"]]
        except Exception as e:
            return f"FAILED: can't reach Ollama at {self.url} ({e})"
        return (f"ok (Ollama at {self.url}, model {model} is pulled)" if model in names
                else f"FAILED: {model!r} is not pulled at {self.url} (run: ollama pull {model})")


@register("openai")
class OpenAICompatProvider(Provider):
    """Any server with an OpenAI-style /v1/chat/completions endpoint: vLLM, LM Studio,
    llama.cpp server, Ollama's /v1, hosted gateways..."""

    def _headers(self):
        return {"Authorization": f"Bearer {self.secret}"} if self.secret else {}

    def complete(self, system, messages, *, model, effort, label):
        ui.say(f"\n--- {label} ({model}) is writing...")
        payload = {"model": model, "messages": [{"role": "system", "content": system}] + text_messages(messages)}
        payload.update(self.cfg.options.get("extra_body", {}))
        with _post(f"{self.cfg.url.rstrip('/')}/v1/chat/completions", payload, self._headers()) as r:
            data = json.load(r)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise ProviderError(f"unexpected response from {self.cfg.url}: {str(data)[:300]}") from e
        ui.say(text)
        return Reply(text=text, content=text)

    def check(self, model):
        try:
            data = _get_json(f"{self.cfg.url.rstrip('/')}/v1/models", self._headers())
            ids = [m.get("id") for m in data.get("data", [])]
        except Exception as e:
            return f"FAILED: can't reach {self.cfg.url} ({e})"
        return f"ok ({self.cfg.url})" if not ids or model in ids else f"FAILED: {model!r} not served by {self.cfg.url}"


@register("agent-http")
class RemoteAgentProvider(Provider):
    """An agent served by `agent-team serve` on another machine (see docs/remote-agents.md).

    The remote node owns its model and credentials; this side only sends the conversation and
    a bearer token. The remote node is stateless: every call carries the whole conversation.
    """

    def _headers(self):
        if not self.secret:
            raise ProviderError(f"remote agent at {self.cfg.url} needs a token: set {self.cfg.api_key_env or 'api_key_env'}")
        return {"Authorization": f"Bearer {self.secret}"}

    def complete(self, system, messages, *, model, effort, label):
        ui.say(f"\n--- {label} (remote: {self.cfg.url}) is working...")
        payload = {"system": system, "messages": text_messages(messages), "model": model, "effort": effort}
        with _post(f"{self.cfg.url.rstrip('/')}/v1/turn", payload, self._headers()) as r:
            data = json.load(r)
        text = data.get("text", "")
        ui.say(text)
        return Reply(text=text, content=text)

    def check(self, model):
        try:
            info = _get_json(f"{self.cfg.url.rstrip('/')}/v1/info", self._headers())
        except Exception as e:
            return f"FAILED: can't reach remote agent at {self.cfg.url} ({e})"
        return f"ok (remote node {info.get('node', '?')}, {info.get('provider', '?')}/{info.get('model', '?')})"
