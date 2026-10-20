"""Local model servers besides Ollama: mlx_lm, LM Studio, llama.cpp, vLLM, Jan... (the OpenAI API)."""
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
            owner = {"owned_by": self.owner} if getattr(self, "owner", "") else {}
            body = json.dumps({"object": "list", "data": [{"id": m, "object": "model", **owner} for m in self.models]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


class SlowMlx(FakeMlx):
    """mlx_lm reads its model cache on every /v1/models: a couple of seconds before it answers."""
    def do_GET(self):
        import time
        time.sleep(1.2)
        super().do_GET()


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

    def test_a_slow_listing_is_still_found(self):
        httpd = HTTPServer(("127.0.0.1", 0), SlowMlx)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}"
            found = readiness.probe(url, timeout=0.5)   # the sweep's quick timeout: the open port earns a longer wait
            self.assertEqual(found and found["models"], SlowMlx.models)
            self.assertEqual(readiness._scan([url], 0.5)[0]["url"], url)
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertFalse(readiness._port_open("http://127.0.0.1"))   # no port: no crash

    def test_labels(self):
        self.assertEqual(readiness.server_label("http://h:1234", ["qwen"], "uvicorn"), "LM Studio")
        self.assertEqual(readiness.server_label("http://h:8080", ["m"], "llama.cpp"), "llama.cpp")
        self.assertEqual(readiness.server_label("http://h:8080", ["mlx-community/x"], ""), "mlx_lm")
        self.assertEqual(readiness.server_label("http://h:9000", ["m"], "nginx"), "OpenAI-compatible server")

    def test_other_local_ai_apps_by_name(self):
        label = readiness.server_label
        self.assertEqual(label("http://h:8000", ["Qwen/Qwen2.5-7B"], "uvicorn", ("vllm",)), "vLLM")
        self.assertEqual(label("http://h:8000", ["m"], "uvicorn"), "vLLM")
        self.assertEqual(label("http://h:1337", ["m"], "", ("llamacpp",)), "Jan")       # Jan runs llama.cpp inside
        self.assertEqual(label("http://h:1234", ["m"], "", ("organization_owner",)), "LM Studio")
        self.assertEqual(label("http://h:5000", ["m"], "uvicorn"), "text-generation-webui")
        self.assertEqual(label("http://h:5001", ["m"], "", ("koboldcpp",)), "KoboldCpp")
        self.assertEqual(label("http://h:4891", ["m"], ""), "GPT4All")
        self.assertEqual(label("http://h:8080", ["m"], "llamafile", ("llamafile",)), "llamafile")
        self.assertEqual(label("http://h:8080", ["m"], "", ("llamacpp",)), "llama.cpp")
        self.assertEqual(label("http://h:8080", ["gpt-4"], ""), "LocalAI")
        self.assertEqual(label("http://h:9000", ["m"], "", ("localai",)), "LocalAI")

    def test_probe_names_the_server_from_what_it_says(self):
        FakeMlx.owner = "vllm"
        try:
            found = readiness.probe(self.url)
        finally:
            del FakeMlx.owner
        self.assertEqual((found["kind"], found["label"]), ("openai", "vLLM"))

    def test_find_local_lists_ollama_then_others(self):
        with mock.patch.object(readiness, "find_ollama", return_value=[("http://localhost:11434", ["q"])]):
            found = readiness.find_local(candidates=["http://localhost:11434", self.url])
        self.assertEqual([(f["kind"], f["label"]) for f in found], [("ollama", "Ollama"), ("openai", "mlx_lm")])

    def test_candidates_cover_the_openai_ports(self):
        with mock.patch.object(readiness, "ollama_candidates", return_value=["http://localhost:11434", "http://10.211.55.2:11434"]):
            urls = readiness.local_candidates()
        for u in ("http://localhost:8080", "http://localhost:1234", "http://localhost:8000", "http://localhost:1337",
                  "http://localhost:5000", "http://localhost:5001", "http://localhost:4891", "http://10.211.55.2:8080"):
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

    def test_a_test_without_a_model_lists_what_is_served(self):
        from agent_team.dashboard.server import _test_provider
        from agent_team.providers import build
        status = build(config.ProviderConfig(name="m", kind="openai", url=self.url), "").check("")
        self.assertTrue(status.startswith("ok ("), status)
        self.assertIn("serves: mlx-community/Qwen2.5-Coder-7B-Instruct-4bit", status)
        r = _test_provider({"provider": {"kind": "openai", "url": self.url}, "model": ""})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["models"], FakeMlx.models)   # the page fills its Model list with these
        r = _test_provider({"provider": {"kind": "openai", "url": "http://127.0.0.1:9"}, "model": ""})
        self.assertFalse(r["ok"])
        self.assertEqual(r["models"], [])

    def test_a_member_without_a_model(self):
        from agent_team.providers import build
        from agent_team.providers.http_providers import _model
        # OpenAI-compatible: the model is left out, so mlx_lm uses its --model (it fails on an empty name)
        self.assertNotIn("model", _model({"messages": []}, ""))
        self.assertEqual(_model({"messages": []}, "m")["model"], "m")
        status = build(config.ProviderConfig(name="m", kind="openai", url=self.url), "").check_member("")
        self.assertTrue(status.startswith("ok (no model set, so the server's default;"), status)
        # Ollama answers "model is required": the team's check says so
        with mock.patch("agent_team.providers.http_providers._get_json", return_value={"models": [{"name": "qwen3"}]}):
            p = build(config.ProviderConfig(name="o", kind="ollama", url="http://127.0.0.1:11434"), "")
            self.assertTrue(p.check("").startswith("ok"))   # Test connection lists what's pulled
            status = p.check_member("")
        self.assertTrue(status.startswith("FAILED: no model chosen; Ollama needs one"), status)
        self.assertIn("qwen3", status)

    def test_the_team_page_names_what_runs_without_a_model(self):
        js = (Path(__file__).resolve().parent.parent / "src/agent_team/dashboard/static/app.js").read_text()
        self.assertIn('m.model || noModel(m.kind)', js)
        self.assertIn('kind === "agent-http" ? "chosen by the node" : kind === "openai" ? "the server\'s default"', js)

    def test_the_host_reached_on_two_vm_networks_is_listed_once(self):
        models = FakeMlx.models
        def found(host, port=8080, label="mlx_lm", m=models):
            return {"url": f"http://{host}:{port}", "kind": "openai", "label": label, "models": list(m)}
        finds = [found("10.211.55.2"), found("10.37.129.2"),
                 found("192.168.1.20"), found("192.168.1.21"),      # two machines serving the same model
                 found("10.0.2.2", port=1234, label="LM Studio")]
        with mock.patch.object(readiness, "find_ollama", return_value=[]), \
                mock.patch.object(readiness, "probe", side_effect=lambda u, t: next(f for f in finds if f["url"] == u)):
            out = readiness.find_local(candidates=[f["url"] for f in finds])
        self.assertEqual([f["url"] for f in out], ["http://10.211.55.2:8080", "http://192.168.1.20:8080",
                                                   "http://192.168.1.21:8080", "http://10.0.2.2:1234"])
        same = readiness._same_host_server
        self.assertFalse(same(found("10.211.55.2"), found("10.37.129.2", m=["other"])))    # different models
        self.assertFalse(same(found("10.211.55.2"), found("10.37.129.2", port=8000)))      # different port
        self.assertFalse(same(found("10.211.55.2"), found("10.211.55.3")))                 # not a host address
        self.assertFalse(same(found("10.211.55.2", m=[]), found("10.37.129.2", m=[])))     # nothing to compare

    def test_chat_template_tokens_are_taken_out(self):
        from agent_team import files
        from agent_team.providers.http_providers import clean
        reply = "Great plan.\n\nSTATUS: AGREE<|im_end|>"   # what mlx_lm with Qwen returned in a real discussion
        self.assertEqual(files.last_marker(files.STATUS_RE, reply), "")   # not seen: the discussion never agreed
        self.assertEqual(files.last_marker(files.STATUS_RE, clean(reply)), "AGREE")
        self.assertEqual(clean("hi<|eot_id|>"), "hi")
        self.assertEqual(clean("a </s>"), "a")
        self.assertEqual(clean("x < y and <b>bold</b>"), "x < y and <b>bold</b>")

    def test_tool_calls_written_as_text_are_read(self):
        from agent_team.providers.http_providers import calls_in_text
        names = {"read_file", "run_tests"}
        call = '{"name": "read_file", "arguments": {"path": "ROADMAP.md"}}'   # as Qwen2.5-Coder on mlx_lm wrote it
        (c,) = calls_in_text(call, names)
        self.assertEqual((c.name, c.arguments), ("read_file", {"path": "ROADMAP.md"}))
        self.assertEqual(len(calls_in_text(f"```json\n{call}\n```", names)), 1)
        self.assertEqual(len(calls_in_text(f"<tool_call>\n{call}\n</tool_call><tool_call>{{\"name\": \"run_tests\"}}</tool_call>", names)), 2)
        self.assertEqual(calls_in_text('{"name": "delete_everything", "arguments": {}}', names), [])
        self.assertEqual([c.name for c in calls_in_text('Here: {"name": "read_file"}', names)], ["read_file"])   # a call ending the reply
        self.assertEqual(calls_in_text('{"name": "read_file", "arguments": "x"}', names), [])
        said = 'Sure, I will run them.\n\n{"name": "run_tests", "arguments": "{\\"only\\": \\"slots\\"}"}'   # seen in a real chat
        (c,) = calls_in_text(said, names)
        self.assertEqual((c.name, c.arguments), ("run_tests", {"only": "slots"}))
        self.assertEqual(calls_in_text('Use {"name": "read_file"} first, then continue.', names), [])

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
