"""A remote node (`agent-team serve`) and the agent-http provider talking to each other."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from agent_team import providers, server
from agent_team.config import ProviderConfig
from agent_team.providers.base import ProviderError

import helpers
from helpers import SCRIPTS, CALLS, quiet

TOKEN = "t" * 32


class RemoteNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake = providers.build(ProviderConfig(name="f", kind="fake"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(fake, "tiny", TOKEN, "box-1"))
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        helpers.reset()

    def client(self, token=TOKEN):
        return providers.build(ProviderConfig(name="r", kind="agent-http", url=self.url, api_key_env="X"), token)

    def test_round_trip(self):
        SCRIPTS["node box-1"].append("hello from the node")
        with quiet():
            reply = self.client().complete("sys", [{"role": "user", "content": "hi"}],
                                           model="tiny", effort="low", label="Forge")
        self.assertEqual(reply.text, "hello from the node")
        self.assertEqual(CALLS[-1]["system"], "sys")

    def test_info(self):
        with quiet():
            self.assertIn("box-1", self.client().check("tiny"))

    def test_wrong_token_is_rejected(self):
        with quiet(), self.assertRaisesRegex(ProviderError, "401"):
            self.client("wrong-token-wrong-token").complete("s", [{"role": "user", "content": "x"}],
                                                            model="m", effort="low", label="L")

    def test_missing_token_fails_before_sending(self):
        with self.assertRaisesRegex(ProviderError, "needs a token"):
            self.client("").complete("s", [{"role": "user", "content": "x"}], model="m", effort="low", label="L")

    def test_bad_request(self):
        req = urllib.request.Request(f"{self.url}/v1/turn", data=json.dumps({"system": "s", "messages": []}).encode(),
                                     headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        with quiet(), self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_serve_refuses_a_weak_token(self):
        import os
        os.environ["AGENT_TEAM_TEST_TOKEN"] = "short"
        with self.assertRaises(SystemExit):
            server.serve("fake", "m", token_env="AGENT_TEAM_TEST_TOKEN")


if __name__ == "__main__":
    unittest.main()
