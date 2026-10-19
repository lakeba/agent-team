"""Inspire without a terminal: a checked background run, the owner's confirmation, and the API the
dashboard and the desktop app read."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import helpers
from helpers import project

from agent_team import inspire, jobs, mcp_server
from agent_team.dashboard import server as dash


class ArgvTests(unittest.TestCase):
    def test_a_checked_inspire_run(self):
        argv = jobs.argv_for("inspire", {"url": "https://app.example/", "max_pages": 6,
                                         "journeys": [['click link "Pricing"', "wait 500"], ["goto /docs"]]})
        self.assertEqual(argv, ["inspire", "https://app.example/", "--max-pages", "6",
                                "--journey", 'click link "Pricing"; wait 500', "--journey", "goto /docs"])
        self.assertEqual(jobs.argv_for("inspire", {"url": "https://app.example/"})[3], str(inspire.MAX_PAGES))

    def test_bad_input_is_refused_before_anything_starts(self):
        for params, words in [
            ({"url": "file:///etc/passwd"}, "web address"),
            ({"url": "https://app.example/ x"}, "web address"),
            ({"url": "https://app.example/", "max_pages": 500}, "max_pages"),
            ({"url": "https://app.example/", "journeys": [["wait 1s"]]}, "journey 1, step 1"),
            ({"url": "https://app.example/", "journeys": [['click link "A"; goto /x']]}, "no ';'"),
            ({"url": "https://app.example/", "journeys": [[]]}, "journey 1 is a list"),
            ({"url": "https://app.example/", "journeys": [["wait 500"]] * 6}, "at most 5"),
        ]:
            with self.subTest(params=params), self.assertRaises(jobs.JobError) as e:
                jobs.argv_for("inspire", params)
            self.assertIn(words, str(e.exception))

    def test_mcp_never_offers_it(self):
        self.assertNotIn("inspire", mcp_server.WORKFLOWS)
        start = next(t for t in mcp_server.tools() if t["name"] == "team_start_run")
        self.assertNotIn("inspire", start["inputSchema"]["properties"]["workflow"]["enum"])
        with self.assertRaises(mcp_server.ToolError):
            mcp_server.call("team_start_run", {"workflow": "inspire", "url": "https://app.example/"}, project())


class ApiTests(unittest.TestCase):
    TOKEN = "c" * 40

    def setUp(self):
        helpers.reset()
        self.root = project()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = dash.make_handler(self.root, self.port, token="s" * 40, client_token=self.TOKEN)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def call(self, method, path, body=None, auth=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.TOKEN}"
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
        r = c.getresponse()
        data = r.read()
        return r.status, (json.loads(data or b"{}") if r.getheader("Content-Type", "").startswith("application/json") else data)

    def test_the_feature_is_announced(self):
        self.assertIn("inspiration", self.call("GET", "/api/meta")[1]["features"])

    def test_only_a_confirmed_app_is_explored(self):
        url = "https://app.example/"
        status, body = self.call("POST", "/api/jobs/start", {"workflow": "inspire", "params": {"url": url}})
        self.assertEqual(status, 422)
        self.assertIn("confirm first", body["error"])
        self.assertEqual(self.call("POST", "/api/inspiration/confirm", {"url": url}, auth=False)[0], 403)   # owners only
        self.assertEqual(self.call("POST", "/api/inspiration/confirm", {"url": "javascript:alert(1)"})[0], 422)
        status, body = self.call("POST", "/api/inspiration/confirm", {"url": url})
        self.assertEqual((status, body["app"], body["statement"]), (200, "app-example", inspire.CONFIRMATION))
        self.assertTrue(inspire.confirmed(self.root, url))
        real = jobs.subprocess.Popen

        def popen(argv, *a, **kw):   # the run itself isn't started; everything else runs as usual
            return mock.Mock(pid=99999999) if "agent_team.jobs" in argv else real(argv, *a, **kw)

        with mock.patch.object(jobs.subprocess, "Popen", popen):
            status, job = self.call("POST", "/api/jobs/start", {"workflow": "inspire", "params": {
                "url": url, "journeys": [['click link "Pricing"']]}})
        self.assertEqual(status, 200)
        self.assertEqual(job["argv"], ["inspire", url, "--max-pages", "20", "--journey", 'click link "Pricing"'])

    def test_apps_details_and_screenshots(self):
        url = "https://app.example/"
        inspire.confirm(self.root, url)
        f = inspire.folder(self.root, url)
        (f / "pages").mkdir()
        (f / "pages" / "01.png").write_bytes(b"\x89PNG fake")
        (f / "index.json").write_text(json.dumps({"start": url, "pages": [{"label": "page 1", "url": url, "problem": ""}],
                                                  "journeys": [], "skipped": [], "notes": ["a note"], "asked": [["wait 500"]]}))
        (f / "brief.md").write_text("## What it is\nA tracker.")
        status, body = self.call("GET", "/api/inspiration")
        (app,) = body["apps"]
        self.assertEqual((app["app"], app["url"], app["brief"], app["confirmed"], app["pages"]), ("app-example", url, True, True, 1))
        self.assertEqual(body["statement"], inspire.CONFIRMATION)
        status, d = self.call("GET", "/api/inspiration/app-example")
        self.assertEqual((d["brief"], d["pages"][0]["shot"], d["asked"], d["notes"]),
                         ("## What it is\nA tracker.", "pages/01.png", [["wait 500"]], ["a note"]))
        status, png = self.call("GET", "/api/inspiration/app-example/shot/pages/01.png")
        self.assertEqual((status, png), (200, b"\x89PNG fake"))
        for bad in ("/api/inspiration/app-example/shot/../../.team.toml", "/api/inspiration/app-example/shot/brief.md",
                    "/api/inspiration/app-example/shot/pages%2F..%2F..%2F.team.toml", "/api/inspiration/..%2F..%2Fetc",
                    "/api/inspiration/nope", "/api/inspiration/app-example/shot/pages/02.png"):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("GET", bad)[0], 404)
        self.assertEqual(self.call("POST", "/api/inspiration/forget", {"app": "app-example"}, auth=False)[0], 403)
        self.assertEqual(self.call("POST", "/api/inspiration/forget", {"app": "../x"})[0], 422)
        self.assertEqual(self.call("POST", "/api/inspiration/forget", {"app": "app-example"})[1], {"forgotten": True})
        self.assertEqual(self.call("GET", "/api/inspiration")[1]["apps"], [])

    def test_the_tab_is_served(self):
        status, page = self.call("GET", "/")
        self.assertIn(b'data-tab="inspire"', page)
        status, js = self.call("GET", "/inspire.js")
        self.assertEqual(status, 200)
        self.assertNotIn(b"innerHTML", js)   # the brief is drawn as text, never as HTML


if __name__ == "__main__":
    unittest.main()
