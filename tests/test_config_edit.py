"""Editing .team.toml: the writer, and the dashboard's protected write API."""
import http.client
import json
import threading
import tomllib
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent_team import config, config_io
from agent_team.dashboard import server as dash

import helpers  # noqa: F401
from helpers import load, project

ROOT = Path(__file__).resolve().parent.parent


class WriterTests(unittest.TestCase):
    def test_examples_round_trip(self):
        for f in ["examples/todo-py.team.toml", "examples/distributed.team.toml", ".team.toml"]:
            team = config.load(ROOT / f)
            text = config_io.render(config_io.to_data(team))
            self.assertEqual(config_io.to_data(config_io.validate(text, team.root)), config_io.to_data(team), f)

    def test_strings_are_escaped(self):
        text = config_io.render({"project": {"name": 'a "quoted"\\name\nnext', "guarantees": ["tab\there"]},
                                 "providers": {"c": {"kind": "fake"}},
                                 "agents": [{"name": "Ünïcødé ✓", "role": "lead", "provider": "c"}]})
        data = tomllib.loads(text)
        self.assertEqual(data["project"]["name"], 'a "quoted"\\name\nnext')
        self.assertEqual(data["agents"][0]["name"], "Ünïcødé ✓")

    def test_unknown_keys_from_the_api_are_dropped(self):
        data = config_io.clean({"project": {"name": "p", "evil": 1}, "providers": {"c": {"kind": "fake", "x": 2}},
                                "agents": [{"name": "A", "role": "lead", "provider": "c", "owns": ["", " a/ "], "z": 3}]})
        self.assertNotIn("evil", data["project"])
        self.assertNotIn("x", data["providers"]["c"])
        self.assertEqual(data["agents"][0], {"name": "A", "role": "lead", "provider": "c", "owns": ["a/"]})

    def test_plan_change_reports_invalid_teams(self):
        root = project()
        data = config_io.to_data(load(root))
        data["agents"][0]["provider"] = "nope"
        change = config_io.plan_change(root, data)
        self.assertFalse(change["valid"])
        self.assertIn("unknown provider", change["error"])

    def test_save_validates_backs_up_and_refuses_concurrent_edits(self):
        root = project()
        before = (root / ".team.toml").read_text()
        data = config_io.to_data(load(root))
        data["agents"].append({"name": "Quinn", "role": "reviewer", "provider": "fake", "owns": ["src/auth/"]})
        result = config_io.save(root, data, expected_old=before)
        self.assertTrue(result["saved"])
        self.assertEqual((root / ".team.toml.bak").read_text(), before)
        self.assertEqual(load(root).get("Quinn").owns, ["src/auth/"])
        with self.assertRaisesRegex(config.ConfigError, "changed on disk"):
            config_io.save(root, data, expected_old=before)
        bad = config_io.to_data(load(root))
        bad["agents"] = []
        with self.assertRaisesRegex(config.ConfigError, "no \\[\\[agents\\]\\]"):
            config_io.save(root, bad)


class WriteApiTests(unittest.TestCase):
    TOKEN = "t" * 40

    @classmethod
    def setUpClass(cls):
        cls.root = project()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.RequestHandlerClass = dash.make_handler(cls.root, cls.port, token=cls.TOKEN)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.origin = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, token=None, origin=None, ctype="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if method == "POST":
            headers.update({"Origin": origin or self.origin, "Content-Type": ctype,
                            "X-Agent-Team-Token": self.TOKEN if token is None else token})
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def config(self):
        return self.call("GET", "/api/config")[1]

    def test_session_token_is_served_to_the_page(self):
        self.assertEqual(self.call("GET", "/api/session")[1]["token"], self.TOKEN)

    def test_writes_need_token_origin_and_json(self):
        cfg = self.config()
        body = {"data": cfg["data"], "sha": cfg["sha"]}
        self.assertEqual(self.call("POST", "/api/config/save", body, token="wrong")[0], 403)
        self.assertEqual(self.call("POST", "/api/config/save", body, origin="http://evil.example")[0], 403)
        self.assertEqual(self.call("POST", "/api/config/save", body, ctype="text/plain")[0], 415)

    def test_preview_then_save(self):
        cfg = self.config()
        data = cfg["data"]
        data["project"]["guarantees"] = data["project"].get("guarantees", []) + ["Every PR has a test"]
        status, preview = self.call("POST", "/api/config/preview", {"data": data})
        self.assertEqual(status, 200)
        self.assertTrue(preview["valid"])
        self.assertIn('+guarantees = ["Never delete user data", "Every PR has a test"]', preview["diff"])
        status, saved = self.call("POST", "/api/config/save", {"data": data, "sha": cfg["sha"]})
        self.assertEqual(status, 200, saved)
        self.assertIn("Every PR has a test", load(self.root).project.guarantees)
        # the old sha is now stale
        self.assertEqual(self.call("POST", "/api/config/save", {"data": data, "sha": cfg["sha"]})[0], 409)

    def test_invalid_save_is_refused_and_nothing_changes(self):
        cfg = self.config()
        before = (self.root / ".team.toml").read_text()
        data = cfg["data"]
        data["agents"][0]["provider"] = "missing"
        status, body = self.call("POST", "/api/config/save", {"data": data, "sha": cfg["sha"]})
        self.assertEqual(status, 422)
        self.assertEqual((self.root / ".team.toml").read_text(), before)

    def test_node_token_and_provider_test(self):
        status, body = self.call("POST", "/api/node-token", {})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(body["token"]), 40)
        status, body = self.call("POST", "/api/test-provider", {"provider": {"kind": "fake"}, "model": "m"})
        self.assertEqual((status, body["ok"]), (200, True))
        status, body = self.call("POST", "/api/test-provider", {"provider": {"kind": "nope"}})
        self.assertEqual(status, 422)


if __name__ == "__main__":
    unittest.main()
