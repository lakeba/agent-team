"""The first-run wizard, the plain-language run story, Run my app and My MVP."""
import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import helpers
from helpers import load, project, quiet

from agent_team import apprun, mvp, progress, projects, setup_wizard
from agent_team.dashboard import server as dash


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


class CreateProjectTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {setup_wizard.HOME_ENV: str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_creates_a_working_project(self):
        with quiet():
            made = setup_wizard.create_project({"name": "Study Buddy", "owner": "Ada", "models": "claude",
                                                "extras": ["qa"], "per_day": 5,
                                                "vision": "A web app for students to plan their study week, with exams and breaks."})
        root = Path(made["root"])
        self.assertEqual(root, (self.home / "study-buddy").resolve())
        self.assertIn("plan their study week", (root / "VISION.md").read_text())
        self.assertTrue((root / "README.md").read_text().startswith("# Study Buddy"))
        team = load(root)
        self.assertEqual(team.project.name, "Study Buddy")
        self.assertEqual(team.project.library, ["builtin"])
        self.assertEqual(team.limits.per_day, 5.0)
        self.assertIn("qa", {a.role for a in team.agents.values()})
        log = subprocess.run(["git", "-C", str(root), "log", "--oneline"], capture_output=True, text=True).stdout
        self.assertIn("Start Study Buddy", log)
        self.assertIn(str(root), projects.registered())

    def test_refuses_bad_input_and_busy_folders(self):
        with self.assertRaises(setup_wizard.SetupError):
            setup_wizard.create_project({"name": "", "vision": "x" * 40})
        with self.assertRaises(setup_wizard.SetupError):
            setup_wizard.create_project({"name": "A", "vision": "x" * 40, "models": "gpt"})
        (self.home / "taken").mkdir(parents=True)
        (self.home / "taken" / "file.txt").write_text("mine")
        with self.assertRaises(setup_wizard.SetupError):
            setup_wizard.create_project({"name": "Taken", "vision": "x" * 40, "models": "claude"})
        self.assertEqual((self.home / "taken" / "file.txt").read_text(), "mine")

    def test_sets_up_a_folder_with_code_without_touching_it(self):
        root = self.home / "formApp"
        (root / "src").mkdir(parents=True)
        (root / "formApp.csproj").write_text("<Project/>")
        (root / "src" / "Program.cs").write_text("// mine\n")
        (root / "VISION.md").write_text("# Vision\n\nForms for clinics.\n")
        info = setup_wizard.folder_info(root)
        self.assertTrue(info["usable"] and info["has_files"])
        self.assertEqual(info["language"], "dotnet")
        self.assertIn("Forms for clinics", info["vision"])
        with quiet():
            made = setup_wizard.create_project({"name": "Form App", "vision": "Forms for clinics.", "models": "claude",
                                                "folder": str(root), "existing": True})
        self.assertEqual(Path(made["root"]), root.resolve())
        self.assertEqual((root / "src" / "Program.cs").read_text(), "// mine\n")
        self.assertFalse((root / "README.md").exists() and "Form App" not in (root / "README.md").read_text())
        tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout.split()
        self.assertIn(".team.toml", tracked)
        self.assertNotIn("src/Program.cs", tracked)          # the owner's code isn't committed for them
        self.assertNotIn("VISION.md", tracked)               # unchanged, so not ours to commit
        self.assertEqual(load(root).project.name, "Form App")
        self.assertFalse(setup_wizard.folder_info(root)["usable"])   # it has a team now

    def test_home_folder_is_never_offered(self):
        self.assertFalse(setup_wizard.folder_info(Path.home())["usable"])
        with self.assertRaises(setup_wizard.SetupError):
            setup_wizard.create_project({"name": "X", "vision": "x" * 40, "models": "claude",
                                         "folder": str(Path.home()), "existing": True})

    def test_slug(self):
        self.assertEqual(setup_wizard.slug("Tip Splitter!"), "tip-splitter")
        self.assertEqual(setup_wizard.slug("???"), "my-idea")


class ReadyAndKeysTest(unittest.TestCase):
    def test_ready_lists_each_check_once_and_marks_github_optional(self):
        root = project()
        checks = setup_wizard.ready(root)
        names = [c["name"] for c in checks]
        self.assertEqual(len(names), len(set(names)))
        github = [c for c in checks if c["name"].startswith("GitHub") and not c["ok"]]
        self.assertTrue(all(c["optional"] and c["action"] == "github" for c in github))

    def test_key_is_saved_and_never_returned(self):
        from agent_team import keys
        with mock.patch("agent_team.providers.build") as build:
            build.return_value.check.return_value = "ok (claude)"
            out = setup_wizard.save_key("sk-ant-" + "a" * 40)
        self.assertEqual(out, {"saved": True, "ok": True, "status": "ok (claude)"})
        self.assertEqual(keys.read()["ANTHROPIC_API_KEY"], "sk-ant-" + "a" * 40)
        with self.assertRaises(setup_wizard.SetupError):
            setup_wizard.save_key("not a key")
        os.environ.pop("ANTHROPIC_API_KEY", None)
        keys.remove("ANTHROPIC_API_KEY")

    def test_tasks_from_the_lead(self):
        helpers.reset()
        root = project(files={"VISION.md": "# Vision\n\nA tip calculator."})
        helpers.SCRIPTS["Atlas"].append("TASK: Split a bill evenly\n- TASK: Add a tip\nnoise")
        with quiet():
            self.assertEqual(setup_wizard.suggest_tasks(root), ["Split a bill evenly", "Add a tip"])


class StoryTest(unittest.TestCase):
    def test_build_output_in_plain_words(self):
        text = "\n".join(["--- Atlas · lead (m) is writing...", "VERDICT: APPROVED",
                          "=========== Round 1/3 ===========", "--- Forge · builder (m) is writing...",
                          "Ran 4 tests in 0.01s", "OK", "## Check `ruff check .`: FAILED (exit code 1)",
                          "--- Atlas · lead (m) is writing...", "VERDICT: CHANGES",
                          "=========== Round 2/3 ===========", "--- Forge · builder (m) is writing...",
                          "  ! held back .github/workflows/ci.yml: sensitive", "--- Atlas · lead (m) is writing...",
                          "VERDICT: APPROVED", "Atlas approved after 2 round(s)."])
        lines = [s["text"] for s in progress.story(text)]
        self.assertEqual(lines[0], "Atlas is writing the plan")       # the plan's own VERDICT isn't counted
        self.assertNotIn("Atlas approved it", lines[:2])
        self.assertIn("Tests: all passed", lines)
        self.assertIn("Check ruff check .: failed", lines)
        self.assertIn("Atlas asked for changes", lines)
        self.assertIn("A change to .github/workflows/ci.yml waits for the builder to explain it first", lines)
        self.assertEqual(lines[-1], "Done: Atlas approved the work after 2 rounds")


class AppRunTest(unittest.TestCase):
    def folder(self, files):
        root = Path(tempfile.mkdtemp())
        for rel, body in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(body)
        return root

    def test_detect(self):
        self.assertEqual(apprun.detect(self.folder({"package.json": '{"scripts": {"dev": "vite"}}'}))["command"],
                         "npm install && npm run dev")
        self.assertIn("flask --app app run", apprun.detect(self.folder({"app.py": "app = Flask(__name__)"}))["command"])
        cli = apprun.detect(self.folder({"pyproject.toml": "", "src/tipcalc/__init__.py": "", "src/tipcalc/__main__.py": ""}))
        self.assertEqual(cli["kind"], "cli")
        self.assertIn("-m tipcalc", cli["command"])
        self.assertEqual(apprun.detect(self.folder({"index.html": "<p>hi</p>"}))["kind"], "static")
        pkg = apprun.detect(self.folder({"src/__init__.py": "", "src/cli.py": "if __name__ == '__main__':\n    pass\n"}))
        self.assertTrue(pkg["command"].endswith("-m src.cli"))
        script = apprun.detect(self.folder({"tool.py": "if __name__ == \"__main__\":\n    pass\n", "test_tool.py": ""}))
        self.assertTrue(script["command"].endswith("tool.py"))
        self.assertEqual(apprun.detect(self.folder({}))["kind"], "none")
        self.assertEqual(apprun.detect(self.folder({}), "make run")["command"], "make run")

    def test_cli_runs_with_arguments(self):
        root = self.folder({"pyproject.toml": "", "src/hello/__init__.py": "",
                            "src/hello/__main__.py": "import sys\nprint('hi', *sys.argv[1:])\n"})
        out = apprun.run_cli(root, "there 'my friend'")
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(out["output"].strip(), "hi there my friend")

    def test_static_site_starts_and_stops(self):
        root = self.folder({"index.html": "<p>hi</p>"})
        s = apprun.start(root)
        try:
            self.assertTrue(s["running"])
            self.assertTrue(s["url"].startswith("http://127.0.0.1:"))
        finally:
            self.assertFalse(apprun.stop(root)["running"])


class MvpTest(unittest.TestCase):
    def test_summary_and_keeping_a_version(self):
        root = project(files={"VISION.md": "# Vision\n\nSplit bills.", "ROADMAP.md": "- Add tips\n- Share links\n"})
        git(root, "init", "-q")
        git(root, "-c", "user.email=a@b", "-c", "user.name=a", "add", "-A")
        git(root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "start")
        git(root, "config", "user.email", "a@b")
        git(root, "config", "user.name", "a")
        (root / "app.py").write_text("print(1)\n")
        team = load(root)
        s = mvp.summary(team)
        self.assertEqual(s["vision"], "Split bills.")
        self.assertEqual(s["changed"], ["app.py"])
        self.assertEqual(s["roadmap"], ["Add tips", "Share links"])
        out = mvp.keep_version(team, "First calculator")
        self.assertTrue(out["kept"])
        self.assertEqual(mvp.changed(root), [])
        self.assertFalse(mvp.keep_version(team)["kept"])


class SetupModeServerTest(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.httpd.server_address[1]
        self.folder = Path(tempfile.mkdtemp())
        self.httpd.RequestHandlerClass = dash.make_handler(None, self.port, folder=self.folder)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method, path, body=None, token=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            headers.update({"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}",
                            "X-Agent-Team-Token": token or ""})
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_no_project_then_open_one(self):
        self.assertEqual(self.request("GET", "/api/team"), (200, {"setup": True}))
        self.assertEqual(self.request("GET", "/api/runs")[0], 409)
        with mock.patch("agent_team.readiness.find_ollama", return_value=[]):
            status, s = self.request("GET", "/api/setup/status")
        self.assertEqual(status, 200)
        self.assertIn("home", s)
        self.assertEqual(s["here"]["path"], str(self.folder.resolve()))
        self.assertTrue(s["here"]["usable"])
        token = self.request("GET", "/api/session")[1]["token"]
        self.assertEqual(self.request("POST", "/api/setup/open", {"root": "/nowhere"}, token)[0], 404)
        root = project()
        projects.register(root)
        self.assertEqual(self.request("POST", "/api/setup/open", {"root": str(root.resolve())}, token)[0], 200)
        self.assertEqual(self.request("GET", "/api/team")[1]["project"]["name"], "demo")
        self.assertEqual(self.request("POST", "/api/setup/key", {"value": "x"}, token="wrong")[0], 403)


if __name__ == "__main__":
    unittest.main()
