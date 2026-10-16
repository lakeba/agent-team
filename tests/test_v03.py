"""0.3.0: patch edits, reviews with tools, fixes inside the shift, autopilot, team memory, scoreboard."""
import subprocess
import unittest
from unittest import mock

from agent_team import agent, files, memory, review_tools, scoreboard, usage
from agent_team.providers.base import Provider, Reply, ToolCall, register
from agent_team.workflows import autopilot, build

import helpers
from helpers import CALLS, SCRIPTS, load, project, quiet


@register("scripted-tools")
class ScriptedTools(Provider):
    """A provider that can call tools, replaying a script; also answers plain turns from SCRIPTS."""
    supports_tools = True
    script: list = []
    seen: list = []

    def complete_tools(self, system, messages, tools, *, model, effort, label):
        ScriptedTools.seen.append({"system": system, "messages": [dict(m) for m in messages],
                                   "tools": [t["name"] for t in tools]})
        return ScriptedTools.script.pop(0)

    def complete(self, system, messages, *, model, effort, label):
        CALLS.append({"label": label, "system": system, "messages": [dict(m) for m in messages]})
        for name, queue in SCRIPTS.items():
            if name in label and queue:
                text = queue.popleft()
                return Reply(text=text, content=text)
        raise AssertionError(f"no scripted reply left for {label!r}")


def tool_lead(root):
    """Point the lead at the tool-capable provider."""
    text = (root / ".team.toml").read_text().replace(
        '[providers.fake]\nkind = "fake"', '[providers.fake]\nkind = "fake"\n\n[providers.tools]\nkind = "scripted-tools"')
    text = text.replace('name = "Atlas"\nrole = "lead"\nprovider = "fake"', 'name = "Atlas"\nrole = "lead"\nprovider = "tools"')
    (root / ".team.toml").write_text(text)


class PatchEditTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_search_replace_edits(self):
        new, problem = files.apply_hunks("a\nb\nc\n", [("b", "B"), ("c\n", "C\n")])
        self.assertEqual((new, problem), ("a\nB\nC\n", ""))
        self.assertIn("matches 2 places", files.apply_hunks("x\nx\n", [("x", "y")])[1])
        new, problem = files.apply_hunks("def f():\n    return 1\n", [("def g():", "z")])
        self.assertIn("isn't in the file", problem)
        self.assertEqual(new, "def f():\n    return 1\n")                  # unchanged on a problem
        self.assertEqual(files.apply_hunks("a  \nb\n", [("a\nb", "c")]), ("c\n", ""))   # trailing spaces

    def test_edit_blocks_apply_atomically_per_file_and_report_problems(self):
        root = project(files={"app.py": "def f():\n    return 1\n", "util.py": "X = 1\n"})
        reply = ('<edit path="app.py">\n<<<<<<< SEARCH\n    return 1\n=======\n    return 2\n>>>>>>> REPLACE\n</edit>\n'
                 '<edit path="util.py">\n<<<<<<< SEARCH\nY = 1\n=======\nY = 2\n>>>>>>> REPLACE\n</edit>\n'
                 '<edit path="nope.py">\n<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE\n</edit>\n'
                 '<file path="new.py">\nN = 1\n</file>')
        with quiet():
            written = files.write_files(root, reply)
        self.assertEqual(sorted(written), ["app.py", "new.py"])
        self.assertEqual((root / "app.py").read_text(), "def f():\n    return 2\n")
        self.assertEqual((root / "util.py").read_text(), "X = 1\n")
        note = files.problems_note(written)
        self.assertIn("util.py: edit 1: the SEARCH text isn't in the file", note)
        self.assertIn("nope.py: no such file to edit", note)
        self.assertEqual(files.strip_files(reply).count("[edit omitted]"), 3)

    def test_edits_respect_allowed_paths_and_the_project_boundary(self):
        root = project(files={"src/a.py": "1\n", "docs/x.md": "1\n"})
        reply = ('<edit path="docs/x.md">\n<<<<<<< SEARCH\n1\n=======\n2\n>>>>>>> REPLACE\n</edit>'
                 '<edit path="../escape.py">\n<<<<<<< SEARCH\n1\n=======\n2\n>>>>>>> REPLACE\n</edit>')
        with quiet():
            written = files.write_files(root, reply, allowed=("src/",))
        self.assertEqual(list(written), [])
        self.assertEqual((root / "docs/x.md").read_text(), "1\n")

    def test_failed_edits_reach_the_lead_and_the_next_round(self):
        root = project(files={"app.py": "A = 1\n"})
        SCRIPTS["Atlas"].extend(['<file path="PLAN.md">\n# Plan\n</file>', "Edit didn't apply.\nVERDICT: CHANGES",
                                 "Good.\nVERDICT: APPROVED"])
        SCRIPTS["Forge"].extend(['<edit path="app.py">\n<<<<<<< SEARCH\nA = 9\n=======\nA = 2\n>>>>>>> REPLACE\n</edit>',
                                 '<edit path="app.py">\n<<<<<<< SEARCH\nA = 1\n=======\nA = 2\n>>>>>>> REPLACE\n</edit>'])
        with quiet():
            self.assertTrue(build.run(load(root), "set A to 2", rounds=2))
        self.assertEqual((root / "app.py").read_text(), "A = 2\n")
        review_prompt = [c for c in CALLS if "Atlas" in c["label"]][1]["messages"][-1]["content"]
        self.assertIn("Edits that were NOT applied", review_prompt)
        second_build = [c for c in CALLS if "Forge" in c["label"]][1]["messages"][-1]["content"]
        self.assertIn("app.py: edit 1: the SEARCH text isn't in the file", second_build)


class ToolReviewTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()
        ScriptedTools.script, ScriptedTools.seen = [], []

    def test_tools_read_search_and_refuse_secrets(self):
        root = project(files={"src/app.py": "def handler():\n    return 404\n", ".env": "KEY=secret\n"})
        tools = {t.name: t for t in review_tools.make_tools(load(root), touched={"src/app.py"})}
        self.assertIn("    2     return 404", tools["read_file"].call({"path": "src/app.py"}))
        self.assertIn("Not readable", tools["read_file"].call({"path": ".env"}))
        self.assertIn("Not readable", tools["read_file"].call({"path": ".team.toml"}))
        self.assertIn("Not readable", tools["read_file"].call({"path": "../../etc/passwd"}))
        self.assertIn("src/app.py:2:", tools["search"].call({"pattern": r"return \d+"}))
        self.assertIn("src/app.py", tools["list_files"].call({"prefix": "src/"}))
        self.assertIn("exit code 0", tools["run_tests"].call({}))
        self.assertIn("return 404", tools["diff"].call({}))

    def test_the_diff_tool_uses_git_when_there_is_a_base(self):
        root = project(files={"a.py": "1\n"})
        for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (root / "a.py").write_text("2\n")
        (root / "b.py").write_text("new\n")
        diff = {t.name: t for t in review_tools.make_tools(load(root), base)}["diff"].call({})
        self.assertIn("-1\n+2", diff)
        self.assertIn("--- new file b.py", diff)

    def test_a_tool_capable_lead_reviews_with_tools(self):
        root = project(files={"app.py": "A = 1\n"})
        tool_lead(root)
        self.assertTrue(review_tools.supported(load(root), load(root).get("Atlas")))
        SCRIPTS["Atlas"].append('<file path="PLAN.md">\n# Plan: set A\n</file>')        # planning stays a plain turn
        SCRIPTS["Forge"].append('<file path="app.py">\nA = 2\n</file>')
        ScriptedTools.script = [Reply("", "", tool_calls=[ToolCall("1", "read_file", {"path": "app.py"})]),
                                Reply("Checked app.py: A is 2.\nVERDICT: APPROVED", "")]
        with quiet():
            self.assertTrue(build.run(load(root), "set A to 2", rounds=1))
        first = ScriptedTools.seen[0]
        self.assertIn("read_file", first["tools"])
        self.assertIn("# PLAN.md", first["messages"][0]["content"])
        self.assertIn("    1 A = 2", ScriptedTools.seen[1]["messages"][-1]["content"])   # the tool result

    def test_snapshot_mode_and_non_tool_providers_keep_the_old_review(self):
        root = project()
        self.assertFalse(review_tools.supported(load(root), load(root).get("Atlas")))     # fake provider: no tools
        tool_lead(root)
        (root / ".team.toml").write_text((root / ".team.toml").read_text().replace('guarantees =', 'review = "snapshot"\nguarantees ='))
        self.assertFalse(review_tools.supported(load(root), load(root).get("Atlas")))


class MemoryTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_lessons_are_learned_deduplicated_and_shown_to_every_member(self):
        root = project()
        team = load(root)
        added = memory.learn(team, "Blocking: fake version.\nLESSON: Never name a release version that doesn't exist yet.\n"
                                   "- LESSON: Every behaviour change gets a Changed entry in CHANGELOG.md.\n"
                                   "LESSON: a third one is ignored because only two count\nVERDICT: CHANGES", "Atlas")
        self.assertEqual(len(added), 2)
        self.assertEqual(memory.learn(team, "LESSON: never name a release version that doesn't exist yet!", "Atlas"), [])
        system = agent.make(load(root), load(root).get("Forge"), "builder").system
        self.assertIn("# Lessons this team has learned on this project", system)
        self.assertIn("- Never name a release version that doesn't exist yet.", system)
        self.assertEqual(memory.forget(root, 1), "Never name a release version that doesn't exist yet.")
        self.assertEqual(len(memory.lessons(root)), 1)

    def test_memory_is_capped(self):
        root = project()
        memory.add(root, [f"Lesson number {i} about something specific" for i in range(memory.MAX_LESSONS + 5)])
        items = memory.lessons(root)
        self.assertEqual(len(items), memory.MAX_LESSONS)
        self.assertIn("number 44", items[-1]["text"])


class ScoreboardTests(unittest.TestCase):
    def test_builders_reviewers_and_cost_per_merged_pr(self):
        root = project()
        log = files.Log(root, "build", "Build: x")
        log.record("Forge: round 1", "built")
        log.record("Tests: round 1", "ok")
        log.record("Atlas: review 1", "no\nVERDICT: CHANGES")
        log.record("Forge: round 2", "built")
        log.record("Atlas: review 2", "yes\nVERDICT: APPROVED")
        log.f.close()
        usage.record(root, "Forge", "anthropic", "claude-opus-5-5", {"input": 1_000_000})
        log = files.Log(root, "ship", "Ops shift")
        log.record("Atlas: review of PR #1 at abc", "ok\nVERDICT: APPROVED")
        log.record("Harbor: action", "merged PR #1 at abc")
        log.f.close()
        usage.set_run("")
        data = scoreboard.compute(load(root))
        forge = data["builders"]["Forge"]
        self.assertEqual((forge["builds"], forge["approved"], forge["first_round"], forge["avg_rounds"]), (1, 1, 0, 2.0))
        self.assertEqual(forge["cost"], 4.0)
        self.assertNotIn("Tests", data["builders"])
        self.assertEqual(data["reviewers"]["Atlas"]["reviews"], 3)
        self.assertEqual(data["reviewers"]["Atlas"]["pushback_rate"], 0.33)
        self.assertEqual((data["team"]["merged_prs"], data["team"]["cost_per_merged_pr"]), (1, 4.0))


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def team(self):
        root = project()
        (root / ".team.toml").write_text((root / ".team.toml").read_text().replace('repo = ""', 'repo = "acme/app"')
                                         + '\n[[agents]]\nname = "Harbor"\nrole = "devops"\nprovider = "fake"\nmodel = "m"\n')
        (root / "ROADMAP.md").write_text("# Roadmap\n## M1\n- export\n")
        return load(root)

    def test_picks_the_next_task_or_says_done(self):
        team = self.team()
        lead = agent.make(team, team.get("Atlas"), "lead")
        SCRIPTS["Atlas"].extend(["TASK: Add CSV export (M1).\nBRANCH: csv export", "DONE: M1 is merged."])
        with mock.patch("agent_team.github.gh_json", return_value=[]), quiet():
            self.assertEqual(autopilot.pick_next(team, lead, "M1"), ("Add CSV export (M1).", "team/csv-export", ""))
            self.assertEqual(autopilot.pick_next(team, lead, "M1"), ("", "", "M1 is merged."))
        self.assertIn("within milestone M1", CALLS[0]["messages"][0]["content"])

    def test_cycles_ship_then_build_then_stop_when_done(self):
        team = self.team()
        open_prs = [[{"number": 7, "headRefOid": "a"}], [], []]
        calls = []
        with mock.patch.object(autopilot, "team_prs", side_effect=lambda repo: open_prs.pop(0)), \
             mock.patch.object(autopilot.ship, "run", side_effect=lambda *a, **k: calls.append("ship")), \
             mock.patch.object(autopilot.build, "run", side_effect=lambda *a, **k: calls.append(("build", k["branch"])) or True), \
             mock.patch.object(autopilot, "pick_next", side_effect=[("Add export", "team/export", ""), ("", "", "all done")]), \
             mock.patch("agent_team.github.git", return_value=""), quiet():
            self.assertTrue(autopilot.run(team, "M1", max_cycles=5))
        self.assertEqual(calls, ["ship", ("build", "team/export")])
        self.assertIn("Done: all done", (team.root / ".team/logs/autopilot.md").read_text())

    def test_stops_when_open_prs_dont_move(self):
        team = self.team()
        with mock.patch.object(autopilot, "team_prs", return_value=[{"number": 7, "headRefOid": "a"}]), \
             mock.patch.object(autopilot.ship, "run") as shift, \
             mock.patch("agent_team.github.git", return_value=""), quiet():
            self.assertFalse(autopilot.run(team, max_cycles=6))
        self.assertEqual(shift.call_count, 2)
        self.assertIn("didn't move in two shifts", (team.root / ".team/logs/autopilot.md").read_text())

    def test_jobs_accept_autopilot(self):
        from agent_team import jobs
        self.assertEqual(jobs.argv_for("autopilot", {"milestone": "M2", "max_cycles": 4}),
                         ["autopilot", "--max-cycles", "4", "--milestone", "M2"])
        with self.assertRaises(jobs.JobError):
            jobs.argv_for("autopilot", {"milestone": "M2; rm -rf /"})


if __name__ == "__main__":
    unittest.main()
