"""Providers that talk plain HTTP: Ollama, OpenAI-compatible servers, and remote agent-team nodes.

All of them can point at another machine (`url = "http://gpu-box:11434"`), which is how
external machines join the team. Only the standard library is used.
"""
from __future__ import annotations

import json
import re
import time
import uuid
import urllib.error
import urllib.request

from .. import ui
from .base import Provider, ProviderError, Reply, ToolCall, register, text_messages


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


def _openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                              "parameters": t["input_schema"]}} for t in tools]


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_unparsed": raw}
    return value if isinstance(value, dict) else {"_unparsed": raw}


def _say_calls(text: str, calls: list[ToolCall]) -> None:
    if text.strip():
        ui.say(text)
    for c in calls:
        ui.say(f"  → {c.name}({json.dumps(c.arguments)[:140]})")


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
        parts, usage = [], {}
        with _post(f"{self.url}/api/chat", payload, {}) as r:
            for line in r:
                chunk = json.loads(line)
                if "error" in chunk:
                    raise ProviderError(f"Ollama: {chunk['error']}")
                piece = chunk.get("message", {}).get("content", "")
                parts.append(piece)
                ui.say(piece, end="")
                if chunk.get("done"):
                    usage = {"input": chunk.get("prompt_eval_count", 0), "output": chunk.get("eval_count", 0)}
        ui.say()
        text = "".join(parts)
        return Reply(text=text, content=text, usage=usage)

    supports_tools = True

    def complete_tools(self, system, messages, tools, *, model, effort, label):
        ui.say(f"\n--- {label} ({model}) is working...")
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                out.append({"role": "assistant", "content": m.get("content") or "",
                            "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                                           for c in m.get("tool_calls") or []]})
            elif m["role"] == "tool":
                out.append({"role": "tool", "content": m["content"], "tool_name": m.get("name", "")})
            else:
                out.append({"role": "user", "content": m["content"]})
        payload = {"model": model, "stream": False, "messages": out, "tools": _openai_tools(tools),
                   "options": {"num_ctx": int(self.cfg.options.get("num_ctx", 65536))}}
        with _post(f"{self.url}/api/chat", payload, {}) as r:
            data = json.load(r)
        if "error" in data:
            raise ProviderError(f"Ollama: {data['error']}")
        msg = data.get("message") or {}
        calls = [ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=c["function"]["name"],
                          arguments=_args(c["function"].get("arguments")))
                 for c in msg.get("tool_calls") or []]
        text = clean(msg.get("content") or "")
        if not calls and (found := calls_in_text(text, {t["name"] for t in tools})):
            calls, text = found, ""
        _say_calls(text, calls)
        return Reply(text=text, content=text, tool_calls=calls,
                     usage={"input": data.get("prompt_eval_count", 0), "output": data.get("eval_count", 0)})

    def check(self, model):
        try:
            names = [m["name"] for m in _get_json(f"{self.url}/api/tags")["models"]]
        except Exception as e:
            return f"FAILED: can't reach Ollama at {self.url} ({e})"
        if not model:   # nothing chosen yet: say what there is to choose from
            return f"ok (Ollama at {self.url}; pulled: {', '.join(names)[:200] or 'nothing yet'})"
        if model in names:
            return f"ok (Ollama at {self.url}, model {model} is pulled)"
        near = closest_model(model, names)
        if near:
            return f"FAILED: {model!r} is not pulled at {self.url}; did you mean {near!r}?"
        return f"FAILED: {model!r} is not pulled at {self.url} (run: ollama pull {model})"

    def check_member(self, model):
        status = self.check(model)
        if not model and status.startswith("ok"):   # Ollama answers "model is required"
            return f"FAILED: no model chosen; Ollama needs one{status[2:]}"
        return status


# Chat-template tokens some local servers leave in the reply (mlx_lm with Qwen ends it with <|im_end|>).
# Left in, they hide markers such as a last line "STATUS: AGREE".
TEMPLATE_TOKENS = re.compile(r"<\|(?:im_end|im_start|eot_id|end_of_text|endoftext|end|eom_id|start_header_id|end_header_id)\|>|</s>")


def clean(text: str) -> str:
    """A local model's reply without chat-template tokens."""
    return TEMPLATE_TOKENS.sub("", text).rstrip() if "<" in text else text


def calls_in_text(text: str, names: set[str]) -> list[ToolCall]:
    """Tool calls a local model wrote as text instead of through the API (Qwen2.5-Coder on mlx_lm:
    {"name": ..., "arguments": {...}}, bare, in a ```json fence, in <tool_call> tags or after a sentence,
    its arguments sometimes a JSON string). Taken only when every call names an offered tool, so a plain
    JSON answer stays an answer. The words before a call are dropped: the call is what the member did."""
    def read(piece: str) -> ToolCall | None:
        try:
            v = json.loads(piece)
        except ValueError:
            return None
        args = v.get("arguments", v.get("parameters")) if isinstance(v, dict) else None
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return None
        if not isinstance(v, dict) or v.get("name") not in names or (args is not None and not isinstance(args, dict)):
            return None
        return ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=v["name"], arguments=args or {})

    tagged = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.S)
    if tagged:
        calls = [read(t) for t in tagged]
        return calls if all(calls) else []
    fenced = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, re.S)
    if whole := read(fenced.group(1) if fenced else text.strip()):
        return [whole]
    at = text.rfind('{"name"')   # a sentence, then the call at the very end
    if at > 0 and (call := read(re.sub(r"\s*```\s*$", "", text[at:]).strip())):
        return [call]
    return []


def closest_model(model: str, served: list[str]) -> str:
    """The served model `model` most likely means: the same name without its organisation
    ("Qwen2.5-Coder-7B-Instruct-4bit" for "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"), ignoring case,
    or the same name with :latest. "" when nothing matches."""
    want = model.strip().lower()
    for m in served:
        if m.startswith("/"):
            continue
        name = m.lower()
        if want in (name.rsplit("/", 1)[-1], name.removesuffix(":latest"), f"{name}:latest") or \
                want.rsplit("/", 1)[-1] == name.rsplit("/", 1)[-1]:
            return m
    return ""


def _model(payload: dict, model: str) -> dict:
    """No model chosen: leave it out, so the server uses its default (mlx_lm its --model, LM Studio the
    loaded one). An empty "model" isn't that: mlx_lm tries to load a model named ''."""
    return {"model": model, **payload} if model else payload


@register("openai")
class OpenAICompatProvider(Provider):
    """Any server with an OpenAI-style /v1/chat/completions endpoint: vLLM, LM Studio,
    llama.cpp server, Ollama's /v1, hosted gateways..."""

    def _headers(self):
        return {"Authorization": f"Bearer {self.secret}"} if self.secret else {}

    def complete(self, system, messages, *, model, effort, label):
        ui.say(f"\n--- {label} ({model}) is writing...")
        payload = _model({"messages": [{"role": "system", "content": system}] + text_messages(messages)}, model)
        payload.update(self.cfg.options.get("extra_body", {}))
        with _post(f"{self.cfg.url.rstrip('/')}/v1/chat/completions", payload, self._headers()) as r:
            data = json.load(r)
        try:
            text = clean(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError) as e:
            raise ProviderError(f"unexpected response from {self.cfg.url}: {str(data)[:300]}") from e
        ui.say(text)
        u = data.get("usage") or {}
        return Reply(text=text, content=text,
                     usage={"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)})

    supports_tools = True

    def complete_tools(self, system, messages, tools, *, model, effort, label):
        ui.say(f"\n--- {label} ({model}) is working...")
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                item = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    item["tool_calls"] = [{"id": c["id"], "type": "function",
                                           "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                                          for c in m["tool_calls"]]
                out.append(item)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            else:
                out.append({"role": "user", "content": m["content"]})
        payload = _model({"messages": out, "tools": _openai_tools(tools)}, model)
        payload.update(self.cfg.options.get("extra_body", {}))
        with _post(f"{self.cfg.url.rstrip('/')}/v1/chat/completions", payload, self._headers()) as r:
            data = json.load(r)
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"unexpected response from {self.cfg.url}: {str(data)[:300]}") from e
        calls = [ToolCall(id=c.get("id") or f"call_{uuid.uuid4().hex[:12]}", name=c["function"]["name"],
                          arguments=_args(c["function"].get("arguments")))
                 for c in msg.get("tool_calls") or []]
        text = clean(msg.get("content") or "")
        if not calls and (found := calls_in_text(text, {t["name"] for t in tools})):
            calls, text = found, ""
        if not calls and not text.strip() and data["choices"][0].get("finish_reason") == "tool_calls":
            raise ProviderError(f"{model} tried to call a tool, but {self.cfg.url} couldn't read the call (mlx_lm logs "
                                f"'Failed to parse tool call'). The model may be too small for tool use: use a larger "
                                f"one, or set [project].review = \"snapshot\" so reviews don't need tools")
        _say_calls(text, calls)
        u = data.get("usage") or {}
        return Reply(text=text, content=text, tool_calls=calls,
                     usage={"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)})

    def check(self, model):
        try:
            data = _get_json(f"{self.cfg.url.rstrip('/')}/v1/models", self._headers())
            ids = [m.get("id") for m in data.get("data", [])]
        except Exception as e:
            return f"FAILED: can't reach {self.cfg.url} ({e})"
        if not model:   # nothing chosen yet: say what there is to choose from
            named = [i for i in ids if isinstance(i, str) and not i.startswith('/')]
            return f"ok ({self.cfg.url}; serves: {', '.join(named)[:200] or 'no models listed'})"
        if not ids or model in ids:
            return f"ok ({self.cfg.url})"
        near = closest_model(model, ids)
        hint = f"; did you mean {near!r}? (set the member's model to that)" if near else \
            f"; it serves: {', '.join(i for i in ids if not i.startswith('/'))[:200]}"
        return f"FAILED: {model!r} not served by {self.cfg.url}{hint}"

    def check_member(self, model):
        status = self.check(model)
        if not model and status.startswith("ok ("):
            return "ok (no model set, so the server's default; " + status[4:]
        return status


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
        return Reply(text=text, content=text, usage=data.get("usage"))

    supports_tools = True

    def complete_tools(self, system, messages, tools, *, model, effort, label):
        ui.say(f"\n--- {label} (remote: {self.cfg.url}) is working...")
        payload = {"system": system, "messages": messages, "tools": tools, "model": model, "effort": effort}
        with _post(f"{self.cfg.url.rstrip('/')}/v1/turn", payload, self._headers()) as r:
            data = json.load(r)
        calls = [ToolCall(id=c.get("id") or f"call_{uuid.uuid4().hex[:12]}", name=c["name"],
                          arguments=_args(c.get("arguments"))) for c in data.get("tool_calls") or []]
        text = data.get("text", "")
        _say_calls(text, calls)
        return Reply(text=text, content=text, usage=data.get("usage"), tool_calls=calls)

    def check(self, model):
        try:
            info = _get_json(f"{self.cfg.url.rstrip('/')}/v1/info", self._headers())
        except Exception as e:
            return f"FAILED: can't reach remote agent at {self.cfg.url} ({e})"
        return f"ok (remote node {info.get('node', '?')}, {info.get('provider', '?')}/{info.get('model', '?')})"
