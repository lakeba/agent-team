"""Finding agent-team nodes on the local network, without typing addresses.

A node started with `agent-team serve --host 0.0.0.0` answers discovery probes: UDP datagrams
sent to port 8766. `agent-team discover` (and the dashboard's "Add a machine") broadcasts a probe
and lists the nodes that answer. The answer says only what the node serves (name, provider,
model, port); calling it still needs its token. Start a node with --no-announce to stay quiet.
"""
from __future__ import annotations

import json
import socket
import threading
import time

from . import __version__

PORT = 8766
PROBE = b"agent-team discover v1"


def answer(node: str, kind: str, model: str, port: int) -> bytes:
    return json.dumps({"agent_team": 1, "node": node, "provider": kind, "model": model,
                       "port": port, "version": __version__}).encode()


def start_responder(node: str, kind: str, model: str, port: int, bind: str = "") -> threading.Thread | None:
    """Answer probes in a background thread. Returns None if the discovery port is taken."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    try:
        sock.bind((bind, PORT))
    except OSError:
        sock.close()
        return None
    reply = answer(node, kind, model, port)

    def loop():
        while True:
            try:
                data, addr = sock.recvfrom(512)
            except OSError:
                return
            if data.strip() == PROBE:
                try:
                    sock.sendto(reply, addr)
                except OSError:
                    pass

    t = threading.Thread(target=loop, daemon=True, name="agent-team-discovery")
    t.start()
    return t


def discover(timeout: float = 2.0, targets: tuple[str, ...] = ("255.255.255.255",)) -> list[dict]:
    """Broadcast a probe and collect answers for `timeout` seconds: [{node, url, provider, model, ...}]."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)
    found: dict[str, dict] = {}
    try:
        for target in targets:
            try:
                sock.sendto(PROBE, (target, PORT))
            except OSError:
                continue
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, (host, _) = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                info = json.loads(data)
            except ValueError:
                continue
            if not isinstance(info, dict) or info.get("agent_team") != 1 or not isinstance(info.get("port"), int):
                continue
            url = f"http://{host}:{info['port']}"
            found[url] = {"node": str(info.get("node", "")), "url": url, "host": host,
                          "provider": str(info.get("provider", "")), "model": str(info.get("model", "")),
                          "version": str(info.get("version", ""))}
    finally:
        sock.close()
    return sorted(found.values(), key=lambda n: n["node"])
