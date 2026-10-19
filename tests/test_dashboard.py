"""Usage recording, the log parser, and the read-only dashboard server."""
import http.client
import json
import os
import threading
import time
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer

from agent_team import logs, usage
from agent_team.dashboard import server as dash
from agent_team.workflows import build

import helpers
from helpers import SCRIPTS, load, project, quiet


class UsageTests(unittest.TestCase):
    def test_prices_and_summary(self):
        entries = [
            {"agent": "Atlas", "kind": "anthropic", "model": "claude-opus-5-5", "run": "build@1",
             "input": 1_000_000, "output": 100_000, "cache_read": 1_000_000, "cache_write": 0},
            {"agent": "Forge", "kind": "ollama", "model": "qwen", "run": "build@1", "input": 500, "output": 50},
            {"agent": "X", "kind": "anthropic", "model": "claude-unknown", "run": "", "input": 10, "output": 10},
        ]
        s = usage.summarize(entries)
        self.assertAlmostEqual(s["by_agent"]["Atlas"]["cost"], 4.0 + 2.0 + 0.20)   # input + output + cache read
        self.assertEqual(s["by_agent"]["Forge"]["cost"], 0.0)                         # local models are free
        self.assertEqual(s["unpriced_models"], ["claude-unknown"])
        self.assertEqual(s["by_run"]["build@1"]["calls"], 2)
        self.assertIn("(untagged)", s["by_run"])

    def test_overrides(self):
        s = usage.summarize([{"model": "qwen", "kind": "ollama", "input": 1_000_000, "output": 0}],
                            {"qwen": {"input": 0.5, "output": 1.0}})
        self.assertAlmostEqual(s["total"]["cost"], 0.5)

    def test_workflow_records_usage_per_call_and_tags_the_run(self):
        helpers.reset()
        root = project()
        SCRIPTS["Atlas"].extend(['<file path="PLAN.md">\nplan\n</file>', "VERDICT: APPROVED"])
        SCRIPTS["Forge"].append("done")
        orig = helpers.FakeProvider.complete

        def with_usage(self, *a, **kw):
            r = orig(self, *a, **kw)
            r.usage = {"input": 100, "output": 10}
            return r
        helpers.FakeProvider.complete = with_usage
        try:
            with quiet():
                build.run(load(root), "t", rounds=1)
        finally:
            helpers.FakeProvider.complete = orig
        entries = usage.load(root)
        self.assertEqual([e["agent"] for e in entries], ["Atlas", "Forge", "Atlas"])
        self.assertTrue(all(e["run"].startswith("build@") for e in entries))

    def test_half_written_lines_are_skipped(self):
        root = project()
        (root / ".team").mkdir()
        (root / ".team" / "usage.jsonl").write_text('{"agent": "A", "input": 1}\n{"agent": "B", "inp')
        self.assertEqual(len(usage.load(root)), 1)


class LogParserTests(unittest.TestCase):
    def test_marked_logs_ignore_headings_inside_replies(self):
        helpers.reset()
        root = project()
        SCRIPTS["Atlas"].extend(['# PLAN heading inside a reply\n<file path="PLAN.md">\n# not a run\n</file>',
                                 "## Review\n# also not a run\nVERDICT: APPROVED"])
        SCRIPTS["Forge"].append("# heading\n## another\ndone")
        with quiet():
            build.run(load(root), "add a thing", rounds=1)
        runs = logs.parse(root)
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual(r["title"], "Build: add a thing")
        self.assertEqual([e["who"] + ": " + e["what"] for e in r["entries"]],
                         ["Atlas: plan", "Forge: round 1", "Tests: round 1", "Atlas: review 1"])
        self.assertEqual(r["outcome"], "approved after 1 round(s)")
        self.assertIsNotNone(r["started"])
        self.assertTrue(all(e["at"] for e in r["entries"]))

    def test_legacy_logs_without_markers(self):
        root = project()
        (root / ".team" / "logs").mkdir(parents=True)
        (root / ".team" / "logs" / "ship.md").write_text(
            "\n# Ops shift on o/r\n\n## Harbor: action\n\nmerged PR #3 at abc\n\n## Atlas: review of PR #3 at abc\n\n"
            "# a heading in a reply\n## Changes\nVERDICT: APPROVED\n\n## Harbor: shift summary\n\ndone\n")
        runs = logs.parse(root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0]["entries"]), 3)
        self.assertEqual(runs[0]["outcome"], "merged PR #3 at abc")
        self.assertIsNone(runs[0]["started"])


class MixedLogTests(unittest.TestCase):
    def test_old_unmarked_runs_followed_by_marked_ones(self):
        helpers.reset()
        root = project()
        (root / ".team" / "logs").mkdir(parents=True)
        (root / ".team" / "logs" / "build.md").write_text(
            "\n# Task\n\nold task one\n\n## Atlas: plan\n\nplan\n\n## Atlas: review 1\n\nVERDICT: APPROVED\n")
        SCRIPTS["Atlas"].extend(['<file path="PLAN.md">\nplan\n</file>', "VERDICT: APPROVED"])
        SCRIPTS["Forge"].append("done")
        with quiet():
            build.run(load(root), "new task", rounds=1)
        runs = logs.parse(root)
        self.assertEqual(sorted(r["title"] for r in runs), ["Build: new task", "old task one"])
        self.assertTrue(all(r["outcome"].startswith("approved") for r in runs))


class DashboardPortZeroTests(unittest.TestCase):
    def test_port_0_serves_on_the_port_it_got(self):
        started = []

        class Recording(ThreadingHTTPServer):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                started.append(self)

        root = project()
        with mock.patch.object(dash, "ThreadingHTTPServer", Recording), quiet():
            t = threading.Thread(target=dash.serve, args=(root, 0, False), daemon=True)
            t.start()
            for _ in range(100):
                if started:
                    break
                time.sleep(0.05)
            httpd = started[0]
            port = httpd.server_address[1]
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.request("GET", "/api/team", headers={"Host": f"127.0.0.1:{port}"})
                self.assertEqual(c.getresponse().status, 200)
            finally:
                httpd.shutdown()
                t.join(5)


class DashboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = project()
        os.environ.pop("DEMO_KEY", None)
        text = (cls.root / ".team.toml").read_text().replace('kind = "fake"', 'kind = "fake"\napi_key_env = "DEMO_KEY"')
        (cls.root / ".team.toml").write_text(text)
        os.environ["DEMO_KEY"] = "super-secret-value-123"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.RequestHandlerClass = dash.make_handler(cls.root, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop("DEMO_KEY", None)

    def get(self, path, host=None, method="GET"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, headers={"Host": host or f"127.0.0.1:{self.port}"})
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()

    def test_team_never_contains_secret_values(self):
        status, headers, body = self.get("/api/team")
        self.assertEqual(status, 200)
        self.assertNotIn(b"super-secret-value-123", body)
        member = json.loads(body)["members"][0]
        self.assertEqual(member["key_env"], "DEMO_KEY")
        self.assertTrue(member["key_set"])

    def test_pages_and_security_headers(self):
        for path, ctype in [("/", "text/html"), ("/app.js", "text/javascript"), ("/app.css", "text/css")]:
            status, headers, _ = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(headers["Content-Type"].startswith(ctype))
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_wrong_host_is_refused(self):
        self.assertEqual(self.get("/api/team", host="evil.example:80")[0], 421)

    def test_writes_without_the_session_token_are_refused(self):
        self.assertEqual(self.get("/api/config/save", method="POST")[0], 403)
        for method in ("PUT", "DELETE"):
            self.assertEqual(self.get("/api/team", method=method)[0], 405)

    def test_health_runs_usage_and_github(self):
        self.assertTrue(all(m["ok"] for m in json.loads(self.get("/api/health")[2])["members"].values()))
        self.assertEqual(json.loads(self.get("/api/runs")[2]), {"runs": []})
        self.assertEqual(json.loads(self.get("/api/usage")[2])["recorded_calls"], 0)
        self.assertFalse(json.loads(self.get("/api/github")[2])["available"])   # no repo configured

    def test_unknown_paths(self):
        self.assertEqual(self.get("/etc/passwd")[0], 404)
        self.assertEqual(self.get("/api/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
