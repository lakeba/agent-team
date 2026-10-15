"""Spend limits, focused context, parallel builders, the qa/security/docs roles, scheduled shifts,
tool use for any provider, network discovery and background runs."""
import json
import os
import plistlib
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from anthropic import beta_tool

from agent_team import agent, budget, config_io, context, discovery, files, jobs, schedule, server, tool_loop, usage
from agent_team.config import ProviderConfig
from agent_team.providers import build as build_provider
from agent_team.providers.base import Provider, Reply, ToolCall, register
from agent_team.workflows import build

import helpers
from helpers import CALLS, SCRIPTS, load, project, quiet


def add_to_config(root: Path, text: str) -> None:
    path = root / ".team.toml"
    path.write_text(path.read_text() + text)


class SpendLimitTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_a_run_stops_once_it_reaches_its_limit(self):
        root = project()
        add_to_config(root, '\n[limits]\nper_run = 1.0\n\n[pricing.m]\ninput = 1000000.0\noutput = 0.0\n')
        team = load(root)
        usage.set_run("build@test")
        a = agent.make(team, team.get("Forge"), "builder")
        SCRIPTS["Forge"].append("ok")
        with quiet():
            a.turn("first")                       # nothing spent yet: allowed
        usage.record(root, "Forge", "fake", "m", {"input": 2, "output": 0})   # $2 at this price
        with self.assertRaises(budget.SpendLimitError):
            a.turn("second")
        self.assertEqual(budget.spent(team)["run"], 2.0)

    def test_the_daily_limit_counts_every_run_today(self):
        root = project()
        add_to_config(root, '\n[limits]\nper_day = 1.5\n\n[pricing.m]\ninput = 1000000.0\noutput = 0.0\n')
        team = load(root)
        usage.set_run("a@1")
        usage.record(root, "Atlas", "fake", "m", {"input": 1})
        usage.set_run("b@2")
        budget.check(team)                         # $1 of $1.50
        usage.record(root, "Atlas", "fake", "m", {"input": 1})
        with self.assertRaises(budget.SpendLimitError):
            budget.check(team)

    def test_limits_round_trip_through_the_editor(self):
        root = project()
        add_to_config(root, '\n[limits]\nper_run = 2.5\n')
        data = config_io.to_data(load(root))
        self.assertEqual(data["limits"], {"per_run": 2.5})
        self.assertIn("[limits]\nper_run = 2.5", config_io.render(data))
        self.assertTrue(config_io.plan_change(root, data)["valid"])

    def test_a_remote_node_is_priced_by_the_model_it_ran(self):
        @register("remote-claude-stub")
        class Stub(Provider):
            def complete(self, system, messages, *, model, effort, label):
                return Reply("hi", "hi", usage={"input": 1_000_000, "output": 0, "kind": "anthropic",
                                                 "model": "claude-opus-5-5"})
        root = project()
        text = (root / ".team.toml").read_text().replace('[providers.fake]\nkind = "fake"',
                                                        '[providers.fake]\nkind = "fake"\n\n[providers.node]\nkind = "remote-claude-stub"')
        (root / ".team.toml").write_text(text.replace('name = "Forge"\nrole = "builder"\nprovider = "fake"',
                                                      'name = "Forge"\nrole = "builder"\nprovider = "node"'))
        team = load(root)
        with quiet():
            agent.make(team, team.get("Forge"), "builder").turn("go")
        summary = usage.summarize(usage.load(root))
        self.assertEqual(summary["by_agent"]["Forge"]["cost"], 4.0)   # Opus 5.5 input, not "free"


class FocusedContextTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def big_project(self):
        files_ = {"README.md": "demo\n", "src/app.py": "def app():\n    return 1\n", "src/util.py": "X = 1\n"}
        files_.update({f"data/blob{i}.txt": "x" * 4000 for i in range(10)})
        root = project(files=files_)
        text = (root / ".team.toml").read_text().replace('guarantees =', 'context_limit = 20000\nguarantees =')
        (root / ".team.toml").write_text(text)
        return root

    def test_the_lead_picks_files_when_the_project_is_too_big(self):
        root = self.big_project()
        SCRIPTS["Atlas"].extend([
            "FILE: src/app.py",
            '<file path="PLAN.md">\n# Plan\n</file>\nFILE: src/util.py',
            "Good.\nVERDICT: APPROVED",
        ])
        SCRIPTS["Forge"].append('<file path="src/app.py">\ndef app():\n    return 2\n</file>')
        with quiet():
            self.assertTrue(build.run(load(root), "change app", rounds=1))
        planning = CALLS[1]["messages"][-1]["content"]
        self.assertIn('<file path="src/app.py">', planning)
        self.assertNotIn("blob0.txt\">", planning)                     # big files stay out
        builder_view = next(c for c in CALLS if "Forge" in c["label"])["messages"][-1]["content"]
        self.assertIn('<file path="src/util.py">', builder_view)       # widened by a FILE: line

    def test_small_projects_are_sent_whole(self):
        team = load(project(files={"a.py": "1\n"}))
        self.assertFalse(context.needs_focus(team))
        self.assertIn('<file path="a.py">', context.for_topic(team))

    def test_full_mode_still_fails_loudly(self):
        root = self.big_project()
        text = (root / ".team.toml").read_text().replace("context_limit = 20000", 'context_limit = 20000\ncontext = "full"')
        (root / ".team.toml").write_text(text)
        with self.assertRaises(files.SnapshotTooLarge):
            context.for_topic(load(root))

    def test_topic_workflows_get_key_files_and_a_map(self):
        text = context.for_topic(load(self.big_project()))
        self.assertIn('<file path="README.md">', text)
        self.assertIn("data/blob3.txt  (4,000 bytes)", text)


class ParallelAndRolesTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def team_with(self, extra: str, files_=None):
        root = project(files=files_ or {"README.md": "demo\n"})
        add_to_config(root, extra)
        return root

    def test_builders_work_on_their_own_parts_at_once(self):
        root = self.team_with('\n[[agents]]\nname = "Anvil"\nrole = "builder"\nprovider = "fake"\nmodel = "m"\n')
        SCRIPTS["Atlas"].extend([
            '<file path="PLAN.md">\n# Plan\n</file>\nPART: Forge | api/ | the API\nPART: Anvil | web/ | the page',
            "Both parts done.\nVERDICT: APPROVED",
        ])
        SCRIPTS["Forge"].append('<file path="api/a.py">\nA = 1\n</file>\n<file path="web/sneaky.html">\nx\n</file>')
        SCRIPTS["Anvil"].append('<file path="web/index.html">\n<p>hi</p>\n</file>')
        with quiet():
            self.assertTrue(build.run(load(root), "api and page", rounds=1, parallel=True))
        self.assertTrue((root / "api/a.py").exists())
        self.assertTrue((root / "web/index.html").exists())
        self.assertFalse((root / "web/sneaky.html").exists())          # outside Forge's part
        review = [c for c in CALLS if "Atlas" in c["label"]][-1]["messages"][-1]["content"]
        self.assertIn("Forge's message", review)
        self.assertIn("Anvil's message", review)

    def test_overlapping_parts_fall_back_to_one_builder(self):
        team = load(self.team_with('\n[[agents]]\nname = "Anvil"\nrole = "builder"\nprovider = "fake"\nmodel = "m"\n'))
        with quiet():
            parts = build.parse_parts(team, "PART: Forge | src/ | a\nPART: Anvil | src/web/ | b", team.all_by_role("builder"))
        self.assertEqual([p.builder.name for p in parts], ["Forge"])

    def test_qa_first_security_sends_back_docs_after(self):
        root = self.team_with(
            '\n[[agents]]\nname = "Probe"\nrole = "qa"\nprovider = "fake"\nmodel = "m"\n'
            '\n[[agents]]\nname = "Sentinel"\nrole = "security"\nprovider = "fake"\nmodel = "m"\nowns = ["*"]\n'
            '\n[[agents]]\nname = "Scribe"\nrole = "docs"\nprovider = "fake"\nmodel = "m"\n')
        SCRIPTS["Atlas"].extend(['<file path="PLAN.md">\n# Plan\n</file>', "VERDICT: APPROVED", "VERDICT: APPROVED"])
        SCRIPTS["Probe"].append('<file path="tests/test_x.py">\nassert True\n</file>\n<file path="src/x.py">\nno\n</file>')
        SCRIPTS["Forge"].extend(['<file path="src/x.py">\nos.system(cmd)\n</file>', '<file path="src/x.py">\nsafe()\n</file>'])
        SCRIPTS["Sentinel"].extend(["Shell injection in src/x.py.\nSIGN-OFF: NO", "Fixed.\nSIGN-OFF: YES"])
        SCRIPTS["Scribe"].append('<file path="README.md">\ndemo, now with x\n</file>')
        with quiet():
            self.assertTrue(build.run(load(root), "add x", rounds=3))
        self.assertTrue((root / "tests/test_x.py").exists())
        self.assertEqual((root / "src/x.py").read_text(), "safe()\n")   # QA couldn't write src/
        second = [c for c in CALLS if "Forge" in c["label"]][1]["messages"][-1]["content"]
        self.assertIn("Shell injection", second)                       # the NO went back to the builder
        self.assertEqual((root / "README.md").read_text(), "demo, now with x\n")

    def test_skip_leaves_optional_members_out(self):
        root = self.team_with('\n[[agents]]\nname = "Sentinel"\nrole = "security"\nprovider = "fake"\nmodel = "m"\n')
        SCRIPTS["Atlas"].extend(['<file path="PLAN.md">\n# Plan\n</file>', "VERDICT: APPROVED"])
        SCRIPTS["Forge"].append('<file path="a.py">\n1\n</file>')
        with quiet():
            self.assertTrue(build.run(load(root), "a", rounds=1, skip=("security",)))
        self.assertFalse(any("Sentinel" in c["label"] for c in CALLS))

    def test_star_owns_every_path(self):
        root = self.team_with('\n[[agents]]\nname = "Sentinel"\nrole = "security"\nprovider = "fake"\nmodel = "m"\nowns = ["*"]\n')
        self.assertIn("Sentinel", load(root).owners_of(["anything/at/all.py"]))


class ScheduleTests(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(schedule.parse_every("6h"), 21600)
        self.assertEqual(schedule.parse_every("30m"), 1800)
        for bad in ("2m", "6", "soon"):
            with self.assertRaises(ValueError):
                schedule.parse_every(bad)

    def test_two_shifts_never_overlap(self):
        root = project()
        with schedule.lock(root, "ship"):
            with self.assertRaises(schedule.AlreadyRunning):
                with schedule.lock(root, "ship"):
                    pass
        with schedule.lock(root, "ship"):   # released afterwards
            pass

    def test_scheduler_entries(self):
        root = project()
        plist = plistlib.loads(schedule.launchd_plist(root, "ship", 21600, ["--max-steps", "20"]))
        self.assertEqual(plist["StartInterval"], 21600)
        self.assertIn("ship", plist["ProgramArguments"][-1])
        self.assertIn("--max-steps 20", plist["ProgramArguments"][-1])
        self.assertTrue(schedule.cron_line(root, "ship", 21600).startswith("0 */6 * * * "))
        self.assertTrue(schedule.cron_line(root, "ship", 1800).startswith("*/30 * * * * "))


@register("fake-tools")
class FakeToolProvider(Provider):
    supports_tools = True
    script: list = []

    def complete_tools(self, system, messages, tools, *, model, effort, label):
        FakeToolProvider.seen = [dict(m) for m in messages]
        return FakeToolProvider.script.pop(0)


class ToolLoopTests(unittest.TestCase):
    def test_any_provider_can_act_through_tools(self):
        root = project()
        text = (root / ".team.toml").read_text().replace('[providers.fake]\nkind = "fake"',
                                                        '[providers.fake]\nkind = "fake"\n\n[providers.local]\nkind = "fake-tools"')
        (root / ".team.toml").write_text(text + '\n[[agents]]\nname = "Harbor"\nrole = "devops"\nprovider = "local"\nmodel = "q"\n')
        done = []

        @beta_tool
        def comment(number: int, body: str) -> str:
            """Comment on an issue.

            Args:
                number: The issue.
                body: The text.
            """
            done.append((number, body))
            return "posted"

        FakeToolProvider.script = [
            Reply("Commenting.", "", tool_calls=[ToolCall("c1", "comment", {"number": 3, "body": "thanks"}),
                                                 ToolCall("c2", "nope", {})]),
            Reply("Shift done.", ""),
        ]
        team = load(root)
        with quiet():
            summary = tool_loop.run(team, team.get("Harbor"), "sys", [comment], "start", max_steps=5)
        self.assertEqual(summary, "Shift done.")
        self.assertEqual(done, [(3, "thanks")])
        results = [m for m in FakeToolProvider.seen if m["role"] == "tool"]
        self.assertEqual(results[0]["content"], "posted")
        self.assertIn("no tool named 'nope'", results[1]["content"])

    def test_openai_compatible_tool_calls(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                body = json.dumps({"choices": [{"message": {"content": "", "tool_calls": [
                    {"id": "x1", "type": "function", "function": {"name": "comment", "arguments": '{"number": 1, "body": "hi"}'}}]}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            p = build_provider(ProviderConfig(name="o", kind="openai", url=f"http://127.0.0.1:{httpd.server_address[1]}"))
            msgs = [{"role": "user", "content": "go"},
                    {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "comment", "arguments": {"number": 9}}]},
                    {"role": "tool", "tool_call_id": "a", "name": "comment", "content": "ok"}]
            tools = [{"name": "comment", "description": "d", "input_schema": {"type": "object"}}]
            with quiet():
                reply = p.complete_tools("sys", msgs, tools, model="m", effort="high", label="L")
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(reply.tool_calls[0].arguments, {"number": 1, "body": "hi"})
        sent = seen["body"]
        self.assertEqual(sent["tools"][0]["function"]["name"], "comment")
        self.assertEqual(json.loads(sent["messages"][2]["tool_calls"][0]["function"]["arguments"]), {"number": 9})
        self.assertEqual(sent["messages"][3], {"role": "tool", "tool_call_id": "a", "content": "ok"})

    def test_remote_nodes_pass_tools_through(self):
        FakeToolProvider.script = [Reply("", "", tool_calls=[ToolCall("r1", "comment", {"number": 2})])]
        node = build_provider(ProviderConfig(name="f", kind="fake-tools"))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(node, "q", "t" * 32, "box"))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        os.environ["NODE_TOK_TEST"] = "t" * 32
        try:
            remote = build_provider(ProviderConfig(name="r", kind="agent-http", url=f"http://127.0.0.1:{httpd.server_address[1]}"),
                                    "t" * 32)
            with quiet():
                reply = remote.complete_tools("sys", [{"role": "user", "content": "go"}],
                                              [{"name": "comment", "input_schema": {"type": "object"}}],
                                              model="", effort="high", label="L")
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual((reply.tool_calls[0].name, reply.tool_calls[0].arguments), ("comment", {"number": 2}))
        self.assertEqual(reply.usage["kind"], "fake-tools")


class DiscoveryTests(unittest.TestCase):
    def test_a_node_answers_a_probe(self):
        if not discovery.start_responder("studio", "ollama", "qwen", 8765):
            self.skipTest("discovery port in use")
        found = discovery.discover(1.0, targets=("127.0.0.1",))
        self.assertIn({"node": "studio", "url": "http://127.0.0.1:8765", "host": "127.0.0.1", "provider": "ollama",
                       "model": "qwen", "version": found[0]["version"]}, found)


class JobTests(unittest.TestCase):
    def test_form_input_is_checked(self):
        self.assertEqual(jobs.argv_for("fix", {"number": 12}), ["fix", "12", "--rounds", "2"])
        with self.assertRaises(jobs.JobError):
            jobs.argv_for("fix", {"number": "12; rm"})
        self.assertEqual(jobs.argv_for("build", {"task": "add x", "branch": "feat/x", "pr": True, "skip": ["docs"]}),
                         ["build", "add x", "--rounds", "3", "--branch", "feat/x", "--pr", "--skip", "docs"])
        for wf, params in [("build", {}), ("build", {"task": "x", "pr": True}), ("build", {"task": "x", "branch": "--force"}),
                           ("build", {"task": "x", "rounds": "3; rm"}), ("rm", {}), ("discuss", {"topic": 5}),
                           ("build", {"task": "x", "skip": ["lead"]})]:
            with self.assertRaises(jobs.JobError, msg=(wf, params)):
                jobs.argv_for(wf, params)
        with self.assertRaises(jobs.JobError):
            jobs.get(project(), "../../etc/passwd")

    def test_a_background_run_records_output_and_exit_code(self):
        root = project()
        job = jobs.start(root, "doctor")
        deadline = time.time() + 30
        while jobs.get(root, job["id"])["status"] == "running" and time.time() < deadline:
            time.sleep(0.2)
        out = jobs.output(root, job["id"])
        self.assertIn("$ agent-team doctor", out["text"])
        self.assertIn(out["status"], ("failed", "succeeded"))     # the fake provider isn't known to a new process
        self.assertEqual(jobs.list_jobs(root)[0]["id"], job["id"])


if __name__ == "__main__":
    unittest.main()
