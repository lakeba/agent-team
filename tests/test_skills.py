"""Skills: Markdown files or skill folders added to one member's prompt."""
import unittest
from pathlib import Path

from agent_team import agent, config_io
from agent_team.config import ConfigError
from agent_team.dashboard.server import team_info
from agent_team import skills

import helpers
from helpers import load, project

SKILL_MD = """---
name: owasp-checklist
description: What to look for in web code
---
Check every input for injection.
"""


def with_skills(entries: list[str], files: dict | None = None) -> Path:
    root = project(files=files)
    text = (root / ".team.toml").read_text()
    listed = ", ".join(f'"{e}"' for e in entries)
    text = text.replace('name = "Forge"\nrole = "builder"\nprovider = "fake"\nmodel = "m"',
                        f'name = "Forge"\nrole = "builder"\nprovider = "fake"\nmodel = "m"\nskills = [{listed}]')
    (root / ".team.toml").write_text(text)
    return root


class SkillTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_files_and_skill_folders_are_added_after_the_role_prompt(self):
        root = with_skills(["team/style.md", "team/owasp"],
                           {"team/style.md": "Use type hints.\n", "team/owasp/SKILL.md": SKILL_MD})
        team = load(root)
        system = agent.make(team, team.get("Forge"), "builder", file_format="FMT").system
        self.assertLess(system.index("You are Forge"), system.index("# Your skills"))
        self.assertIn("## Skill: style\n", system)
        self.assertIn("## Skill: owasp-checklist", system)
        self.assertIn("_What to look for in web code_", system)
        self.assertIn("Check every input for injection.", system)
        self.assertNotIn("name: owasp-checklist", system)            # front matter is not sent
        self.assertIn("Skills: style, owasp-checklist.", agent.team_roster(team))
        self.assertNotIn("# Your skills", agent.make(team, team.get("Atlas"), "lead").system)

    def test_home_folder_paths(self):
        home_skill = Path.home() / ".agent-team-test-skill.md"
        home_skill.write_text("Be brief.\n")
        try:
            team = load(with_skills(["~/.agent-team-test-skill.md"]))
            self.assertIn("Be brief.", agent.make(team, team.get("Forge"), "builder").system)
        finally:
            home_skill.unlink()

    def test_missing_skills_are_reported_not_silently_skipped(self):
        team = load(with_skills(["team/nope.md"]))
        with self.assertRaises(ConfigError):
            agent.make(team, team.get("Forge"), "builder")
        self.assertIn("not found", skills.problems(team)["Forge"])
        info = {m["name"]: m for m in team_info(team)["members"]}
        self.assertTrue(info["Forge"]["skills"][0]["missing"])
        self.assertIn("not found", info["Forge"]["skills_problem"])

    def test_oversized_skills_are_refused(self):
        team = load(with_skills(["big.md"], {"big.md": "x" * (skills.MAX_CHARS + 1)}))
        with self.assertRaises(ConfigError):
            skills.load(team, team.get("Forge"))

    def test_skills_must_be_a_list_of_paths(self):
        root = with_skills(["a.md"])
        (root / ".team.toml").write_text((root / ".team.toml").read_text().replace('skills = ["a.md"]', 'skills = "a.md"'))
        with self.assertRaises(ConfigError):
            load(root)

    def test_skills_round_trip_through_the_editor(self):
        root = with_skills(["team/style.md"], {"team/style.md": "x\n"})
        data = config_io.to_data(load(root))
        forge = next(a for a in data["agents"] if a["name"] == "Forge")
        self.assertEqual(forge["skills"], ["team/style.md"])
        forge["skills"] = ["team/style.md", "  ", ""]
        self.assertIn('skills = ["team/style.md"]', config_io.plan_change(root, data)["text"])


if __name__ == "__main__":
    unittest.main()
