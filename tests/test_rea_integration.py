import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import quiet

from agent_team import behaviour, cli, config, rea, sandbox, steps
from agent_team.workflows import init, journeys
from test_mcp import MCP_TOML, git_project, project_with

PAGE_V1 = "<html><body><h1>Tally</h1><p>No timer running.</p><button>Start</button></body></html>"
PAGE_V2 = "<html><body><h1>Tally</h1><p>Running: client-a</p><button>Start</button><!-- v2 --></body></html>"


def web_project(before: str, after: str) -> tuple[Path, str]:
    """A git project serving index.html with python's http.server; the page changes in the working tree."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    root, base = git_project("true\n", "true\n")
    text = (root / ".team.toml").read_text().split("[[behaviour.scenarios]]")[0]
    (root / ".team.toml").write_text(text + f'''
[[behaviour.scenarios]]
name = "home page"
kind = "browser"
serve = "{sys.executable} -m http.server {port} --bind 127.0.0.1"
url = "http://127.0.0.1:{port}/"
steps = ['click button "Start"']
timeout = 30
''')
    (root / "index.html").write_text(before)
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "web"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (root / "index.html").write_text(after)
    return root, base


class StepsTests(unittest.TestCase):
    def test_plain_words_become_browser_actions(self):
        actions = steps.parse_steps(['fill textbox "Project" with "a b"', 'click button "Start"', "wait 200",
                                     'press textbox "Project" Enter', 'select combobox "Plan" option "Pro"',
                                     'check css "#remember"', 'wait for text "Running"', "goto /about"])
        self.assertEqual(actions[0]["value"], {"source": "literal", "value": "a b"})
        self.assertEqual(actions[1]["locator"], {"kind": "role", "role": "button", "name": "Start"})
        self.assertEqual([a["action"] for a in actions],
                         ["fill", "click", "wait_for_timeout", "press", "select_option", "check", "wait_for", "goto"])

    def test_mistakes_are_explained(self):
        for bad, words in [("tap button \"x\"", "steps start with"), ('click blob "x"', "isn't a role"),
                           ('fill textbox "x"', "with"), ('press textbox "x" Zz', "one key")]:
            with self.assertRaises(steps.StepError) as e:
                steps.parse_step(bad, 0)
            self.assertIn(words, str(e.exception))


class ScenarioConfigTests(unittest.TestCase):
    def test_kinds_need_their_fields_and_browsers_stay_local(self):
        cases = [('kind = "browser"\nurl = "https://example.com/"', "don't visit other sites"),
                 ('kind = "api"', "assembly"), ('kind = "api"\nassembly = "a.dll"\npackage = "."', "either"), ('kind = "terminal"', "needs run"), ('kind = "gui"\nrun = "x"', "kind is"),
                 ('kind = "browser"\nurl = "http://127.0.0.1:1/"\nsteps = ["tap x"]', "steps start with"),
                 ('kind = "browser"\nurl = "http://127.0.0.1:1/"\nstep_timeout = 0', "step_timeout is seconds")]
        for body, words in cases:
            root = project_with(f'\n[[behaviour.scenarios]]\nname = "a"\n{body}\n')
            with self.assertRaises(config.ConfigError) as e:
                config.load(root)
            self.assertIn(words, str(e.exception), body)

    def test_the_teams_own_file_is_read_and_kept_out_of_saves(self):
        from agent_team import config_io
        root = project_with('\n[behaviour]\nserver = "fake"\n')
        (root / "team").mkdir()
        (root / "team/behaviour.toml").write_text('[[scenarios]]\nname = "journey"\nrun = "echo hi"\n')
        team = config.load(root)
        self.assertEqual([(s.name, s.source) for s in team.behaviour.scenarios], [("journey", "team/behaviour.toml")])
        self.assertNotIn("journey", config_io.render(config_io.clean(config_io.to_data(team))))
        (root / "team/behaviour.toml").write_text("[other]\nx = 1\n")
        with self.assertRaises(config.ConfigError):
            config.load(root)


class KindsTests(unittest.TestCase):
    def test_browser_journey_finds_the_changed_page(self):
        root, base = web_project(PAGE_V1, PAGE_V2)
        team = config.load(root)
        team.behaviour.browser = "/usr/bin/true"   # the fake server doesn't launch it
        with quiet():
            outcomes = behaviour.run(team, base, label="test")
        o = outcomes[0]
        self.assertEqual((o.kind, o.status), ("browser", "changed"))
        self.assertIn('"Tally No timer running. Start"', o.first_difference)
        self.assertIn("5.0% of the screenshot's pixels changed", o.notes)
        saved = behaviour.recent(team)
        self.assertEqual(saved[0]["outcomes"][0]["status"], "changed")
        folder = behaviour.evidence_root(team) / saved[0]["id"]
        self.assertTrue((folder / "1-work.png").exists() and (folder / "report.md").exists())

    def test_each_browser_step_has_a_deadline_except_a_pause(self):
        sc = config.BehaviourScenario(name="a", kind="browser", url="http://127.0.0.1:1/", step_timeout=5,
                                      steps=['click button "Start"', "wait 200", 'wait for text "Running"', "goto /x"])
        actions = behaviour.browser_input(config.load(project_with("")), sc)["actions"]
        self.assertEqual([a.get("timeout_ms") for a in actions], [5000, None, 5000, 5000])
        sc.timeout = 3   # never longer than the whole scenario
        actions = behaviour.browser_input(config.load(project_with("")), sc)["actions"]
        self.assertEqual(actions[0]["timeout_ms"], 3000)

    def test_a_step_that_fails_is_named_not_an_empty_page(self):
        root, base = web_project(PAGE_V1, PAGE_V1.replace("<button>Start</button>", "<button>Begin</button>"))
        team = config.load(root)
        team.behaviour.browser = "/usr/bin/true"
        with quiet():
            o = behaviour.run(team, base)[0]
        self.assertEqual(o.status, "changed")
        self.assertEqual(o.base.exit, "all steps completed")
        self.assertIn('step step-1 (click button "Start") failed', o.work.exit)
        self.assertIn('stopped at step step-1 (click button "Start") failed', o.work.view)
        self.assertIn('now "stopped at step step-1', o.first_difference)
        self.assertIn('- Now: step step-1 (click button "Start") failed', behaviour.report([o]))

    def test_a_new_page_error_counts(self):
        root, base = web_project(PAGE_V1, PAGE_V1.replace("</body>", "boom</body>"))
        team = config.load(root)
        team.behaviour.browser = "/usr/bin/true"
        with quiet():
            o = behaviour.run(team, base)[0]
        self.assertEqual(o.status, "changed")

    def test_api_changes_and_what_breaks_callers(self):
        def asm(methods):
            return json.dumps({"types": [{"full_name": "Lib.Store", "flags": 1}, {"full_name": "<>c", "flags": 3}],
                               "methods": [{"declaring_type": "Lib.Store", "name": n, "flags": f,
                                            "signature": {"parameter_types": p, "return_type": "class:93"}}
                                           for n, f, p in methods], "fields": []})
        root, base = git_project("true\n", "true\n")
        text = (root / ".team.toml").read_text().split("[[behaviour.scenarios]]")[0]
        (root / ".team.toml").write_text(text + '\n[[behaviour.scenarios]]\nname = "public API"\nkind = "api"\n'
                                         'assembly = "out/Lib.dll"\n')
        (root / "out").mkdir()
        (root / "out/Lib.dll").write_text(asm([("Load", 6, []), ("Save", 6, ["string"]), ("Hidden", 1, [])]))
        for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "api"]):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (root / "out/Lib.dll").write_text(asm([("Load", 6, []), ("Save", 6, ["string", "i4"]), ("Version", 6, []),
                                               ("Hidden2", 1, [])]))
        with quiet():
            o = behaviour.run(config.load(root), base)[0]
        self.assertEqual(o.status, "changed")
        self.assertEqual(o.breaking, ["method Lib.Store.Save(string): class"])
        self.assertIn("method Lib.Store.Version(): class", o.added)
        self.assertNotIn("Hidden", " ".join(o.breaking + o.added))
        self.assertIn("breaks callers", behaviour.report([o], for_pr=True))


    def test_javascript_exports(self):
        root, base = git_project("true\n", "true\n")
        text = (root / ".team.toml").read_text().split("[[behaviour.scenarios]]")[0]
        (root / ".team.toml").write_text(text + '\n[[behaviour.scenarios]]\nname = "library"\nkind = "api"\npackage = "lib"\n')
        (root / "lib/src").mkdir(parents=True)
        (root / "lib/package.json").write_text('{"exports": {".": "./src/index.js"}}')
        (root / "lib/src/index.js").write_text("export function start() {}\nexport function stop() {}\n")
        (root / "lib/src/internal.js").write_text("export function helper() {}\n")
        for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "js"]):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (root / "lib/src/index.js").write_text("export function start() {}\nexport const VERSION = 2\n")
        (root / "lib/src/internal.js").write_text("")
        with quiet():
            o = behaviour.run(config.load(root), base)[0]
        self.assertEqual(o.breaking, ["export src/index.js: stop"])   # internal.js isn't public
        self.assertEqual(o.added, ["export src/index.js: VERSION"])


class ReleaseCheckTests(unittest.TestCase):
    def test_the_smallest_version_the_changes_allow(self):
        from agent_team import release_check as rc
        self.assertEqual(rc.needed((1, 4, 2), breaking=True, added=False), (2, 0, 0))
        self.assertEqual(rc.needed((0, 4, 2), breaking=True, added=True), (0, 5, 0))   # 0.x: minor
        self.assertEqual(rc.needed((1, 4, 2), breaking=False, added=True), (1, 5, 0))
        self.assertEqual(rc.needed((1, 4, 2), breaking=False, added=False), (1, 4, 3))

    def test_a_too_small_release_is_refused_with_the_evidence(self):
        from agent_team import release_check as rc
        root, _ = git_project("true\n", "true\n")
        text = (root / ".team.toml").read_text().split("[[behaviour.scenarios]]")[0]
        (root / ".team.toml").write_text(text + '\n[[behaviour.scenarios]]\nname = "library"\nkind = "api"\npackage = "lib"\n')
        (root / "lib").mkdir()
        (root / "lib/package.json").write_text('{"exports": {".": "./index.js"}}')
        (root / "lib/index.js").write_text("export function start() {}\nexport function stop() {}\n")
        git = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "1.4.0")
        git("tag", "v1.4.0")
        (root / "lib/index.js").write_text("export function start() {}\n")    # stop is gone
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "drop stop")
        head = git("rev-parse", "HEAD").strip()
        with quiet():
            result = rc.check(config.load(root), head)
        self.assertEqual((result["since"], result["breaking"], result["least"]), ("v1.4.0", ["export index.js: stop"], "2.0.0"))
        self.assertIn("must be at least 2.0.0", rc.refuse(result, "1.5.0"))
        self.assertEqual(rc.refuse(result, "2.0.0"), "")
        self.assertIn("breaks callers", rc.summary(result))

    def test_nothing_to_compare(self):
        from agent_team import release_check as rc
        self.assertEqual(rc.check(config.load(project_with()), "HEAD"), {})
        self.assertEqual(rc.refuse({}, "0.0.1"), "")


class SandboxTests(unittest.TestCase):
    def test_terminal_runs_go_into_the_container(self):
        root, _ = git_project("true\n", "true\n")
        team = config.load(root)
        team.sandbox.mode = "container"
        with mock.patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}" if n == "docker" else None):
            req = behaviour.scenario_input(team.behaviour.scenarios[0], Path("/p"), Path("/w"), team)
        self.assertEqual(req["executable"], "/usr/bin/docker")
        argv = req["arguments"]
        self.assertIn("/p:/project", " ".join(argv))
        self.assertIn("--network", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertIn("-t", argv)

    def test_browser_apps_publish_only_on_loopback(self):
        team = config.load(project_with())
        with mock.patch("shutil.which", return_value="/usr/bin/docker"):
            argv = sandbox.container(team, "n", {"/p": "/project"}, "/project", ports=[5173])
        self.assertIn("127.0.0.1:5173:5173", argv)


class ReaTests(unittest.TestCase):
    def test_claude_codes_registration_is_reused(self):
        home = Path(tempfile.mkdtemp())
        (home / ".claude.json").write_text(json.dumps({"mcpServers": {"rea": {"command": sys.executable,
                                                                              "args": ["-m", "rea"]}}}))
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home), "XDG_DATA_HOME": str(home)}), \
                mock.patch("shutil.which", return_value=None):
            self.assertEqual(rea.find(), (sys.executable, ["-m", "rea"], "registered with Claude Code"))

    def test_configure_appends_once_and_keeps_comments(self):
        root = helpers.project()
        (root / ".team.toml").write_text((root / ".team.toml").read_text() + "\n# my note\n")
        self.assertTrue(rea.configure(root, "/opt/rea", ["--mcp"]))
        self.assertFalse(rea.configure(root, "/opt/rea", ["--mcp"]))
        text = (root / ".team.toml").read_text()
        self.assertIn("# my note", text)
        team = config.load(root)
        self.assertEqual((team.mcp["rea"].command, team.behaviour.server), ("/opt/rea", "rea"))

    def test_node_versions(self):
        for out, ok in [("v22.19.0", True), ("v22.18.1", False), ("v24.10.0", False), ("v24.11.0", True),
                        ("v26.1.0", True), ("v20.5.0", False)]:
            with mock.patch("shutil.which", return_value="/usr/bin/node"), \
                    mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, out, "")):
                self.assertEqual(rea.node_ok()[0], ok, out)

    def test_init_sets_up_rea_when_it_is_installed(self):
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(rea, "find", return_value=("/opt/rea", ["--mcp"], "on the PATH")), quiet():
            init.run(root)
        self.assertEqual(config.load(root).mcp["rea"].command, "/opt/rea")
        other = Path(tempfile.mkdtemp())
        with mock.patch.object(rea, "find", return_value=("/opt/rea", ["--mcp"], "on the PATH")), quiet():
            init.run(other, use_rea=False)
        self.assertEqual(config.load(other).mcp, {})

    def test_status_without_rea(self):
        out = io.StringIO()
        with mock.patch.object(rea, "find", return_value=("", [], "")), mock.patch("sys.stdout", out):
            self.assertEqual(cli.main(["rea", "status", "-C", str(helpers.project())]), 1)
        self.assertIn("agent-team rea setup", out.getvalue())


class JourneyTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_the_team_writes_valid_journeys_and_bad_ones_are_sent_back(self):
        root = project_with('\n[behaviour]\nserver = "fake"\n')
        team = config.load(root)
        helpers.SCRIPTS["Atlas"].extend([
            '<file path="team/behaviour.toml">\n[[scenarios]]\nname = "x"\nkind = "browser"\nurl = "https://a.b/"\n</file>',
            '<file path="team/behaviour.toml">\n[[scenarios]]\nname = "start a timer"\nrun = "echo hi"\n</file>'])
        with quiet():
            written = journeys.for_task(team, team.agents["Atlas"], "timers", "# Plan")
        self.assertEqual(written, ["team/behaviour.toml"])
        self.assertIn("don't visit other sites", str(helpers.CALLS[-1]["messages"][-1]["content"]))
        self.assertEqual([s.name for s in config.load(root).behaviour.scenarios], ["start a timer"])

    def test_no_change_and_two_bad_tries_leave_the_file_alone(self):
        root = project_with('\n[behaviour]\nserver = "fake"\n')
        team = config.load(root)
        helpers.SCRIPTS["Atlas"].append("NO CHANGE")
        with quiet():
            self.assertEqual(journeys.for_task(team, team.agents["Atlas"], "t", "p"), [])
        helpers.SCRIPTS["Atlas"].extend(['<file path="team/behaviour.toml">\nnot toml\n</file>'] * 2)
        with quiet():
            self.assertEqual(journeys.for_task(team, team.agents["Atlas"], "t", "p"), [])
        self.assertFalse((root / "team/behaviour.toml").exists())

    def test_cli_list_and_run(self):
        root, _ = git_project("echo one\n", "echo two\n")
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            cli.main(["behaviour", "list", "-C", str(root)])
            code = cli.main(["behaviour", "run", "-C", str(root)])
        self.assertIn("journey  (terminal, in .team.toml)", out.getvalue())
        self.assertIn("behaves differently", out.getvalue())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
