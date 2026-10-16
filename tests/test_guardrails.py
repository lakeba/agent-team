"""Guardrail scenarios: whole devops shifts against a stand-in GitHub, with a scripted devops member.

Each scenario scripts the tool calls the devops member makes and checks what the tools allowed:
the rules are enforced in code, so they must hold whatever the model asks for.
"""
import json
import unittest
from unittest import mock

from agent_team import gates, github
from agent_team.providers.base import Provider, Reply, ToolCall, register
from agent_team.workflows import ship

import helpers
from helpers import SCRIPTS, load, project, quiet


@register("guard-devops")
class ScriptedDevops(Provider):
    """Replays tool calls; each step's tool results are kept for the test to read."""
    supports_tools = True
    steps: list = []
    results: list = []

    def complete_tools(self, system, messages, tools, *, model, effort, label):
        ScriptedDevops.results = [m for m in messages if m["role"] == "tool"]
        if not ScriptedDevops.steps:
            return Reply("Shift summary: done.", "")
        calls = ScriptedDevops.steps.pop(0)
        return Reply("", "", tool_calls=[ToolCall(f"c{i}", name, args) for i, (name, args) in enumerate(calls)])


class FakeGitHub:
    def __init__(self, paths, sha="aaaaaaaaaa11"):
        self.paths, self.sha, self.calls, self.green = paths, sha, [], True

    def gh_json(self, *args, check=True):
        if args[:2] == ("pr", "view"):
            return {"title": "Change things", "body": "", "headRefOid": self.sha, "author": {"login": "lakeba"}}
        return []

    def gh(self, *args, check=True, input=None, token=""):
        self.calls.append(args)
        return ""

    def merged(self):
        return any(c[:2] == ("pr", "merge") for c in self.calls)

    def patches(self):
        return [mock.patch.object(github, "gh_json", self.gh_json), mock.patch.object(github, "gh", self.gh),
                mock.patch.object(github, "head_sha", lambda repo: "main0000000"),
                mock.patch.object(github, "run_for_commit", lambda repo, sha: None),
                mock.patch.object(github, "release_test_counts", lambda repo, p: {}),
                mock.patch.object(github, "ci_test_counts", lambda repo, sha, p: {}),
                mock.patch.object(github, "ci_status", lambda repo, n: (self.green, "test: SUCCESS")),
                mock.patch.object(github, "ci_failed", lambda repo, n: not self.green),
                mock.patch.object(github, "changed_files", lambda repo, n: list(self.paths)),
                mock.patch.object(github, "diff_for", lambda repo, n, prefixes=None: "diff --git a/x b/x"),
                mock.patch.object(github, "main_snapshot", lambda *a, **k: "(files)"),
                mock.patch.object(ship.time, "sleep", lambda s: None)]


def team_root(extra=""):
    root = project()
    text = (root / ".team.toml").read_text().replace('repo = ""', f'repo = "acme/app"{extra}')
    text = text.replace('[providers.fake]\nkind = "fake"', '[providers.fake]\nkind = "fake"\n\n[providers.ops]\nkind = "guard-devops"')
    (root / ".team.toml").write_text(text + '\n[[agents]]\nname = "Harbor"\nrole = "devops"\nprovider = "ops"\nmodel = "m"\n')
    return root


class GuardrailScenarios(unittest.TestCase):
    def setUp(self):
        helpers.reset()
        ScriptedDevops.steps, ScriptedDevops.results = [], []

    def shift(self, root, gh, steps, **kw):
        ScriptedDevops.steps = steps
        patches = gh.patches()
        for p in patches:
            p.start()
        try:
            with quiet():
                ship.run(load(root), **kw)
        finally:
            for p in patches:
                p.stop()
        out = [m["content"] for m in ScriptedDevops.results]
        errors = [o for o in out if o.startswith("error:")]
        self.assertEqual(errors, [], "a tool failed inside the shift")
        return out

    def test_no_merge_without_the_leads_approval(self):
        gh = FakeGitHub(["app.py"])
        out = self.shift(team_root(), gh, [[("merge_pull_request", {"number": 1})]])
        self.assertIn("REFUSED: the lead has not approved", out[0])
        self.assertFalse(gh.merged())

    def test_the_leads_approval_is_its_own_sign_off(self):
        gh = FakeGitHub(["ROADMAP.md"])                       # Atlas owns ROADMAP.md
        SCRIPTS["Atlas"].append("Fine.\nVERDICT: APPROVED")
        out = self.shift(team_root(), gh, [[("request_signoffs", {"number": 1, "note": "n"})],
                                           [("request_lead_review", {"number": 1, "note": "n"})],
                                           [("merge_pull_request", {"number": 1})]])
        self.assertIn("counts as its sign-off", out[0])
        self.assertEqual(out[-1], "merged")
        self.assertTrue(gh.merged())

    def test_an_owners_no_blocks_the_merge(self):
        gh = FakeGitHub(["site/index.html"])                  # Spark owns site/
        SCRIPTS["Spark"].append("Wrong claims.\nSIGN-OFF: NO")
        SCRIPTS["Atlas"].append("Fine.\nVERDICT: APPROVED")
        out = self.shift(team_root(), gh, [[("request_signoffs", {"number": 1, "note": "n"})],
                                           [("request_lead_review", {"number": 1, "note": "n"})],
                                           [("merge_pull_request", {"number": 1})]])
        self.assertIn("REFUSED: missing sign-off on this commit from: Spark", out[-1])
        self.assertFalse(gh.merged())

    def test_red_ci_blocks_the_merge(self):
        gh = FakeGitHub(["app.py"])
        gh.green = False
        SCRIPTS["Atlas"].append("Fine.\nVERDICT: APPROVED")
        out = self.shift(team_root(), gh, [[("request_lead_review", {"number": 1, "note": "n"})],
                                           [("merge_pull_request", {"number": 1})]])
        self.assertIn("REFUSED: CI is not all green", out[-1])

    def test_gated_paths_wait_for_the_owners_approval_of_that_commit(self):
        root = team_root('\nrequire_approval = ["auth/"]')
        gh = FakeGitHub(["auth/token.py"])
        SCRIPTS["Atlas"].extend(["Fine.\nVERDICT: APPROVED"] * 2)
        steps = [[("request_lead_review", {"number": 1, "note": "n"})], [("merge_pull_request", {"number": 1})]]
        out = self.shift(root, gh, [list(s) for s in steps])
        self.assertIn("needs the owners' approval", out[-1])
        self.assertFalse(gh.merged())
        self.assertEqual(gates.requests(root)[0]["number"], 1)
        gates.approve(root, 1, gh.sha)                        # the owner approves this exact commit
        out = self.shift(root, gh, [list(s) for s in steps])
        self.assertEqual(out[-1], "merged")
        self.assertEqual(gates.requests(root), [])

    def test_an_approval_doesnt_carry_over_to_a_new_commit(self):
        root = team_root('\nrequire_approval = ["auth/"]')
        gh = FakeGitHub(["auth/token.py"])
        gates.approve(root, 1, "old0000000")
        SCRIPTS["Atlas"].append("Fine.\nVERDICT: APPROVED")
        out = self.shift(root, gh, [[("request_lead_review", {"number": 1, "note": "n"})],
                                    [("merge_pull_request", {"number": 1})]])
        self.assertIn("needs the owners' approval", out[-1])

    def test_request_fix_then_a_fresh_review_of_the_new_commit(self):
        gh = FakeGitHub(["app.py"])
        SCRIPTS["Atlas"].extend(["Broken.\nVERDICT: CHANGES", "Now fine.\nVERDICT: APPROVED"])

        def fake_fix(team, number, *a, **k):
            gh.sha = "bbbbbbbbbb22"                           # the builder pushed a new commit
            return True
        with mock.patch("agent_team.workflows.fix.run", fake_fix):
            out = self.shift(team_root(), gh, [[("request_lead_review", {"number": 1, "note": "n"})],
                                               [("request_fix", {"number": 1})],
                                               [("merge_pull_request", {"number": 1})],
                                               [("request_lead_review", {"number": 1, "note": "n"})],
                                               [("merge_pull_request", {"number": 1})]])
        self.assertIn("Fixed: new head bbbbbbbbbb", out[1])
        self.assertIn("REFUSED: the lead has not approved", out[2])     # the old approval was for CHANGES anyway
        self.assertEqual(out[-1], "merged")
        merge = next(c for c in gh.calls if c[:2] == ("pr", "merge"))
        self.assertIn("bbbbbbbbbb22", merge)                  # merged exactly the reviewed commit

    def test_request_fix_is_limited_per_pr(self):
        gh = FakeGitHub(["app.py"])
        with mock.patch("agent_team.workflows.fix.run", lambda *a, **k: False):
            out = self.shift(team_root(), gh, [[("request_fix", {"number": 1})], [("request_fix", {"number": 1})],
                                               [("request_fix", {"number": 1})]])
        self.assertIn("NOT FIXED", out[0])
        self.assertIn("REFUSED: PR #1 has had two fixes this shift", out[2])

    def test_release_ask_records_a_proposal_and_publishes_nothing(self):
        root = team_root('\nrelease = "ask"')
        gh = FakeGitHub([])
        out = self.shift(root, gh, [[("create_release", {"version": "0.2.0", "notes": "Fixes"})]])
        self.assertIn("NOT RELEASED", out[0])
        self.assertFalse(any(c[:2] == ("release", "create") for c in gh.calls))
        self.assertEqual(json.loads((root / ".team/release-proposal.json").read_text())["version"], "0.2.0")

    def test_set_labels_creates_missing_labels(self):
        gh = FakeGitHub([])
        self.shift(team_root(), gh, [[("set_labels", {"number": 3, "add": ["needs-triage"], "remove": []})]])
        self.assertIn(("label", "create", "needs-triage"), [c[:3] for c in gh.calls])


if __name__ == "__main__":
    unittest.main()
