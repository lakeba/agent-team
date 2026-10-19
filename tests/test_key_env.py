"""A key pasted where a provider's api_key_env (a variable's name) goes is refused and never echoed."""
import subprocess
import unittest
from unittest import mock

from agent_team import config_io, secret_scan
from agent_team.config import ConfigError, key_env_problem

import helpers  # noqa: F401
from helpers import load, project

ANTHROPIC = "sk-ant-api03-" + "Ab3dE5gH7jK9mN1pQ3sT5vX7zA9cD1fG3hJ5kL7"
LONG_TOKEN = "f3Kq9ZxT2LmP8wRv4NcY7bHd6JsG1aE5"           # no prefix, just a long mixed token
BAD = {"sk-": "sk-proj-abc123", "anthropic": ANTHROPIC, "long token": LONG_TOKEN,
       "hyphenated": "abcd-efgh-ijkl-mnop-qrst"}


def with_key_env(root, value):
    path = root / ".team.toml"
    path.write_text(path.read_text().replace('kind = "fake"\n', f'kind = "fake"\napi_key_env = "{value}"\n', 1))
    return root


class KeyEnvValidationTests(unittest.TestCase):
    def test_valid_names_pass(self):
        for name in ("ANTHROPIC_API_KEY", "STUDIO_NODE_TOKEN", "_X", "my_service_token_for_staging",
                     "A_VERY_LONG_ENVIRONMENT_VARIABLE_NAME_FOR_THE_STAGING_NODE"):
            self.assertEqual(key_env_problem(name), "", name)
            self.assertEqual(load(with_key_env(project(), name)).providers["fake"].api_key_env, name)

    def test_keys_and_tokens_are_refused_without_echoing_them(self):
        for label, value in BAD.items():
            with self.assertRaises(ConfigError, msg=label) as cm:
                load(with_key_env(project(), value))
            msg = str(cm.exception)
            self.assertIn("looks like a key or token", msg, label)
            self.assertIn("agent-team keys set", msg)
            self.assertNotIn(value, msg)

    def test_names_that_arent_variables_are_refused(self):
        for value in ("1ABC", "MY KEY", "A" * 101):
            msg = key_env_problem(value)
            self.assertIn("name of an environment variable", msg)
            self.assertNotIn(value, msg)

    def test_dashboard_preview_refuses_and_hides_the_key(self):
        root = project()
        data = config_io.to_data(load(root))
        data["providers"]["fake"]["api_key_env"] = ANTHROPIC
        change = config_io.plan_change(root, data)
        self.assertFalse(change["valid"])
        self.assertIn("looks like a key or token", change["error"])
        for part in ("error", "diff", "text"):
            self.assertNotIn(ANTHROPIC, change[part], part)
        with self.assertRaises(ConfigError) as cm:
            config_io.save(root, data)
        self.assertNotIn(ANTHROPIC, str(cm.exception))
        self.assertNotIn(ANTHROPIC, (root / ".team.toml").read_text())


class KeyEnvSecretScanTests(unittest.TestCase):
    def staged(self, value):
        root = with_key_env(project(), value)
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"], ["add", "-A"]):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        with mock.patch.object(secret_scan.keys, "read", return_value={}):
            return "\n".join(secret_scan.check_staged(root))

    def test_a_key_in_api_key_env_is_flagged(self):
        for value in (LONG_TOKEN, "sk-proj-abc123"):
            found = self.staged(value)
            self.assertIn(".team.toml:", found)
            self.assertIn("api_key_env holds what looks like a key", found)
            self.assertNotIn(value, found)

    def test_a_variable_name_is_not(self):
        self.assertEqual(self.staged("ANTHROPIC_API_KEY"), "")


if __name__ == "__main__":
    unittest.main()
