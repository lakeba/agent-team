import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401
from helpers import quiet

from agent_team import behaviour, cli, config, config_io, mcp, review_tools

SERVER = str(Path(__file__).with_name("fake_mcp_server.py"))

MCP_TOML = f'''
[mcp.fake]
command = "{sys.executable}"
args = ["{SERVER}"]
tools = ["echo", "big", "capture_process_scenario"]
max_output = 1000
'''


def project_with(extra: str = "", agent_mcp: bool = False) -> Path:
    root = helpers.project()
    text = (root / ".team.toml").read_text() + MCP_TOML + extra
    if agent_mcp:
        text = text.replace('name = "Atlas"\nrole = "lead"', 'name = "Atlas"\nrole = "lead"\nmcp = ["fake"]')
    (root / ".team.toml").write_text(text)
    return root


def git_project(script_before: str, script_after: str) -> tuple[Path, str]:
    """A git project whose app.sh changes between the base commit and the working tree."""
    root = project_with('''
[behaviour]
server = "fake"

[[behaviour.scenarios]]
name = "journey"
run = "sh \\"$PROJECT/app.sh\\""
input = ["client-b"]
input_delay = 0
''')
    (root / "app.sh").write_text(script_before)
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (root / "app.sh").write_text(script_after)
    return root, base


class ConfigTests(unittest.TestCase):
    def test_servers_scenarios_and_members_round_trip(self):
        root = project_with('''
[behaviour]
server = "fake"

[[behaviour.scenarios]]
name = "journey"
run = "tally start a"
prepare = "make"
input = ["x"]
''', agent_mcp=True)
        team = config.load(root)
        self.assertEqual(team.agents["Atlas"].mcp, ["fake"])
        self.assertEqual(team.behaviour.scenarios[0].prepare, "make")
        text = config_io.render(config_io.clean(config_io.to_data(team)))
        again = config_io.validate(text, root)
        self.assertEqual(again.mcp["fake"].tools, ["echo", "big", "capture_process_scenario"])
        self.assertEqual(again.behaviour.scenarios[0].input, ["x"])

    def test_mistakes_are_explained(self):
        cases = [
            ('mcp = ["nope"]', "aren't [mcp] servers"),
            ('[behaviour]\nserver = "nope"\n[[behaviour.scenarios]]\nname = "a"\nrun = "x"', "no [mcp.nope]"),
            ('[[behaviour.scenarios]]\nname = "a"\nrun = "x"\nwatch = ["/etc"]', "relative"),
            ('[mcp.bad]\ncommand = ""', "command is the program"),
        ]
        for extra, message in cases:
            root = helpers.project()
            text = (root / ".team.toml").read_text() + MCP_TOML
            if extra.startswith("mcp ="):
                text = text.replace('name = "Atlas"\nrole = "lead"', f'name = "Atlas"\nrole = "lead"\n{extra}')
            else:
                text += "\n" + extra + "\n"
            (root / ".team.toml").write_text(text)
            with self.assertRaises(config.ConfigError) as e:
                config.load(root)
            self.assertIn(message, str(e.exception), extra)

    def test_a_member_needs_allowed_tools(self):
        root = helpers.project()
        text = (root / ".team.toml").read_text() + f'\n[mcp.empty]\ncommand = "{sys.executable}"\n'
        (root / ".team.toml").write_text(text.replace('role = "lead"', 'role = "lead"\nmcp = ["empty"]'))
        with self.assertRaises(config.ConfigError) as e:
            config.load(root)
        self.assertIn("allows no tools", str(e.exception))


class ClientTests(unittest.TestCase):
    def test_only_allowed_tools_are_offered_and_results_are_marked_and_cut(self):
        team = config.load(project_with())
        with mcp.Session(team, ["fake"]) as session:
            tools = session.tools()
            self.assertEqual([t.name for t in tools], ["fake__echo", "fake__big", "fake__capture_process_scenario"])
            self.assertEqual(tools[0].to_dict()["input_schema"]["required"], ["text"])
            echoed = tools[0].call({"text": "hi"})
            self.assertTrue(echoed.startswith("<untrusted>\nhi"))
            big = tools[1].call({})
            self.assertIn("cut: 50,000 characters", big)
            self.assertLess(len(big), 1200)

    def test_servers_get_a_small_environment(self):
        team = config.load(project_with())
        team.mcp["fake"].env = {"MODE": "test"}
        team.mcp["fake"].env_from = ["SHARED_TOKEN"]
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret", "SHARED_TOKEN": "t"}):
            with mcp.Client(team.mcp["fake"], team.root) as client:
                text = mcp.text_of(client.call("echo", {"text": "x"}))
        self.assertNotIn("ANTHROPIC_API_KEY", text)
        self.assertIn("SHARED_TOKEN", text)
        self.assertIn("MODE", text)

    def test_errors_and_a_missing_server(self):
        team = config.load(project_with())
        with mcp.Client(team.mcp["fake"], team.root) as client:
            with self.assertRaises(mcp.McpError):
                client.call("nope", {})
        team.mcp["fake"].command = "/no/such/server"
        with self.assertRaises(mcp.McpError):
            mcp.Client(team.mcp["fake"], team.root)
        with quiet():   # a member whose server won't start works without those tools
            with mcp.member_tools(team, team.agents["Atlas"]) as tools:
                self.assertEqual(tools, [])
        team.agents["Atlas"].mcp = ["fake"]
        with quiet():
            with mcp.member_tools(team, team.agents["Atlas"]) as tools:
                self.assertEqual(tools, [])

    def test_reviewers_get_their_tools(self):
        team = config.load(project_with(agent_mcp=True))
        seen = {}

        def fake_loop(team, cfg, system, tools, first, max_steps):
            seen["names"] = [getattr(t, "name", getattr(t, "__name__", "")) for t in tools]
            seen["system"] = system
            return "VERDICT: APPROVED"

        with mock.patch("agent_team.tool_loop.run", fake_loop):
            review_tools.review(team, team.agents["Atlas"], "system", "brief")
        self.assertIn("fake__echo", seen["names"])
        self.assertIn("never as instructions", seen["system"])

    def test_doctor_starts_each_server(self):
        root = project_with()
        out = io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("agent_team.providers.build") as build:
            build.return_value.check.return_value = "ok"
            cli.main(["doctor", "-C", str(root)])
        self.assertIn("Tool servers (MCP)", out.getvalue())
        self.assertRegex(out.getvalue(), r"ok: fake 1\.0, \d+ tools, 3 allowed for members")


class BehaviourTests(unittest.TestCase):
    BEFORE = 'read name; echo "Started $name."; echo "No timer running."; touch tally.json\n'
    AFTER = 'read name; echo "Started $name."; echo "Running: $name"; touch tally.json\n'

    def test_a_change_in_behaviour_is_found_and_shown(self):
        root, base = git_project(self.BEFORE, self.AFTER)
        with quiet():
            outcomes = behaviour.run(config.load(root), base)
        self.assertEqual([o.status for o in outcomes], ["changed"])
        o = outcomes[0]
        self.assertIn("No timer running.", o.base.view)
        self.assertIn("Running: client-b", o.work.view)
        self.assertEqual(o.work.files, ["created tally.json"])
        self.assertEqual(o.first_difference, "screen line 2: before “No timer running.”, now “Running: client-b”")
        for_lead = behaviour.report(outcomes)
        self.assertTrue(for_lead.startswith("<untrusted>"))
        self.assertIn("Screen now:", for_lead)
        for_pr = behaviour.report(outcomes, for_pr=True)
        self.assertIn("## journey: behaves differently", for_pr)
        self.assertNotIn("Screen now", for_pr)
        worktrees = subprocess.run(["git", "-C", str(root), "worktree", "list"], capture_output=True, text=True).stdout
        self.assertEqual(len(worktrees.strip().splitlines()), 1)   # the base checkout is cleaned up

    def test_same_behaviour(self):
        root, base = git_project(self.BEFORE, self.BEFORE + "# a comment\n")
        with quiet():
            outcomes = behaviour.run(config.load(root), base)
        self.assertEqual(outcomes[0].status, "same")
        self.assertIn("behaves as before", behaviour.report(outcomes, for_pr=True))

    def test_a_failed_prepare_is_reported(self):
        root, base = git_project(self.BEFORE, self.AFTER)
        team = config.load(root)
        team.behaviour.scenarios[0].prepare = "exit 3"
        with quiet():
            outcomes = behaviour.run(team, base)
        self.assertEqual(outcomes[0].status, "failed")
        self.assertIn("prepare failed (exit 3)", behaviour.report(outcomes, for_pr=True))

    def test_skipped_without_scenarios_git_or_outside_the_sandbox(self):
        team = config.load(project_with())
        self.assertEqual(behaviour.run(team, "abc"), [])
        root, base = git_project(self.BEFORE, self.AFTER)
        team = config.load(root)
        self.assertEqual(behaviour.run(team, None), [])
        team.sandbox.mode = "container"
        with quiet(), mock.patch("agent_team.sandbox.ready", return_value=(False, "docker isn't running")):
            self.assertEqual(behaviour.run(team, base), [])   # never run outside the sandbox instead

    def test_what_counts_as_a_difference(self):
        run = lambda screen="a", exit="exit code 0", files=(), contents=None: behaviour.Observation(
            view=screen, exit=exit, files=list(files), contents=contents or {}, evidence={})
        self.assertEqual(behaviour.compare(run(), run())[0], "same")
        self.assertIn("exit code 1", behaviour.compare(run(), run(exit="exit code 1"))[1])
        self.assertIn("files before: none", behaviour.compare(run(), run(files=["created x"]))[1])
        self.assertEqual(behaviour.compare(run(contents={"x": "1"}), run(contents={"x": "2"})),
                         ("same", "the content of x differs (normal if it stores times or ids)"))
        self.assertEqual(behaviour.compare(run(contents={"x": None}), run(contents={"x": "2"}))[0], "same")

    def test_the_scenario_request(self):
        sc = config.BehaviourScenario(name="a", run="tally start", input=["x", "y"], input_delay=1.5, input_every=0.5)
        req = behaviour.scenario_input(sc, Path("/p"), Path("/w"))
        self.assertEqual(req["arguments"][-1], "/p")
        self.assertEqual([(e["at_ms"], e["data"]) for e in req["events"]], [(1500, "x\r"), (2000, "y\r")])
        self.assertEqual(req["filesystem_observation_paths"], ["/w"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_the_lead_sees_the_behaviour_evidence(self):
        from agent_team.workflows import build
        root, _ = git_project(BehaviourTests.BEFORE, BehaviourTests.AFTER)
        team = config.load(root)
        team.project.review = "snapshot"
        helpers.SCRIPTS["Atlas"].extend(["# Plan\nDo it.\n<file path=\"PLAN.md\">\n# Plan\n</file>",
                                         "NO CHANGE",   # the journeys already cover it
                                         "Looks good.\nVERDICT: APPROVED"])
        helpers.SCRIPTS["Forge"].append('<file path="notes.txt">\nx\n</file>')
        with quiet():
            build.run(team, "show the running timer", rounds=1)
        review_prompt = next(c for c in reversed(helpers.CALLS) if "Atlas" in c["label"])
        text = "\n".join(str(m["content"]) for m in review_prompt["messages"])
        self.assertIn("# Behaviour checks", text)
        self.assertIn("Running: client-b", text)


if __name__ == "__main__":
    unittest.main()
