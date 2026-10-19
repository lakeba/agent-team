"""Local model servers besides Ollama: mlx_lm, LM Studio, llama.cpp (the OpenAI API)."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (test isolation)
from helpers import quiet

from agent_team import composition, config, readiness
from agent_team.workflows import init


class FakeMlx(BaseHTTPRequestHandler):
    """Like mlx_lm.server: Python's http.server, /v1/models in the OpenAI shape."""
    models = ["mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"]

    def do_GET(self):
        if self.path == "/v1/models":
            body = json.dumps({"object": "list", "data": [{"id": m, "object": "model"} for m in self.models]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


class LocalServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), FakeMlx)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_probe_recognises_mlx_lm(self):
        found = readiness.probe(self.url)
        self.assertEqual(found["kind"], "openai")
        self.assertEqual(found["label"], "mlx_lm")
        self.assertEqual(found["models"], FakeMlx.models)
        self.assertIsNone(readiness.probe("http://127.0.0.1:9", timeout=0.5))

    def test_labels(self):
        self.assertEqual(readiness.server_label("http://h:1234", ["qwen"], "uvicorn"), "LM Studio")
        self.assertEqual(readiness.server_label("http://h:8080", ["m"], "llama.cpp"), "llama.cpp")
        self.assertEqual(readiness.server_label("http://h:8080", ["mlx-community/x"], ""), "mlx_lm")
        self.assertEqual(readiness.server_label("http://h:9000", ["m"], "nginx"), "OpenAI-compatible server")

    def test_find_local_lists_ollama_then_others(self):
        with mock.patch.object(readiness, "find_ollama", return_value=[("http://localhost:11434", ["q"])]):
            found = readiness.find_local(candidates=["http://localhost:11434", self.url])
        self.assertEqual([(f["kind"], f["label"]) for f in found], [("ollama", "Ollama"), ("openai", "mlx_lm")])

    def test_candidates_cover_the_openai_ports(self):
        with mock.patch.object(readiness, "ollama_candidates", return_value=["http://localhost:11434", "http://10.211.55.2:11434"]):
            urls = readiness.local_candidates()
        for u in ("http://localhost:8080", "http://localhost:1234", "http://10.211.55.2:8080"):
            self.assertIn(u, urls)

    def test_init_on_an_mlx_server(self):
        root = Path(tempfile.mkdtemp())
        with quiet():
            init.run(root, ollama_url=self.url, models="ollama", builder_model=FakeMlx.models[0])
        team = config.load(root)
        self.assertEqual((team.providers["local"].kind, team.providers["local"].url), ("openai", self.url))
        self.assertEqual({a.model for a in team.agents.values()}, {FakeMlx.models[0]})
        checks = {c.name: c for c in readiness.check(root)}
        self.assertTrue(checks[f"model server at {self.url}"].ok)
        self.assertTrue(checks[f"model {FakeMlx.models[0]}"].ok)

    def test_recomposing_keeps_the_kind(self):
        c = composition.Composition(models="mixed", ollama_url=self.url, ollama_model="m", local_kind="openai")
        self.assertIn('kind = "openai"', composition.providers_text(c))
        data = composition.apply({"providers": {}, "agents": []}, c)
        self.assertEqual(data["providers"]["local"], {"kind": "openai", "url": self.url})
        back = composition.from_data(data)
        self.assertEqual((back.local_kind, back.ollama_url, back.ollama_model), ("openai", self.url, "m"))
        with self.assertRaises(ValueError):
            composition.Composition(local_kind="gpt").check()


if __name__ == "__main__":
    unittest.main()
