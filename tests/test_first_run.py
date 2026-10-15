"""The first minutes on a new machine: the keys file, the readiness checklist and a smarter init."""
import json
import os
import re
import stat
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from agent_team import cli, keys, readiness
from agent_team.workflows import init

from helpers import load, project, quiet


class KeysFileTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.home}, clear=False)
        self.env.start()
        for name in ("AT_TEST_KEY", "AT_OTHER"):
            os.environ.pop(name, None)
        keys._loaded.clear()

    def tearDown(self):
        self.env.stop()

    def test_saved_privately_and_loaded_into_any_command(self):
        keys.set_key("AT_TEST_KEY", "secret-value")
        p = keys.path()
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(p.parent.stat().st_mode), 0o700)
        os.environ.pop("AT_TEST_KEY")
        keys._loaded.clear()
        keys.load_into_env()
        self.assertEqual(os.environ["AT_TEST_KEY"], "secret-value")
        self.assertEqual(keys.where("AT_TEST_KEY"), "keys file")

    def test_the_environment_wins_over_the_file(self):
        keys.set_key("AT_OTHER", "from-file")
        keys._loaded.clear()
        os.environ["AT_OTHER"] = "from-shell"
        keys.load_into_env()
        self.assertEqual(os.environ["AT_OTHER"], "from-shell")
        self.assertEqual(keys.where("AT_OTHER"), "environment")

    def test_values_are_never_printed_and_never_taken_from_arguments(self):
        keys.set_key("AT_TEST_KEY", "secret-value")
        with mock.patch("sys.stdout.write") as out, quiet():
            cli.main(["keys", "list"])
        self.assertNotIn("secret-value", "".join(str(c) for c in out.call_args_list))
        with mock.patch("sys.stdin.isatty", return_value=False), self.assertRaises(SystemExit) as e, quiet():
            cli.main(["keys", "set", "AT_OTHER"])
        self.assertIn("your own terminal", str(e.exception))

    def test_from_env_copies_this_shells_value(self):
        os.environ["AT_OTHER"] = "copied"
        with quiet():
            cli.main(["keys", "set", "AT_OTHER", "--from-env"])
        self.assertEqual(keys.read()["AT_OTHER"], "copied")

    def test_quoted_values_and_comments(self):
        keys.path().parent.mkdir(parents=True, exist_ok=True)
        keys.path().write_text("# note\nexport AT_TEST_KEY='quoted'\nbad line\n")
        self.assertEqual(keys.read(), {"AT_TEST_KEY": "quoted"})


class FakeOllama:
    def __init__(self, models):
        names = models

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"models": [{"name": n} for n in names]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class ReadinessTests(unittest.TestCase):
    def test_a_bare_folder_lists_every_fix(self):
        root = Path(tempfile.mkdtemp())
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tempfile.mkdtemp()}):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            checks = {c.name: c for c in readiness.check(root)}
        self.assertFalse(checks["git repository"].ok)
        self.assertIn("git init", checks["git repository"].fix)
        self.assertFalse(checks["team file"].ok)
        self.assertIn(f"gh repo create {root.name} --private", checks["GitHub repo"].fix)
        self.assertIn("agent-team keys set ANTHROPIC_API_KEY", checks["key ANTHROPIC_API_KEY"].fix)

    def test_a_test_command_that_cannot_run(self):
        c = {c.name: c for c in readiness.check(project(test_command="no-such-runner-xyz test"))}["test command"]
        self.assertFalse(c.ok)
        self.assertIn("no-such-runner-xyz isn't on the PATH", c.detail)

    def test_a_remote_ollama_and_its_models(self):
        server = FakeOllama(["qwen3.8:27b-mlx"])
        try:
            root = project()
            text = (root / ".team.toml").read_text().replace(
                '[providers.fake]\nkind = "fake"', f'[providers.fake]\nkind = "fake"\n\n[providers.local]\nkind = "ollama"\nurl = "{server.url}"')
            (root / ".team.toml").write_text(text + '\n[[agents]]\nname = "Q"\nrole = "builder"\nprovider = "local"\nmodel = "qwen3.8:27b-mlx"\n'
                                             '\n[[agents]]\nname = "R"\nrole = "builder"\nprovider = "local"\nmodel = "missing:7b"\n')
            checks = {c.name: c for c in readiness.check(root)}
        finally:
            server.close()
        self.assertTrue(checks[f"Ollama at {server.url}"].ok)
        self.assertTrue(checks["model qwen3.8:27b-mlx"].ok)
        self.assertFalse(checks["model missing:7b"].ok)

    def test_an_unreachable_remote_ollama_says_how_to_open_it(self):
        with mock.patch.object(readiness, "ollama_models", return_value=None):
            checks = {c.name: c for c in readiness.check(Path(tempfile.mkdtemp()), "http://192.0.2.1:11434")}
        c = checks["Ollama at http://192.0.2.1:11434"]
        self.assertFalse(c.ok)
        self.assertIn("OLLAMA_HOST=0.0.0.0", c.fix)

    def test_ready_never_fails_unless_strict(self):
        root = tempfile.mkdtemp()
        with quiet():
            self.assertEqual(cli.main(["ready", "-C", root]), 0)
            self.assertEqual(cli.main(["ready", "-C", root, "--strict"]), 1)


class InitTests(unittest.TestCase):
    def test_node_runners_and_the_test_folder(self):
        cases = {"node --test": "(?:#|ℹ) tests", "vitest run": "passed", "mocha": "passing", "jest --ci": "total"}
        for script, expect in cases.items():
            root = Path(tempfile.mkdtemp())
            (root / "package.json").write_text(json.dumps({"scripts": {"test": script}}))
            self.assertIn(expect, init.detect(root)[1], script)
        root = Path(tempfile.mkdtemp())
        (root / "test").mkdir()
        self.assertEqual(init.test_dir(root), "test/")
        self.assertEqual(init.test_dir(Path(tempfile.mkdtemp())), "tests/")

    def test_the_builder_model_comes_from_the_server(self):
        self.assertEqual(init.choose_model(["qwen3-embedding:4b", "llama3:8b", "qwen3-coder:30b"])[0], "qwen3-coder:30b")
        model, note = init.choose_model(["llama3:8b"], "qwen3.8:27b")
        self.assertEqual(model, "qwen3.8:27b")
        self.assertIn("isn't pulled", note)
        self.assertIn("couldn't list", init.choose_model(None)[1])

    def test_init_writes_the_remote_ollama_and_the_chosen_model(self):
        server = FakeOllama(["qwen3-embedding:4b", "qwen3.8:27b-mlx"])
        root = Path(tempfile.mkdtemp())
        (root / "test").mkdir()
        (root / "package.json").write_text(json.dumps({"scripts": {"test": "node --test"}}))
        try:
            with quiet():
                cli.main(["init", "-C", str(root), "--ollama-url", server.url])
        finally:
            server.close()
        text = (root / ".team.toml").read_text()
        self.assertIn(f'url = "{server.url}"', text)
        self.assertIn('model = "qwen3.8:27b-mlx"', text)
        self.assertIn('# owns = ["test/"]', text)
        self.assertIn(".team.toml.bak", (root / ".gitignore").read_text())
        from agent_team import config
        self.assertEqual(config.load(root).project.test_count_pattern, "(?:#|ℹ) tests (\\d+)")


class SecondRunFixes(unittest.TestCase):
    def test_ready_checks_the_given_ollama_even_with_a_team(self):
        root = project()
        with mock.patch.object(readiness, "ollama_models", return_value=["m:1"]) as models:
            names = [c.name for c in readiness.check(root, "http://10.37.129.2:11434")]
        self.assertIn("Ollama at http://10.37.129.2:11434", names)
        models.assert_any_call("http://10.37.129.2:11434")

    def test_init_accepts_the_kind_and_writes_a_valid_file(self):
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(readiness, "ollama_models", return_value=["qwen3.8:27b-mlx"]), quiet():
            cli.main(["init", "-C", str(root), "--builder-provider", "ollama", "--ollama-url", "http://10.37.129.2:11434"])
        from agent_team import config
        team = config.load(root)
        self.assertEqual(team.get("Forge").provider, "local")
        self.assertEqual(team.providers["local"].url, "http://10.37.129.2:11434")

    def test_node_pattern_matches_timestamped_ci_lines(self):
        import re
        root = Path(tempfile.mkdtemp())
        (root / "package.json").write_text(json.dumps({"scripts": {"test": "node --test"}}))
        rx = re.compile(init.detect(root)[1])
        self.assertEqual(rx.search("2026-10-15T10:00:01.123Z # tests 3").group(1), "3")
        self.assertEqual(rx.search("ℹ tests 12").group(1), "12")

    def test_a_missing_git_identity_is_reported(self):
        root = Path(tempfile.mkdtemp())
        env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "HOME": tempfile.mkdtemp()}
        with mock.patch.dict(os.environ, env):
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            checks = {c.name: c for c in readiness.check(root)}
        self.assertFalse(checks["git identity"].ok)
        self.assertIn("git config --global user.name", checks["git identity"].fix)

    def test_the_dashboard_knows_the_installed_version(self):
        from agent_team.dashboard.server import team_info
        info = team_info(load(project()))
        self.assertIn("installed_version", info)


if __name__ == "__main__":
    unittest.main()
