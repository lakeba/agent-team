import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (test config dir; no network search for Ollama)
from helpers import quiet

from agent_team import cli, completion, composition, config, config_io, readiness
from agent_team.composition import Composition
from agent_team.workflows import init


def kinds(team) -> dict[str, str]:
    return {a.name: team.providers[a.provider].kind for a in team.agents.values()}


class CompositionTests(unittest.TestCase):
    def test_members_follow_the_models_choice(self):
        c = Composition(models="mixed", extras=("qa",), builders=2)
        roles = [(m["name"], m["role"], m["provider"]) for m in c.members()]
        self.assertEqual(roles, [("Atlas", "lead", "claude"), ("Forge", "builder", "local"), ("Anvil", "builder", "local"),
                                 ("Spark", "marketing", "claude"), ("Harbor", "devops", "claude"), ("Probe", "qa", "claude")])
        self.assertEqual({m["provider"] for m in Composition(models="ollama").members()}, {"local"})
        self.assertEqual({m["provider"] for m in Composition(models="claude").members()}, {"claude"})
        with self.assertRaises(ValueError):
            Composition(builders=9).check()
        with self.assertRaises(ValueError):
            Composition(extras=("chef",)).check()

    def test_init_flags_write_each_composition(self):
        cases = [(["--models", "claude", "--members", "all", "--builders", "3", "--per-run", "2"], 9, {"anthropic"}),
                 (["--models", "ollama", "--members", "qa", "--ollama-url", "http://10.0.0.5:11434"], 5, {"ollama"}),
                 ([], 4, {"anthropic", "ollama"})]
        for flags, size, expected in cases:
            root = Path(tempfile.mkdtemp())
            with mock.patch.object(readiness, "ollama_models", return_value=["qwen3-coder:30b"]), quiet():
                cli.main(["init", "-C", str(root), "--yes", *flags])
            team = config.load(root)
            self.assertEqual(len(team.agents), size, flags)
            self.assertEqual(set(kinds(team).values()), expected, flags)
        self.assertEqual(team.providers["local"].url, "http://localhost:11434")

    def test_claude_only_has_no_ollama_and_keeps_limits(self):
        root = Path(tempfile.mkdtemp())
        with quiet():
            cli.main(["init", "-C", str(root), "--yes", "--models", "claude", "--per-run", "2", "--per-day", "9"])
        team = config.load(root)
        self.assertNotIn("local", team.providers)
        self.assertEqual((team.limits.per_run, team.limits.per_day), (2.0, 9.0))
        self.assertIn('# url = "http://localhost:11434"', (root / ".team.toml").read_text())

    def test_init_asks_in_a_terminal(self):
        root = Path(tempfile.mkdtemp())
        answers = iter(["", "", "2", "security, docs", "2", "1", "y"])   # no vision, no app, Ollama only, two extras, 2 builders, first server, write
        servers = [("http://10.37.129.2:11434", ["qwen3-coder:30b"])]
        with mock.patch("builtins.input", lambda prompt="": next(answers)), \
                mock.patch.object(readiness, "find_ollama", return_value=servers), quiet():
            init.run(root, interactive=True)
        team = config.load(root)
        self.assertEqual(sorted(a.role for a in team.agents.values()),
                         ["builder", "builder", "devops", "docs", "lead", "marketing", "security"])
        self.assertEqual(team.providers["local"].url, "http://10.37.129.2:11434")
        self.assertEqual({a.model for a in team.agents.values()}, {"qwen3-coder:30b"})

    def test_saying_no_writes_nothing(self):
        root = Path(tempfile.mkdtemp())
        answers = iter(["", "", "3", "none", "1", "n", "n"])   # no vision, no app, Claude only, no extras, 1 builder, no limits, don't write
        with mock.patch("builtins.input", lambda prompt="": next(answers)), quiet():
            with self.assertRaises(SystemExit):
                init.run(root, interactive=True)
        self.assertFalse((root / ".team.toml").exists())

    def test_flags_skip_their_questions(self):
        root = Path(tempfile.mkdtemp())
        answers = iter(["y"])   # only the final confirmation is asked
        with mock.patch("builtins.input", lambda prompt="": next(answers)), quiet():
            init.run(root, interactive=True, models="claude", extras=(), builders=1, per_run=0, per_day=0, vision="", inspire_url="")
        self.assertEqual(len(config.load(root).agents), 4)


class InspirationQuestionTests(unittest.TestCase):
    def test_init_asks_for_an_app_you_like_and_its_confirmation(self):
        from agent_team import inspire
        root = Path(tempfile.mkdtemp())
        answers = iter(["", "https://app.example/", "y", "3", "none", "1", "n", "y"])
        out = io.StringIO()
        with mock.patch("builtins.input", lambda prompt="": next(answers)), mock.patch("sys.stdout", out):
            init.run(root, interactive=True)
        self.assertTrue(inspire.confirmed(root, "https://app.example/"))
        self.assertIn(inspire.CONFIRMATION, out.getvalue())
        self.assertIn("agent-team inspire https://app.example/", out.getvalue())
        other = Path(tempfile.mkdtemp())   # no confirmation, no app
        answers = iter(["", "https://app.example/", "", "3", "none", "1", "n", "y"])
        with mock.patch("builtins.input", lambda prompt="": next(answers)), quiet():
            init.run(other, interactive=True)
        self.assertEqual(inspire.apps(other), [])


class VisionTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_init_asks_for_the_vision_first_and_saves_it(self):
        root = Path(tempfile.mkdtemp())
        answers = iter(["Split a bill between friends in one command.", "", "3", "none", "1", "n", "y"])
        with mock.patch("builtins.input", lambda prompt="": next(answers)), quiet():
            init.run(root, interactive=True)
        self.assertEqual((root / "VISION.md").read_text(), "# Vision\n\nSplit a bill between friends in one command.\n")

    def test_init_vision_flag_takes_text_or_a_file_and_keeps_an_existing_one(self):
        root = Path(tempfile.mkdtemp())
        source = Path(tempfile.mkdtemp()) / "idea.md"
        source.write_text("# tipsplit\n\nBills, split fairly.\n")
        with quiet():
            cli.main(["init", "-C", str(root), "--yes", "--models", "claude", "--vision", str(source)])
        self.assertEqual((root / "VISION.md").read_text(), "# tipsplit\n\nBills, split fairly.\n")
        self.assertIn("left as it is", init.write_vision(root, "Something else"))
        self.assertEqual((root / "VISION.md").read_text(), "# tipsplit\n\nBills, split fairly.\n")

    def test_every_workflow_gets_vision_md(self):
        from agent_team import context
        self.assertEqual(context.ALWAYS[0], "VISION.md")
        root = helpers.project(files={"VISION.md": "# Vision\nA calm todo app.\n"})
        team = config.load(root)
        self.assertIn("VISION.md", context.default_paths(team))
        self.assertEqual(context.vision(team), "# Vision\nA calm todo app.")

    def run_discussion(self, root: Path, **kwargs) -> str:
        from agent_team.workflows import discuss
        helpers.reset()
        helpers.SCRIPTS["Atlas"].extend(["Plan.\nSTATUS: AGREE", '<file path="ROADMAP.md">\n# Roadmap\n</file>'])
        helpers.SCRIPTS["Forge"].append("Fine.\nSTATUS: AGREE")
        with quiet():
            discuss.run(config.load(root), turns=2, **kwargs)
        return helpers.CALLS[0]["system"]

    def test_discuss_plans_towards_the_vision(self):
        root = helpers.project(files={"VISION.md": "# Vision\nA calm todo app.\n"})
        system = self.run_discussion(root)
        self.assertIn("# The product vision", system)
        self.assertIn("A calm todo app.", system.split("# Your perspective")[0])
        self.assertIn("No VISION.md yet", self.run_discussion(helpers.project()))

    def test_discuss_vision_flag_saves_vision_md_when_missing(self):
        from agent_team.workflows import discuss
        root = helpers.project()
        source = Path(tempfile.mkdtemp()) / "pitch.md"
        source.write_text("A todo app for teams.\n")
        with quiet():
            text = discuss.adopt_vision(config.load(root), source)
        self.assertEqual(text, "A todo app for teams.")
        self.assertEqual((root / "VISION.md").read_text(), "A todo app for teams.\n")
        source.write_text("Something different.\n")
        with quiet():
            self.assertEqual(discuss.adopt_vision(config.load(root), source), "Something different.")
        self.assertEqual((root / "VISION.md").read_text(), "A todo app for teams.\n")   # kept
        with self.assertRaises(SystemExit):
            discuss.adopt_vision(config.load(root), Path("/nope/vision.md"))

    def test_discuss_topic_is_optional(self):
        args = cli.build_parser().parse_args(["discuss", "--vision", "V.md"])
        self.assertEqual((args.topic, args.vision), ("next milestones", "V.md"))


class RecomposeTests(unittest.TestCase):
    def team_data(self, *flags) -> tuple[Path, dict]:
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(readiness, "ollama_models", return_value=["m"]), quiet():
            cli.main(["init", "-C", str(root), "--yes", *flags])
        return root, config_io.to_data(config.load(root))

    def test_apply_moves_members_and_keeps_their_settings(self):
        root, data = self.team_data("--members", "all", "--builders", "3")
        data["agents"][0]["skills"] = ["team/skills/x.md"]
        data["agents"][1]["escalate_to"] = "Kiln"
        data["limits"] = {"per_run": 4.0}
        new = composition.apply(data, Composition(models="ollama", ollama_url="http://gpu:11434", ollama_model="m2",
                                                  extras=("qa",), builders=1, keep_limits=True))
        self.assertTrue(config_io.plan_change(root, new)["valid"])
        names = [a["name"] for a in new["agents"]]
        self.assertEqual(names, ["Atlas", "Forge", "Spark", "Harbor", "Probe"])
        self.assertEqual(new["agents"][0]["skills"], ["team/skills/x.md"])     # kept
        self.assertNotIn("escalate_to", new["agents"][1])                     # Kiln is gone
        self.assertEqual({a["provider"] for a in new["agents"]}, {"local"})
        self.assertEqual(new["providers"]["local"]["url"], "http://gpu:11434")
        self.assertNotIn("claude", new["providers"])
        self.assertEqual(new["limits"], {"per_run": 4.0})

    def test_from_data_reads_a_team_back(self):
        _, data = self.team_data("--members", "security", "--builders", "2", "--models", "ollama")
        c = composition.from_data(data)
        self.assertEqual((c.models, c.extras, c.builders, c.ollama_model), ("ollama", ("security",), 2, "m"))

    def test_from_form_checks_input(self):
        with self.assertRaises(ValueError):
            composition.from_form({"models": "ollama", "ollama_url": "gpu:11434"})
        with self.assertRaises(ValueError):
            composition.from_form({"builders": "lots"})
        c = composition.from_form({"models": "claude", "extras": ["docs"], "builders": "2"})
        self.assertTrue(c.keep_limits)


class OllamaSearchTests(unittest.TestCase):
    def test_addresses_from_ollama_host(self):
        for value, url in [("0.0.0.0", "http://localhost:11434"), ("10.0.0.5", "http://10.0.0.5:11434"),
                           ("10.0.0.5:9999", "http://10.0.0.5:9999"), ("https://box/", "https://box:11434")]:
            self.assertEqual(readiness._ollama_url(value), url)

    def test_candidates_include_the_vm_host_and_skip_this_machine(self):
        with mock.patch.object(readiness, "_own_addresses", return_value={"10.211.55.4"}), \
                mock.patch.object(readiness, "_gateways", return_value=["10.211.55.1"]), \
                mock.patch.dict(os.environ, {"OLLAMA_HOST": "gpu.local"}):
            urls = helpers.REAL_OLLAMA_CANDIDATES()
        self.assertEqual(urls[:2], ["http://gpu.local:11434", "http://localhost:11434"])
        self.assertIn("http://10.211.55.2:11434", urls)
        self.assertIn("http://10.37.129.2:11434", urls)
        self.assertNotIn("http://10.211.55.4:11434", urls)

    def test_find_keeps_only_servers_that_answer(self):
        answers = {"http://a:11434": None, "http://b:11434": ["m"]}
        with mock.patch.object(readiness, "ollama_models", side_effect=lambda u, timeout=0: answers[u]):
            self.assertEqual(readiness.find_ollama(candidates=list(answers)), [("http://b:11434", ["m"])])

    def test_init_without_an_address_uses_the_server_it_finds(self):
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(readiness, "find_ollama", return_value=[("http://10.37.129.2:11434", ["m"])]), quiet():
            init.run(root)
        self.assertEqual(config.load(root).providers["local"].url, "http://10.37.129.2:11434")


class CompletionTests(unittest.TestCase):
    def complete(self, *words):
        return [w for w, _ in completion.candidates(cli.build_parser(), list(words))]

    def test_commands_options_and_choices(self):
        self.assertIn("build", self.complete("bu"))
        self.assertEqual(self.complete("init", "--mod"), ["--models"])
        self.assertEqual(self.complete("init", "--models", ""), ["mixed", "ollama", "claude"])
        self.assertEqual(self.complete("init", "--models=o"), ["--models=ollama"])
        self.assertEqual(self.complete("init", "--members", "qa,s"), ["qa,security"])
        self.assertEqual(self.complete("completion", ""), ["install", "bash", "zsh"])
        self.assertIn("<task>", self.complete("build", ""))
        self.assertNotIn("--rounds", self.complete("build", "x", "--rounds", ""))   # a number: nothing to offer
        self.assertEqual(self.complete("nope", ""), [])

    def test_member_names_come_from_the_team(self):
        root = helpers.project()
        names = self.complete("build", "-C", str(root), "--builder", "")
        team = config.load(root)
        self.assertEqual(names, [a.name for a in team.agents.values() if a.role == "builder"])

    def test_the_hidden_command_prints_candidates(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(cli.main(["__complete", "init", "--models", ""]), 0)
        self.assertEqual(out.getvalue().split(), ["mixed", "ollama", "claude"])

    def test_install_writes_the_bash_file(self):
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": home}), quiet():
            self.assertEqual(completion.install("bash"), 0)
        self.assertIn("complete -o default -F _agent_team agent-team",
                      (Path(home) / "bash-completion/completions/agent-team").read_text())

    def test_zsh_install_asks_before_editing_zshrc(self):
        home, zdot = tempfile.mkdtemp(), tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": home, "ZDOTDIR": zdot}), \
                mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="n"), quiet():
            completion.install("zsh")
        self.assertFalse((Path(zdot) / ".zshrc").exists())
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": home, "ZDOTDIR": zdot}), quiet():
            completion.install("zsh", yes=True)
            completion.install("zsh", yes=True)     # twice: the line is added once
        self.assertEqual((Path(zdot) / ".zshrc").read_text().count("agent-team tab completion"), 1)


if __name__ == "__main__":
    unittest.main()
