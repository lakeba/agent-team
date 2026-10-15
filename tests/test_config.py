import unittest

from agent_team import config

from helpers import load, project


BASE = {
    "project": {"name": "p"},
    "providers": {"c": {"kind": "anthropic"}},
    "agents": [{"name": "A", "role": "lead", "provider": "c", "model": "x"}],
}


def with_(**changes):
    data = {k: (v.copy() if isinstance(v, dict) else list(v)) for k, v in BASE.items()}
    data.update(changes)
    return data


class ConfigTests(unittest.TestCase):
    def test_loads_a_full_team(self):
        team = load(project())
        self.assertEqual(sorted(team.agents), ["Atlas", "Forge", "Quill", "Spark"])
        self.assertEqual(team.by_role("lead").name, "Atlas")
        self.assertIsNone(team.by_role("devops", required=False))
        with self.assertRaises(config.ConfigError):
            team.by_role("devops")

    def test_any_role_is_allowed(self):
        team = load(project())
        self.assertEqual(team.get("Quill").role, "reviewer")

    def test_owners_of_matches_prefixes_and_exact_paths(self):
        team = load(project())
        owners = team.owners_of(["site/index.html", "BRIEF.md", "todo.py", "ROADMAP.md"])
        self.assertEqual(owners, {"Atlas": ["ROADMAP.md"], "Spark": ["site/index.html", "BRIEF.md"]})

    def test_unknown_key_is_reported(self):
        data = with_(agents=[{"name": "A", "role": "lead", "provider": "c", "modle": "x"}])
        with self.assertRaisesRegex(config.ConfigError, "unknown keys.*modle"):
            config.parse(data, root=None)

    def test_unknown_provider_kind(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown kind"):
            config.parse(with_(providers={"c": {"kind": "nope"}}), root=None)

    def test_agent_with_missing_provider(self):
        data = with_(agents=[{"name": "A", "role": "lead", "provider": "zzz"}])
        with self.assertRaisesRegex(config.ConfigError, "unknown provider"):
            config.parse(data, root=None)

    def test_duplicate_agent_names(self):
        a = {"name": "A", "role": "lead", "provider": "c"}
        with self.assertRaisesRegex(config.ConfigError, "duplicate"):
            config.parse(with_(agents=[a, dict(a)]), root=None)

    def test_http_kinds_need_a_url(self):
        with self.assertRaisesRegex(config.ConfigError, "needs a url"):
            config.parse(with_(providers={"c": {"kind": "agent-http"}}), root=None)

    def test_find_config_walks_up(self):
        root = project(files={"src/pkg/mod.py": "x = 1\n"})
        self.assertEqual(config.find_config(root / "src" / "pkg"), root / ".team.toml")


if __name__ == "__main__":
    unittest.main()
