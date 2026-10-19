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

    def test_lan_candidates_cover_private_networks_but_not_this_machine(self):
        with mock.patch.object(readiness, "_own_addresses", return_value={"192.168.1.92", "8.8.4.4"}):
            urls = helpers.REAL_LAN_CANDIDATES()
        self.assertIn("http://192.168.1.20:8080", urls)
        self.assertIn("http://192.168.1.20:11434", urls)
        self.assertNotIn("http://192.168.1.92:8080", urls)              # this machine: localhost covers it
        self.assertFalse(any("8.8.4." in u for u in urls))              # public networks are never scanned
        self.assertEqual(len(urls), 253 * len(readiness.SCAN_PORTS))

    def test_scan_finds_servers_on_other_machines(self):
        port = self.url.rsplit(":", 1)[1]
        with mock.patch.object(readiness, "lan_candidates", return_value=[f"http://127.0.0.1:{port}", "http://127.0.0.1:9"]), \
                mock.patch.object(readiness, "local_candidates", return_value=[]), \
                mock.patch.object(readiness, "find_ollama", return_value=[]):
            found = readiness.find_local(scan=True)
            self.assertEqual([f["url"] for f in found], [self.url])
            self.assertEqual(readiness.find_local(), [])               # without scan: only the nearby addresses

    def test_paths_are_not_offered_as_models(self):
        FakeMlx.models = ["mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                          "/Users/x/.cache/huggingface/hub/models--mlx-community--Q/snapshots/019cc"]
        try:
            self.assertEqual(readiness.probe(self.url)["models"], ["mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"])
        finally:
            FakeMlx.models = ["mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"]

    def test_a_vm_scans_the_home_networks_whose_router_answers(self):
        with mock.patch.object(readiness, "in_vm", return_value=True), \
                mock.patch.object(readiness, "_own_addresses", return_value={"10.211.55.4"}), \
                mock.patch.object(readiness, "_connect", side_effect=lambda h, p, t: "refused" if h == "192.168.1.1" else "none"):
            self.assertEqual(helpers.REAL_HOME_NETWORKS(), ["192.168.1"])
        with mock.patch.object(readiness, "in_vm", return_value=False):
            self.assertEqual(helpers.REAL_HOME_NETWORKS(), [])

    def test_gentle_scan_finds_a_server_behind_a_silent_port(self):
        port = int(self.url.rsplit(":", 1)[1])
        with mock.patch.object(readiness, "SCAN_PORTS", (11434, port)), \
                mock.patch.object(readiness, "_connect", side_effect=lambda h, p, t: "open" if p == port and h == "127.0.0.1" else "none"):
            found = readiness._gentle_scan(["127.0.0"], 2)
        self.assertEqual([f["url"] for f in found], [self.url])

    def test_incomplete_addresses_are_caught(self):
        from agent_team.config import ConfigError, address_problem, parse
        self.assertIn("for example 192.168.1.141", address_problem("http://192.168.141:8080"))
        self.assertIn("isn't a valid address", address_problem("http://300.1.1.1:80"))
        self.assertIn("needs http://", address_problem("192.168.1.2:80"))
        for ok in ("http://192.168.1.141:8080", "http://studio.local:11434", "http://[::1]:8080", ""):
            self.assertEqual(address_problem(ok), "", ok)
        data = {"project": {"name": "x"}, "providers": {"mlx": {"kind": "openai", "url": "http://192.168.141:8080"}},
                "agents": [{"name": "A", "role": "lead", "provider": "mlx"}]}
        with self.assertRaisesRegex(ConfigError, "192.168.141 isn't a valid address"):
            parse(data, Path(tempfile.mkdtemp()))
        with self.assertRaises(SystemExit):
            init.find_server("http://192.168.141:8080", False)

    def test_a_short_model_name_gets_the_full_one_suggested(self):
        from agent_team.providers import build
        from agent_team.providers.http_providers import closest_model
        served = ["mlx-community/Qwen2.5-Coder-7B-Instruct-4bit", "/cache/models--x/snapshots/1"]
        self.assertEqual(closest_model("Qwen2.5-Coder-7B-Instruct-4bit", served), served[0])
        self.assertEqual(closest_model("qwen2.5-coder-7b-instruct-4bit", served), served[0])
        self.assertEqual(closest_model("llama3", served), "")
        self.assertEqual(closest_model("qwen3", ["qwen3:latest"]), "qwen3:latest")
        status = build(config.ProviderConfig(name="m", kind="openai", url=self.url), "").check("Qwen2.5-Coder-7B-Instruct-4bit")
        self.assertIn("did you mean 'mlx-community/Qwen2.5-Coder-7B-Instruct-4bit'", status)

    def test_test_folder_keeps_its_real_name(self):
        for names, expected in ((["Tests"], "Tests/"), (["tests"], "tests/"), (["App", "App.Tests"], "App.Tests/"), (["src"], "tests/")):
            root = Path(tempfile.mkdtemp())
            for n in names:
                (root / n).mkdir()
            self.assertEqual(init.test_dir(root), expected, names)

    def test_an_owned_path_with_the_wrong_case_is_reported(self):
        from helpers import project
        root = project(files={"Tests/test_a.py": ""})
        text = (root / ".team.toml").read_text().replace('name = "Forge"\nrole = "builder"', 'name = "Forge"\nrole = "builder"\nowns = ["tests/"]')
        (root / ".team.toml").write_text(text)
        check = {c.name: c for c in readiness.check(root)}["Forge owns tests/"]
        self.assertFalse(check.ok)
        self.assertIn('"Tests/"', check.fix)

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
