import json
import re
import tempfile
import unittest
from pathlib import Path

from agent_team import cli, config
from agent_team.workflows import init

import helpers  # noqa: F401  (registers the fake provider)
from helpers import project, quiet


class InitTests(unittest.TestCase):
    def test_detects_npm_and_writes_a_loadable_config(self):
        root = Path(tempfile.mkdtemp())
        (root / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        with quiet():
            init.run(root)
        team = config.load(root)
        self.assertEqual(team.project.test_command, "npm test")
        self.assertEqual(sorted(a.role for a in team.agents.values()), ["builder", "devops", "lead", "marketing"])
        self.assertIn(".team/", (root / ".gitignore").read_text())

    def test_detects_unittest_layout(self):
        root = Path(tempfile.mkdtemp())
        (root / "test_x.py").write_text("")
        self.assertEqual(init.detect(root)[0], "python3 -m unittest -v")

    def test_detects_dotnet_solution_and_its_test_count(self):
        root = Path(tempfile.mkdtemp())
        (root / "App.slnx").write_text("<Solution />")
        (root / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))   # tooling only
        cmd, pattern = init.detect(root)
        self.assertEqual(cmd, "dotnet test")
        rx = re.compile(pattern)
        self.assertEqual(rx.search("2026-10-15T01:02:03Z Passed!  - Failed:     0, Passed:     3, Skipped:     0").group(1), "3")
        self.assertEqual(rx.search("Failed!  - Failed:     1, Passed:    12, Skipped:     0").group(1), "12")
        self.assertEqual(rx.search("  succeeded: 7").group(1), "7")

    def test_detects_a_nested_dotnet_project(self):
        root = Path(tempfile.mkdtemp())
        (root / "src/App").mkdir(parents=True)
        (root / "src/App/App.csproj").write_text("<Project />")
        self.assertEqual(init.detect(root)[0], "dotnet test")

    def test_dotnet_init_ignores_build_output_and_finds_the_test_project(self):
        root = Path(tempfile.mkdtemp())
        (root / "App.sln").write_text("")
        (root / "App.Tests").mkdir()
        with quiet():
            init.run(root)
        team = config.load(root)
        self.assertEqual(team.project.test_command, "dotnet test")
        self.assertIn('owns = ["App.Tests/"]', (root / ".team.toml").read_text())
        ignore = (root / ".gitignore").read_text().splitlines()
        self.assertIn("bin/", ignore)
        self.assertIn("obj/", ignore)

    def test_dotnet_gitignore_is_left_alone(self):
        root = Path(tempfile.mkdtemp())
        (root / "App.sln").write_text("")
        (root / ".gitignore").write_text("[Bb]in/\n[Oo]bj/\n")
        with quiet():
            init.run(root)
        self.assertNotIn("# .NET build output", (root / ".gitignore").read_text())

    def test_refuses_to_overwrite(self):
        root = Path(tempfile.mkdtemp())
        with quiet():
            init.run(root)
        with self.assertRaises(SystemExit):
            init.run(root)

    def test_keeps_existing_gitignore(self):
        root = Path(tempfile.mkdtemp())
        (root / ".gitignore").write_text("node_modules\n")
        with quiet():
            init.run(root)
        self.assertEqual((root / ".gitignore").read_text().splitlines()[0], "node_modules")


class CliTests(unittest.TestCase):
    def test_doctor_reports_each_agent(self):
        root = project()
        with quiet():
            code = cli.main(["doctor", "-C", str(root)])
        self.assertEqual(code, 0)

    def test_config_errors_are_friendly(self):
        root = Path(tempfile.mkdtemp())
        (root / ".team.toml").write_text("[project]\nname='x'\n")
        with self.assertRaisesRegex(SystemExit, "Config error: no \\[\\[agents\\]\\]"):
            cli.main(["agents", "-C", str(root)])


if __name__ == "__main__":
    unittest.main()
