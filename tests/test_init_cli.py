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

    def test_ollama_url_updates_an_existing_team(self):
        root = Path(tempfile.mkdtemp())
        with quiet():
            init.run(root)                                   # first run: Ollama on this machine
            (root / ".team.toml").write_text((root / ".team.toml").read_text() + "\n# my note\n")
            init.run(root, ollama_url="http://10.37.129.2:11434/")
        text = (root / ".team.toml").read_text()
        self.assertEqual(config.load(root).providers["local"].url, "http://10.37.129.2:11434")
        self.assertIn("# my note", text)                      # the rest of the file is kept
        self.assertIn('# url = "http://gpu-box.local:11434"', text)   # commented examples untouched

    def test_ollama_url_leaves_remote_connections_alone(self):
        root = Path(tempfile.mkdtemp())
        (root / ".team.toml").write_text(
            '[project]\nname = "x"\n\n[providers.local]\nkind = "ollama"\n\n'
            '[providers.gpu]\nkind = "ollama"\nurl = "http://gpu.local:11434"\n\n'
            '[[agents]]\nname = "Forge"\nrole = "builder"\nprovider = "local"\nmodel = "m"\n')
        with quiet():
            init.run(root, ollama_url="http://10.0.0.5:11434")
        providers = config.load(root).providers
        self.assertEqual(providers["local"].url, "http://10.0.0.5:11434")   # had no url: one is added
        self.assertEqual(providers["gpu"].url, "http://gpu.local:11434")

    def test_python_test_command_follows_the_runner_the_project_uses(self):
        root = Path(tempfile.mkdtemp())
        (root / "pyproject.toml").write_text('[project]\nname = "x"\n')
        (root / "tests").mkdir()
        (root / "tests/test_a.py").write_text("import unittest\n")
        cmd, pattern = init.detect(root)
        self.assertEqual(cmd, "python3 -m unittest discover -s tests -v")
        self.assertEqual(re.search(pattern, "Ran 3 tests in 0.01s").group(1), "3")
        (root / "pyproject.toml").write_text('[project]\nname = "x"\n\n[tool.pytest.ini_options]\n')
        self.assertEqual(init.detect(root)[0], "python3 -m pytest -q")
        (root / "pyproject.toml").write_text('[project]\nname = "x"\n')
        (root / "tests/test_a.py").write_text("import pytest\n")
        self.assertEqual(init.detect(root)[0], "python3 -m pytest -q")

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
