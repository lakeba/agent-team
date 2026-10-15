"""Claude models through the Anthropic API.

Streams replies, shows a summary of the model's reasoning as dimmed text, retries dropped
connections, and cancels and retries a reply that produces nothing for `stall_seconds`.
"""
from __future__ import annotations

import os
import threading
import time

import anthropic
import httpx2

from .. import ui
from .base import Provider, ProviderError, Reply, register

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


class Stalled(Exception):
    pass


def usage_of(message) -> dict:
    u = getattr(message, "usage", None)
    if u is None:
        return {}
    return {"input": getattr(u, "input_tokens", 0) or 0, "output": getattr(u, "output_tokens", 0) or 0,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}


@register("anthropic")
class AnthropicProvider(Provider):
    supports_images = True

    def __init__(self, cfg, secret=""):
        super().__init__(cfg, secret)
        # With no explicit key the SDK resolves credentials itself (ANTHROPIC_API_KEY, profiles...).
        self.client = anthropic.Anthropic(api_key=secret) if secret else anthropic.Anthropic()
        self.stall_seconds = int(cfg.options.get("stall_seconds", os.environ.get("AGENT_TEAM_STALL_SECONDS", 480)))
        self.attempts = int(cfg.options.get("attempts", 4))

    def complete(self, system, messages, *, model, effort, label):
        for attempt in range(1, self.attempts + 1):
            ui.say(f"\n--- {label} ({model}) is thinking...")
            try:
                response = self._stream(system, messages, model, effort)
                break
            except (anthropic.APIConnectionError, anthropic.InternalServerError,
                    httpx2.TransportError, Stalled) as e:
                if attempt == self.attempts:
                    raise ProviderError(f"{model}: {type(e).__name__}: {e}") from e
                ui.warn(f"connection problem ({type(e).__name__}: {e}); retrying in {10 * attempt}s")
                time.sleep(10 * attempt)
        ui.say()
        if response.stop_reason == "refusal":
            raise ProviderError(f"{model} declined: {response.stop_details}")
        text = "".join(b.text for b in response.content if b.type == "text")
        return Reply(text=text, content=response.content, usage=usage_of(response))

    def _stream(self, system, messages, model, effort):
        extra = {}
        if model.startswith(_FALLBACK_MODELS):
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        with self.client.beta.messages.stream(
            model=model, max_tokens=64000, system=system, messages=messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort}, cache_control={"type": "ephemeral"}, **extra,
        ) as stream:
            last, done, stalled = [time.monotonic()], threading.Event(), threading.Event()

            def watchdog():
                while not done.wait(5):
                    if time.monotonic() - last[0] > self.stall_seconds:
                        stalled.set()
                        stream.close()
                        return

            threading.Thread(target=watchdog, daemon=True).start()
            thinking = False
            try:
                for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    last[0] = time.monotonic()
                    if event.delta.type == "thinking_delta":
                        if not thinking:
                            ui.say(ui.DIM + "\n  thinking: ", end="")
                            thinking = True
                        ui.say(event.delta.thinking.replace("\n", "\n  "), end="")
                    elif event.delta.type == "text_delta":
                        if thinking:
                            ui.say(ui.RESET + "\n")
                            thinking = False
                        ui.say(event.delta.text, end="")
                return stream.get_final_message()
            except Exception as e:
                if stalled.is_set():
                    raise Stalled(f"no output for {self.stall_seconds} seconds") from e
                raise
            finally:
                done.set()
                ui.say(ui.RESET, end="")

    def check(self, model):
        try:
            return f"ok ({self.client.models.retrieve(model).id})"
        except TypeError as e:   # the SDK found no credentials at all
            if "authentication" in str(e).lower():
                return "FAILED: no Anthropic credentials in this environment (set ANTHROPIC_API_KEY or api_key_env)"
            return f"FAILED: TypeError: {e}"
        except anthropic.AuthenticationError:
            return "FAILED: no valid API key (set ANTHROPIC_API_KEY or api_key_env)"
        except anthropic.NotFoundError:
            return f"FAILED: model {model!r} not found"
        except Exception as e:  # doctor should report, never crash
            return f"FAILED: {type(e).__name__}: {e}"
