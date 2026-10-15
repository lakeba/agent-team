import unittest

from agent_team import agent
from agent_team.workflows import build, discuss

import helpers
from helpers import SCRIPTS, CALLS, load, project, quiet


class AgentTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_prompt_is_filled_with_team_facts(self):
        team = load(project())
        a = agent.make(team, team.get("Forge"), "builder", file_format="FMT")
        self.assertIn("You are Forge", a.system)
        self.assertIn("Never delete user data", a.system)
        self.assertIn("- Spark (marketing", a.system)          # the roster lists every member
        self.assertIn("FMT", a.system)

    def test_custom_prompt_file_overrides_the_role_prompt(self):
        root = project(files={"prompts/quill.md": "I am {name}, checking {project}."})
        text = (root / ".team.toml").read_text().replace(
            'description = "Security', 'prompt = "prompts/quill.md"\ndescription = "Security')
        (root / ".team.toml").write_text(text)
        team = load(root)
        self.assertEqual(agent.make(team, team.get("Quill")).system, "I am Quill, checking demo.")

    def test_text_only_providers_get_images_flattened(self):
        team = load(project())
        a = agent.make(team, team.get("Forge"), "builder")
        SCRIPTS["Forge"].append("ok")
        with quiet():
            a.turn([{"type": "text", "text": "look"}, {"type": "image", "source": {}}])
        self.assertIn("[image omitted", CALLS[-1]["messages"][0]["content"])
        self.assertEqual([m["role"] for m in a.messages], ["user", "assistant"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_plan_build_review_until_approved(self):
        root = project(test_command="test -f hello.py", files={"README.md": "demo\n"})
        SCRIPTS["Atlas"].extend([
            '<file path="PLAN.md">\n# Plan\nAdd hello.py\n</file>',
            "Missing a newline.\nVERDICT: CHANGES",
            "All good.\nVERDICT: APPROVED",
        ])
        SCRIPTS["Forge"].extend([
            '<file path="hello.py">\nprint("hi")</file>\nDone.',
            '<file path="hello.py">\nprint("hi")\n</file>\nFixed.',
        ])
        with quiet():
            ok = build.run(load(root), "add hello.py", rounds=3)
        self.assertTrue(ok)
        self.assertEqual((root / "hello.py").read_text(), 'print("hi")\n')
        self.assertTrue((root / "PLAN.md").exists())
        self.assertTrue((root / ".team/logs/build.md").exists())
        # the builder's second turn carried the lead's review and the test output
        second = [c for c in CALLS if "Forge" in c["label"]][1]["messages"][-1]["content"]
        self.assertIn("Missing a newline", second)
        self.assertIn("exit code 0", second)

    def test_plan_sent_as_plain_text_is_saved(self):
        root = project()
        SCRIPTS["Atlas"].extend(["# Plan\nJust do it.", "VERDICT: APPROVED"])
        SCRIPTS["Forge"].append("Nothing to change.")
        with quiet():
            build.run(load(root), "noop", rounds=1)
        self.assertIn("Just do it.", (root / "PLAN.md").read_text())

    def test_lead_cannot_write_project_files(self):
        root = project()
        SCRIPTS["Atlas"].extend(['<file path="PLAN.md">\nplan\n</file>\n<file path="evil.py">\nx\n</file>',
                                 "VERDICT: APPROVED"])
        SCRIPTS["Forge"].append("ok")
        with quiet():
            build.run(load(root), "t", rounds=1)
        self.assertFalse((root / "evil.py").exists())


class DiscussTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_three_members_agree_and_lead_writes_roadmap(self):
        root = project()
        SCRIPTS["Atlas"].extend(["Draft: M1.\nSTATUS: CONTINUE", "Fine.\nSTATUS: AGREE",
                                 '<file path="ROADMAP.md">\n# Roadmap\nM1\n</file>'])
        SCRIPTS["Forge"].extend(["Cheaper: M1 only.\nSTATUS: AGREE", "Still agree.\nSTATUS: AGREE"])
        SCRIPTS["Quill"].extend(["Add a security note.\nSTATUS: AGREE", "Agree.\nSTATUS: AGREE"])
        with quiet():
            agreed = discuss.run(load(root), "next features", ["Atlas", "Forge", "Quill"], turns=9)
        self.assertTrue(agreed)
        self.assertEqual((root / "ROADMAP.md").read_text(), "# Roadmap\nM1\n")
        # Quill heard both earlier speakers before its first turn
        quill_first = [c for c in CALLS if "Quill" in c["label"]][0]["messages"][-1]["content"]
        self.assertIn("Atlas says", quill_first)
        self.assertIn("Forge says", quill_first)

    def test_an_objection_resets_agreement(self):
        root = project()
        SCRIPTS["Atlas"].extend(["A\nSTATUS: AGREE", "C\nSTATUS: AGREE", '<file path="ROADMAP.md">\nx\n</file>'])
        SCRIPTS["Forge"].extend(["B\nSTATUS: CONTINUE", "D\nSTATUS: AGREE"])
        with quiet():
            agreed = discuss.run(load(root), "t", ["Atlas", "Forge"], turns=4)
        self.assertTrue(agreed)
        self.assertEqual(len([c for c in CALLS if "Atlas" in c["label"]]), 3)  # 2 turns + final roadmap

    def test_final_roadmap_may_only_touch_roadmap(self):
        root = project()
        SCRIPTS["Atlas"].extend(["A\nSTATUS: AGREE", '<file path="ROADMAP.md">\nok\n</file><file path="x.py">\nno\n</file>'])
        SCRIPTS["Forge"].append("B\nSTATUS: AGREE")
        with quiet():
            discuss.run(load(root), "t", ["Atlas", "Forge"], turns=2)
        self.assertFalse((root / "x.py").exists())


if __name__ == "__main__":
    unittest.main()


class DiscussFeedbackTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_the_devops_digest_reaches_the_discussion(self):
        root = project(files={".team/FEEDBACK.md": "# Digest\n- Users want CSV export.\n"})
        SCRIPTS["Atlas"].extend(["Export first.\nSTATUS: AGREE", '<file path="ROADMAP.md">\n# Roadmap\n</file>'])
        SCRIPTS["Forge"].append("Fine.\nSTATUS: AGREE")
        with quiet():
            discuss.run(load(root), "next features", turns=2)
        system = CALLS[0]["system"]
        self.assertIn("<untrusted>\n# Digest\n- Users want CSV export.", system)

    def test_no_digest_yet(self):
        team = load(project())
        self.assertIn("No digest yet", discuss.feedback_digest(team))
