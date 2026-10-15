"""The devops guardrails, tested without GitHub: merge gating and the release-PR check."""
import unittest

from agent_team.workflows.ship import is_changelog_rename, merge_blockers, _last_summary

import helpers  # noqa: F401
from helpers import load, project

SHA, OLD = "a" * 40, "b" * 40


class MergeRuleTests(unittest.TestCase):
    def setUp(self):
        self.team = load(project())

    def blockers(self, paths, green=True, approvals=None, signoffs=None):
        return merge_blockers(self.team, 7, SHA, paths, green, "summary", approvals or {}, signoffs or {})

    def test_red_ci_blocks(self):
        self.assertIn("CI is not all green", self.blockers(["app.py"], green=False, approvals={7: SHA}))

    def test_lead_approval_must_match_the_head_commit(self):
        self.assertIn("lead has not approved", self.blockers(["app.py"]))
        self.assertIn("lead has not approved", self.blockers(["app.py"], approvals={7: OLD}))
        self.assertEqual(self.blockers(["app.py"], approvals={7: SHA}), "")

    def test_every_owner_must_sign_the_same_commit(self):
        paths = ["site/index.html", "ROADMAP.md"]            # owned by Spark and Atlas
        self.assertIn("Atlas, Spark", self.blockers(paths, approvals={7: SHA}))
        partial = {(7, "Spark"): SHA, (7, "Atlas"): OLD}
        self.assertIn("Atlas", self.blockers(paths, approvals={7: SHA}, signoffs=partial))
        full = {(7, "Spark"): SHA, (7, "Atlas"): SHA}
        self.assertEqual(self.blockers(paths, approvals={7: SHA}, signoffs=full), "")

    def test_signoff_for_another_pr_does_not_count(self):
        self.assertIn("Spark", self.blockers(["BRIEF.md"], approvals={7: SHA}, signoffs={(8, "Spark"): SHA}))


class ReleasePrTests(unittest.TestCase):
    def test_exact_rename_passes(self):
        self.assertTrue(is_changelog_rename(["-## [Unreleased]", "+## [1.2.0] - 2026-10-15"], ["CHANGELOG.md"], "1.2.0"))

    def test_anything_else_fails(self):
        cases = [
            (["-## [Unreleased]", "+## [1.2.1] - 2026-10-15"], ["CHANGELOG.md"]),            # wrong version
            (["-## [Unreleased]", "+## [1.2.0] - soon"], ["CHANGELOG.md"]),                  # no date
            (["-## [Unreleased]", "+## [1.2.0] - 2026-10-15", "+extra"], ["CHANGELOG.md"]),  # extra line
            (["-## [Unreleased]", "+## [1.2.0] - 2026-10-15"], ["CHANGELOG.md", "app.py"]),  # extra file
        ]
        for lines, paths in cases:
            self.assertFalse(is_changelog_rename(lines, paths, "1.2.0"), (lines, paths))


class HandoverTests(unittest.TestCase):
    def test_last_summary_is_found(self):
        root = project()
        log = root / "ship.md"
        log.write_text("\n# Ops shift\n\n## Harbor: shift summary\n\nold\n\n# Ops shift\n\n## Harbor: action\n\nx\n"
                       "\n## Harbor: shift summary\n\nnew notes\n\n# Ops shift\n")
        self.assertEqual(_last_summary(log), "new notes")
        self.assertEqual(_last_summary(root / "missing.md"), "")


if __name__ == "__main__":
    unittest.main()


class LabelTests(unittest.TestCase):
    def test_missing_labels_are_created_before_use(self):
        from unittest import mock
        from agent_team import github
        from agent_team.workflows import ship
        calls = []

        def gh(*args, **kw):
            calls.append(args)
            return ""
        with mock.patch.object(github, "gh_json", return_value=[{"name": "bug"}, {"name": "Needs-Triage"}]), \
             mock.patch.object(github, "gh", gh):
            created = ship.ensure_labels("acme/app", ["bug", "needs-triage", "changes-requested"])
        self.assertEqual(created, ["changes-requested"])
        self.assertEqual([c[:3] for c in calls], [("label", "create", "changes-requested")])
        self.assertEqual(ship.ensure_labels("acme/app", []), [])
