"""The CLI, the package and the Claude Code plugin must carry the same version: the plugin's
version is what makes an installed copy update, and the panel compares it with the CLI's."""
import json
import re
import tomllib
import unittest
from pathlib import Path

import agent_team

ROOT = Path(__file__).resolve().parent.parent


class VersionTests(unittest.TestCase):
    def test_every_copy_of_the_version_matches(self):
        v = agent_team.__version__
        self.assertEqual(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"], v)
        self.assertEqual(json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())["version"], v)
        panel = (ROOT / "plugin/hooks/register.tsx").read_text()
        self.assertEqual(re.search(r"PLUGIN_VERSION = '([^']+)'", panel).group(1), v)
        fixture = (ROOT / "plugin/tests/panel.test.ts").read_text()
        found = set(re.findall(r"(?:^  version: '|agent-team )(\d+\.\d+\.\d+)", fixture, re.M))
        self.assertEqual(found, {v})   # the panel test's sample CLI status, or its version warning fires


if __name__ == "__main__":
    unittest.main()
