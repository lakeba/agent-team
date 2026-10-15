import json
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
