"""`agent-team serve`: run a team member on this machine and let a team elsewhere call it.

The node is stateless. Each POST /v1/turn carries the system prompt and the whole conversation,
and the node answers with its model's reply. The model, its credentials and any GPU stay on
this machine; the caller only needs the URL and the bearer token.

    AGENT_TEAM_TOKEN=... agent-team serve --provider ollama --model qwen3.8:27b-mlx --port 8765

Endpoints:
    GET  /v1/info   -> {"node", "provider", "model", "version"}
    POST /v1/turn   {"system", "messages": [{"role", "content"}], "effort"?, "tools"?}
                    -> {"text", "tool_calls", "usage"}   (with tools, messages may include tool results)
"""
from __future__ import annotations

import hmac
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, providers, ui
from .config import ProviderConfig

MAX_BODY = 8 * 1024 * 1024


def make_handler(provider, model: str, token: str, node: str):
    lock = threading.Lock()   # one model call at a time on this node

    class Handler(BaseHTTPRequestHandler):
        server_version = f"agent-team/{__version__}"

        def _send(self, code: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            got = self.headers.get("Authorization", "")
            ok = hmac.compare_digest(got.encode(), f"Bearer {token}".encode())
            if not ok:
                self._send(401, {"error": "missing or wrong bearer token"})
            return ok

        def do_GET(self):
            if self.path != "/v1/info":
                return self._send(404, {"error": "not found"})
            if self._authorized():
                self._send(200, {"node": node, "provider": provider.kind, "model": model, "version": __version__})

        def do_POST(self):
            if self.path != "/v1/turn":
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY:
                return self._send(413, {"error": f"body must be 1..{MAX_BODY} bytes"})
            try:
                req = json.loads(self.rfile.read(length))
                system, messages = str(req["system"]), list(req["messages"])
                tools = req.get("tools")
                roles = ("user", "assistant", "tool") if tools else ("user", "assistant")
                if not messages or any(m.get("role") not in roles for m in messages):
                    raise ValueError("messages must be " + "/".join(roles) + " turns")
                if tools is not None and (not isinstance(tools, list) or not all(isinstance(t, dict) and "name" in t for t in tools)):
                    raise ValueError("tools must be a list of {name, description, input_schema}")
            except (ValueError, KeyError, TypeError) as e:
                return self._send(400, {"error": f"bad request: {e}"})
            with lock:
                try:
                    effort = str(req.get("effort", "high"))
                    if tools:
                        reply = provider.complete_tools(system, messages, tools, model=model, effort=effort,
                                                        label=f"node {node}")
                    else:
                        reply = provider.complete(system, messages, model=model, effort=effort, label=f"node {node}")
                except Exception as e:  # report to the caller instead of dropping the connection
                    return self._send(502, {"error": f"{type(e).__name__}: {e}"})
            self._send(200, {"text": reply.text,
                             "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in reply.tool_calls],
                             "usage": {**(reply.usage or {}), "kind": provider.kind, "model": model}})

        def log_message(self, fmt, *args):
            ui.say(f"  [{self.address_string()}] {fmt % args}")

    return Handler


def serve(kind: str, model: str, host: str = "127.0.0.1", port: int = 8765, url: str = "",
          token_env: str = "AGENT_TEAM_TOKEN", api_key_env: str = "", node: str = "", announce: bool = True) -> None:
    token = os.environ.get(token_env, "")
    if len(token) < 16:
        raise SystemExit(f"Set {token_env} to a random token of at least 16 characters "
                         f"(for example: python3 -c 'import secrets; print(secrets.token_urlsafe(32))').")
    cfg = ProviderConfig(name="node", kind=kind, url=url, api_key_env=api_key_env)
    provider = providers.build(cfg, os.environ.get(api_key_env, "") if api_key_env else "")
    node = node or socket.gethostname()
    httpd = ThreadingHTTPServer((host, port), make_handler(provider, model, token, node))
    ui.heading(f"agent-team node {node!r} serving {kind}/{model} on http://{host}:{port}")
    if host not in ("127.0.0.1", "localhost", "::1"):
        ui.warn("listening beyond this machine: put it behind a VPN, SSH tunnel or HTTPS proxy, "
                "since the token travels in plain HTTP")
        if announce:
            from . import discovery
            if discovery.start_responder(node, kind, model, port):
                ui.say(f"  answering discovery on UDP {discovery.PORT} (teams find it with `agent-team discover`; "
                       "--no-announce to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
