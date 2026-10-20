"""What the walkthrough dry run found: CI for a new project, test counts in any common format,
connecting an existing repository, QA's rule about documents, and web apps that live in a package."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import project, quiet

from agent_team import apprun, ci, github, readiness, setup_wizard


def git_repo(root: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "start", "--allow-empty"], capture_output=True)
    return root


class CiTests(unittest.TestCase):
    def test_a_project_without_a_workflow_gets_one_committed(self):
        root = git_repo(Path(tempfile.mkdtemp()))
        self.assertEqual(ci.setup(root), [ci.WORKFLOW, ci.SCRIPT])
        self.assertIn("python3 .github/agent-team-tests.py", (root / ci.WORKFLOW).read_text())
        log = subprocess.run(["git", "-C", str(root), "log", "--oneline", "--", ci.WORKFLOW], capture_output=True, text=True).stdout
        self.assertIn("CI: run the tests", log)
        self.assertEqual(ci.setup(root), [])   # never twice

    def test_a_project_with_its_own_workflow_is_left_alone(self):
        root = Path(tempfile.mkdtemp())
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "build.yml").write_text("name: mine\n")
        self.assertEqual(ci.write(root), [])
        self.assertFalse((root / ci.SCRIPT).exists())

    def run_script(self, root: Path) -> subprocess.CompletedProcess:
        ci.write(root)
        return subprocess.run([sys.executable, ci.SCRIPT], cwd=root, capture_output=True, text=True, timeout=300)

    def test_the_script_passes_before_there_are_tests(self):
        r = self.run_script(Path(tempfile.mkdtemp()))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "No tests yet: nothing to run."))

    def test_the_script_runs_the_configured_command(self):
        root = Path(tempfile.mkdtemp())
        (root / ".team.toml").write_text('[project]\ntest_command = "echo 7 passed; exit 3"\n')
        r = self.run_script(root)
        self.assertEqual(r.returncode, 3)
        self.assertIn("7 passed", r.stdout)

    def test_the_script_finds_python_tests_and_runs_them_in_a_venv(self):
        root = Path(tempfile.mkdtemp())
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("")
        (root / "tests" / "test_ok.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n")
        r = self.run_script(root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(".venv/bin/python -m unittest discover", r.stdout)
        self.assertIn("Ran 1 test", r.stderr)

    def test_the_ready_check_names_missing_ci_on_github(self):
        root = git_repo(project())
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/lakeba/chairtime.git"], capture_output=True)
        check = next(c for c in readiness.check(root) if c.name == "CI")
        self.assertFalse(check.ok)
        self.assertIn("agent-team ci setup", check.fix)
        ci.write(root)
        self.assertTrue(next(c for c in readiness.check(root) if c.name == "CI").ok)


class CountTests(unittest.TestCase):
    def test_the_projects_pattern_then_the_usual_formats(self):
        log = "tests\tRun the tests\t2026-10-20T03:31:31Z 98 passed in 5.38s\ntests\tRun the tests\tdone"
        self.assertEqual(github.counts_in(log, r"Ran (\d+) tests?"), ({"tests": "98"}, "pytest"))
        self.assertEqual(github.counts_in("build\tstep\tRan 12 tests in 0.1s", r"Ran (\d+) tests?"),
                         ({"build": "12"}, "the project's pattern"))
        self.assertEqual(github.counts_in("web\tstep\tTests:       31 passed, 31 total", "")[0], {"web": "31"})
        self.assertEqual(github.counts_in("nothing here", ""), ({}, ""))

    def test_the_report_says_which_format_was_read(self):
        with mock.patch.object(github, "run_for_commit", return_value={"databaseId": 1}), \
                mock.patch.object(github, "gh", return_value="tests\tRun\t98 passed in 1s"):
            self.assertEqual(github.ci_test_counts("o/r", "abc", r"Ran (\d+) tests?"), "tests: 98 (read as pytest output)")


class ExistingRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.root = git_repo(Path(tempfile.mkdtemp()))
        self.calls = []

    def fake_run(self, results):
        def run(argv, cwd=None, timeout=60, stdin=None):
            self.calls.append(argv)
            if argv[:2] == ["git", "remote"]:   # the remote itself is real, so leftovers would show
                subprocess.run(argv, cwd=cwd, capture_output=True)
            for prefix, result in results.items():
                if tuple(argv[:len(prefix)]) == prefix:
                    return result
            return 0, ""
        return run

    def connect(self, name, results=None):
        with mock.patch.object(setup_wizard, "github_status", return_value={"installed": True, "signed_in": True, "user": "lakeba"}), \
                mock.patch.object(setup_wizard, "_run", self.fake_run(results or {})):
            return setup_wizard.create_repo(self.root, existing=name)

    def test_an_empty_repository_is_connected_with_ci(self):
        out = self.connect("https://github.com/lakeba/chairtime.git")
        self.assertEqual(out, {"repo": "lakeba/chairtime", "created": False})
        self.assertIn(["git", "remote", "add", "origin", "https://github.com/lakeba/chairtime.git"], self.calls)
        self.assertIn(["git", "push", "-q", "-u", "origin", "HEAD"], self.calls)
        self.assertFalse(any(c[:3] == ["gh", "repo", "create"] for c in self.calls))
        self.assertTrue((self.root / ci.WORKFLOW).is_file())   # committed before the first push

    def test_bad_names_and_unreachable_or_full_repositories(self):
        with self.assertRaises(setup_wizard.SetupError):
            self.connect("not a repo")
        with self.assertRaises(setup_wizard.SetupError) as e:
            self.connect("lakeba/nope", {("gh", "repo", "view"): (1, "Could not resolve to a Repository")})
        self.assertIn("isn't a repository you can reach", str(e.exception))
        with self.assertRaises(setup_wizard.SetupError) as e:
            self.connect("lakeba/full", {("git", "push"): (1, "! [rejected] main -> main (fetch first)")})
        self.assertIn("use an empty one", str(e.exception))
        remotes = subprocess.run(["git", "-C", str(self.root), "remote"], capture_output=True, text=True).stdout
        self.assertEqual(remotes.strip(), "")   # nothing half-connected


class QaAndPromptTests(unittest.TestCase):
    def test_qa_never_tests_document_wording(self):
        text = (Path(setup_wizard.__file__).parent / "prompts" / "qa.md").read_text()
        self.assertIn("Never\ntest the wording of the changelog", text)

    def test_members_are_told_how_tests_will_run_without_touching_files(self):
        from agent_team import agent, config
        helpers.reset()
        root = project(files={"requirements.txt": "flask\n", "tests/test_x.py": "def test_x():\n    assert True\n"})
        before = (root / ".gitignore").read_text() if (root / ".gitignore").exists() else ""
        team = config.load(root)
        team.project.test_command = ""
        self.assertIn(".venv/bin/python", agent._test_command(team))
        after = (root / ".gitignore").read_text() if (root / ".gitignore").exists() else ""
        self.assertEqual(before, after)


class WebPackageTests(unittest.TestCase):
    def test_a_flask_factory_in_a_package(self):
        root = Path(tempfile.mkdtemp())
        (root / "chairtime").mkdir()
        (root / "chairtime" / "__init__.py").write_text("from flask import Flask\n\ndef create_app():\n    return Flask(__name__)\n")
        (root / "requirements.txt").write_text("flask\n")
        how = apprun.detect(root)
        self.assertEqual(how["kind"], "web")
        self.assertTrue(how["command"].startswith("python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt && "))
        self.assertTrue(how["command"].endswith(".venv/bin/python -m flask --app chairtime run"))
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".venv" / "bin" / "python").write_text("")
        self.assertNotIn("pip install", apprun.detect(root)["command"])   # its environment exists: just run it

    def test_a_fastapi_app_in_a_package(self):
        root = Path(tempfile.mkdtemp())
        (root / "shop").mkdir()
        (root / "shop" / "__init__.py").write_text("")
        (root / "shop" / "main.py").write_text("from fastapi import FastAPI\n\napp = FastAPI()\n")
        how = apprun.detect(root)
        self.assertTrue(how["command"].endswith("-m uvicorn shop.main:app"), how)
        self.assertEqual(how["why"], "the FastAPI app in shop/main.py")

    def test_tests_and_tools_folders_are_not_apps(self):
        root = Path(tempfile.mkdtemp())
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
        self.assertNotEqual(apprun.detect(root).get("why", ""), "the Flask app in tests/")


if __name__ == "__main__":
    unittest.main()
