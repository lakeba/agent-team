"""The test command a project that started empty gets once the team writes tests."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_team.workflows.init import test_command_for


class TestCommandTests(unittest.TestCase):
    def test_the_configured_command_wins(self):
        self.assertEqual(test_command_for(Path(tempfile.mkdtemp()), "make test"), "make test")

    def test_an_empty_project_has_none_yet(self):
        self.assertEqual(test_command_for(Path(tempfile.mkdtemp()), ""), "")

    def test_python_tests_run_with_their_dependencies_in_a_venv(self):
        root = Path(tempfile.mkdtemp())
        (root / "tests").mkdir()
        (root / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n")
        (root / "requirements.txt").write_text("flask\npytest\n")
        (root / ".gitignore").write_text(".team/\n")
        cmd = test_command_for(root, "")
        self.assertTrue(cmd.startswith("test -x .venv/bin/python || python3 -m venv .venv; .venv/bin/python -m pip install -q -r requirements.txt && .venv/bin/python -m "), cmd)
        self.assertTrue(cmd.endswith("pytest -q"), cmd)
        self.assertIn(".venv/", (root / ".gitignore").read_text().splitlines())   # never committed
        test_command_for(root, "")
        self.assertEqual((root / ".gitignore").read_text().count(".venv/"), 1)

    def test_without_requirements_the_detected_command_is_kept(self):
        root = Path(tempfile.mkdtemp())
        (root / "tests").mkdir()
        (root / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n")
        (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        self.assertTrue(test_command_for(root, "").startswith("python3 -m "))

    def test_the_lead_runs_the_same_tests_as_the_build(self):
        from agent_team import review_tools
        src = Path(review_tools.__file__).read_text()
        self.assertIn("test_command_for(team.root, team.project.test_command)", src)


if __name__ == "__main__":
    unittest.main()
