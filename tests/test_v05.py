"""0.5.0: sandbox, estimates and milestone budgets, ranked context, identities, evals, templates,
activity metrics and the project registry."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_team import (budget, config_io, estimate, evals, files, github, metrics, projects, rank, sandbox,
                        templates, usage)
from agent_team.config import ConfigError

import helpers
from helpers import SCRIPTS, load, project, quiet


def toml(root, extra="", project_extra=""):
    text = (root / ".team.toml").read_text().replace('repo = ""', f'repo = "acme/app"{project_extra}')
    (root / ".team.toml").write_text(text + extra)
    return root


class SandboxTests(unittest.TestCase):
    def test_container_command_isolates_the_run(self):
        root = toml(project(files={"pyproject.toml": "[project]\nname='x'\n"}), '\n[sandbox]\nmode = "container"\n')
        team = load(root)
        with mock.patch.object(sandbox.shutil, "which", lambda n: "/usr/bin/docker" if n == "docker" else None):
            argv = sandbox.command(team, "python -m unittest", "agent-team-x")
        self.assertEqual(argv[:3], ["docker", "run", "--rm"])
        self.assertIn("--network", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertIn(f"{Path(root).resolve()}:/work", argv)
        self.assertIn("python:3.12-slim", argv)
        self.assertFalse(any(a.startswith("ANTHROPIC") for a in argv))          # no keys passed in
        self.assertEqual(argv[-3:], ["sh", "-c", "python -m unittest"])

    def test_network_and_images(self):
        root = toml(project(files={"App.csproj": "<Project/>"}), '\n[sandbox]\nmode = "container"\nnetwork = true\n')
        team = load(root)
        with mock.patch.object(sandbox.shutil, "which", lambda n: "/usr/bin/" + n):
            argv = sandbox.command(team, "dotnet test", "n")
        self.assertNotIn("--network", argv)
        self.assertIn("mcr.microsoft.com/dotnet/sdk:10.0", argv)

    def test_no_engine_fails_loudly_never_unsandboxed(self):
        team = load(toml(project(), '\n[sandbox]\nmode = "container"\n'))
        with mock.patch.object(sandbox.shutil, "which", lambda n: None):
            with self.assertRaises(sandbox.SandboxError):
                sandbox.run(team, "true")
            self.assertFalse(sandbox.ready(team)[0])

    def test_off_runs_here_and_bad_modes_are_refused(self):
        team = load(project())
        self.assertEqual(sandbox.run(team, "echo hi")[0], 0)
        with self.assertRaises(ConfigError):
            load(toml(project(), '\n[sandbox]\nmode = "vm"\n'))


class EstimateAndBudgetTests(unittest.TestCase):
    def test_estimates_from_history_and_warnings(self):
        root = toml(project(), '\n[limits]\nper_run = 0.5\n\n[pricing.m]\ninput = 1.0\noutput = 0.0\n')
        self.assertIsNone(estimate.estimate(load(root), "build")["typical"])
        for i, cost in enumerate([0.2, 0.4, 0.6]):
            usage.set_run(f"build@2026-10-0{i + 1}T00:00:00+00:00")
            usage.record(root, "Forge", "fake", "m", {"input": int(cost * 1_000_000)})
        usage.set_run("")
        e = estimate.estimate(load(root), "build")
        self.assertEqual((e["typical"], e["high"], e["runs"]), (0.4, 0.6, 3))
        self.assertIn("per-run limit", e["warning"])

    def test_a_milestone_budget_stops_autopilot_spending(self):
        root = toml(project(), '\n[limits.milestones]\nM2 = 1.0\n\n[pricing.m]\ninput = 1000000.0\noutput = 0.0\n')
        team = load(root)
        usage.set_milestone("M2")
        try:
            usage.record(root, "Forge", "fake", "m", {"input": 1_000_000})
            with self.assertRaises(budget.SpendLimitError):
                budget.check(team)
            usage.set_milestone("M3")
            budget.check(team)                                   # another milestone: no budget
        finally:
            usage.set_milestone("")
        self.assertEqual(json.loads((root / ".team/usage.jsonl").read_text().splitlines()[0])["milestone"], "M2")


class RankTests(unittest.TestCase):
    def test_the_relevant_file_comes_first(self):
        root = project(files={"src/billing/invoice.py": "def invoice_total(items):\n    return sum(items)\n",
                              "src/auth/login.py": "def login(user):\n    return True\n",
                              "README.md": "An app.\n"})
        ranked = rank.rank(root, "Invoices should include tax in the invoice total")
        self.assertEqual(ranked[0][0], "src/billing/invoice.py")
        self.assertEqual(rank.rank(root, "the and for"), [])


class IdentityTests(unittest.TestCase):
    def test_member_tokens_and_reviews_post_as_that_member(self):
        root = project()
        text = (root / ".team.toml").read_text().replace('name = "Spark"\nrole = "marketing"',
                                                        'name = "Spark"\ngithub_token_env = "SPARK_GH"\nrole = "marketing"')
        (root / ".team.toml").write_text(text)
        team = load(root)
        with mock.patch.dict(os.environ, {"SPARK_GH": "tok123"}):
            self.assertEqual(github.member_token(team, team.get("Spark")), "tok123")
        self.assertEqual(github.member_token(team, team.get("Atlas")), "")
        calls = []
        with mock.patch.object(github, "gh", lambda *a, **k: calls.append((a, k)) or ""):
            self.assertEqual(github.review("acme/app", 3, True, "ok", "tok123"), "")
        self.assertIn("--approve", calls[0][0])
        self.assertEqual(calls[0][1]["token"], "tok123")


class TemplateTests(unittest.TestCase):
    def test_every_template_gives_a_valid_team(self):
        root = project()
        base = config_io.to_data(load(root))
        for t in templates.TEMPLATES:
            data = templates.apply(base, t["id"])
            change = config_io.plan_change(root, data)
            self.assertTrue(change["valid"], (t["id"], change["error"]))
        full = templates.apply(base, "full-quality")
        self.assertEqual({a["role"] for a in full["agents"]} >= {"security", "qa", "docs"}, True)
        safe = templates.apply(base, "safe-autopilot")
        self.assertEqual((safe["project"]["release"], safe["sandbox"]["mode"]), ("ask", "container"))
        with self.assertRaises(ValueError):
            templates.apply(base, "nope")


class MetricsAndProjectsTests(unittest.TestCase):
    def test_metrics_from_the_records(self):
        root = project()
        log = files.Log(root, "build", "Build: x")
        log.record("Forge: round 1", "built")
        log.record("Atlas: review 1", "no\nVERDICT: CHANGES")
        log.record("Atlas: review 2", "yes\nVERDICT: APPROVED")
        log.f.close()
        log = files.Log(root, "ship", "Ops shift")
        log.record("Harbor: refused", "merge of PR #2: CI is not all green")
        log.record("Harbor: action", "merged PR #1 at abc")
        log.f.close()
        usage.record(root, "Forge", "fake", "m", {"input": 10})
        usage.set_run("")
        m = metrics.compute(load(root))
        today = m["daily"][-1]
        self.assertEqual((today["runs"], today["approved"], today["merged"], today["refused"]), (2, 1, 1, 1))
        self.assertEqual(m["tiles"]["calls_last_hour"], 1)
        self.assertEqual(len(m["hourly"]), 48)
        self.assertTrue(any(f["what"] == "refused" for f in m["feed"]))

    def test_projects_are_remembered_and_summarised(self):
        root = project()
        projects.register(root)
        projects.register(root)
        self.assertEqual(projects.registered().count(str(Path(root).resolve())), 1)
        s = projects.summary(str(Path(root).resolve()))
        self.assertTrue(s["ok"])
        self.assertEqual(s["members"], 4)
        self.assertTrue(projects.forget(root))
        self.assertIn("agent-team-test-config", str(projects._path()))      # never the real config folder


class EvalTests(unittest.TestCase):
    def setUp(self):
        helpers.reset()

    def test_the_fake_release_scenario_and_the_report(self):
        root = project()
        SCRIPTS["Atlas"].append("No 2.0.0 release exists.\nVERDICT: CHANGES")
        with quiet():
            report = evals.run(load(root), ["fake-release"])
        self.assertEqual((report["passed"], report["total"]), (1, 1))
        self.assertEqual(evals.history(root)[-1]["results"][0]["scenario"], "fake-release")

    def test_a_crashing_scenario_fails_without_stopping_the_rest(self):
        root = project()
        SCRIPTS["Atlas"].append("Fine.\nVERDICT: APPROVED")         # the lead wrongly approves
        with quiet():
            report = evals.run(load(root), ["fake-release", "feature"])
        by = {r["scenario"]: r for r in report["results"]}
        self.assertFalse(by["fake-release"]["passed"])
        self.assertFalse(by["feature"]["passed"])
        self.assertIn("error", by["feature"]["detail"])            # no scripted builder replies left


if __name__ == "__main__":
    unittest.main()


class OptionalKeyTests(unittest.TestCase):
    def test_before_a_team_the_key_is_optional(self):
        from agent_team import cli, readiness
        root = tempfile.mkdtemp()
        os.environ.pop("ANTHROPIC_API_KEY", None)
        key = {c.name: c for c in readiness.check(Path(root))}["key ANTHROPIC_API_KEY"]
        self.assertFalse(key.ok)
        self.assertTrue(key.optional)
        self.assertIn("only needed if members will run on Claude", key.detail)

    def test_an_unused_claude_connection_needs_no_key(self):
        from agent_team import readiness
        root = project()        # members on the fake provider
        (root / ".team.toml").write_text((root / ".team.toml").read_text() + '\n[providers.claude]\nkind = "anthropic"\n')
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertNotIn("key ANTHROPIC_API_KEY", {c.name for c in readiness.check(root)})

    def test_init_no_claude_puts_everyone_on_ollama(self):
        from agent_team import cli, config, readiness
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(readiness, "ollama_models", return_value=["qwen3-coder:30b"]), quiet():
            cli.main(["init", "-C", str(root), "--no-claude"])
        team = config.load(root)
        self.assertEqual({team.providers[a.provider].kind for a in team.agents.values()}, {"ollama"})
        self.assertEqual({a.model for a in team.agents.values()}, {"qwen3-coder:30b"})
        self.assertNotIn("claude", team.providers)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with mock.patch.object(readiness, "ollama_models", return_value=["qwen3-coder:30b"]):
            self.assertFalse(any(c.name.startswith("key ") for c in readiness.check(root)))
        with self.assertRaises(SystemExit), quiet():
            cli.main(["init", "-C", str(Path(tempfile.mkdtemp())), "--no-claude", "--builder-provider", "claude"])

    def test_local_only_template(self):
        root = project()
        data = templates.apply(config_io.to_data(load(root)), "local-only")
        self.assertEqual({data["providers"][a["provider"]]["kind"] for a in data["agents"]}, {"ollama"})
        self.assertTrue(config_io.plan_change(root, data)["valid"])
