"""Distribution: agent-team as an MCP server, `agent-team try`, and templates with ECC's pieces."""
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import load, project, quiet

from agent_team import ecc, mcp_install, mcp_server, packs


class McpServerTest(unittest.TestCase):
    def ask(self, method, params=None, root=None):
        return mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                                 root or Path(tempfile.mkdtemp()))

    def test_initialize_and_tools(self):
        init = self.ask("initialize")["result"]
        self.assertEqual(init["serverInfo"]["name"], "agent-team")
        self.assertIn("instructions", init)
        names = {t["name"] for t in self.ask("tools/list")["result"]["tools"]}
        self.assertIn("team_start_run", names)
        self.assertFalse(any("approve" in n for n in names), "approvals stay with the owner")

    def test_notifications_get_no_reply(self):
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, Path(".")))

    def test_unknown_method(self):
        self.assertEqual(self.ask("nope")["error"]["code"], -32601)

    def test_no_team_is_a_tool_error(self):
        result = self.ask("tools/call", {"name": "team_runs", "arguments": {}})["result"]
        self.assertTrue(result["isError"])
        self.assertIn("agent-team init", result["content"][0]["text"])

    def test_runs_and_bad_workflow(self):
        root = project()
        result = self.ask("tools/call", {"name": "team_runs", "arguments": {}}, root)["result"]
        self.assertEqual(result["structuredContent"], {"runs": []})
        bad = self.ask("tools/call", {"name": "team_start_run", "arguments": {"workflow": "approve"}}, root)["result"]
        self.assertTrue(bad["isError"])

    def test_behaviour(self):
        result = self.ask("tools/call", {"name": "team_behaviour", "arguments": {}}, project())["result"]
        self.assertEqual(result["structuredContent"]["journeys"], [])
        self.assertIsNone(result["structuredContent"]["latest_check"])


class McpInstallTest(unittest.TestCase):
    def test_codex_appends_once(self):
        home = Path(tempfile.mkdtemp())
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(home)}), quiet():
            mcp_install.install("codex", yes=True)
            mcp_install.install("codex", yes=True)
        text = (home / "config.toml").read_text()
        self.assertEqual(text.count("[mcp_servers.agent-team]"), 1)
        self.assertIn("mcp", tomllib.loads(text)["mcp_servers"]["agent-team"]["args"])

    def test_cursor_merges(self):
        home = Path(tempfile.mkdtemp())
        (home / ".cursor").mkdir()
        (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
        with mock.patch.object(Path, "home", return_value=home), quiet():
            mcp_install.install("cursor", yes=True)
        servers = json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]
        self.assertEqual(set(servers), {"other", "agent-team"})


class TryTest(unittest.TestCase):
    def test_replay_demo_builds_and_passes(self):
        folder = Path(tempfile.mkdtemp()) / "demo"
        from agent_team.workflows import try_demo
        with quiet():
            code = try_demo.run("replay", folder=folder)
        self.assertEqual(code, 0)
        self.assertIn("round_up", (folder / "src" / "tipsplit" / "cli.py").read_text())
        self.assertIn("--round", (folder / "src" / "tipsplit" / "cli.py").read_text())


def fake_ecc() -> Path:
    ecc = Path(tempfile.mkdtemp())
    for rel in ("agents/python-reviewer.md", "agents/security-reviewer.md", "agents/code-reviewer.md",
                "agents/tdd-guide.md", "agents/marketing-agent.md"):
        (ecc / rel).parent.mkdir(parents=True, exist_ok=True)
        (ecc / rel).write_text(f"---\nname: {Path(rel).stem}\n---\nReview carefully.\n")
    for name in ("python-patterns", "python-testing", "verification-loop"):
        (ecc / "skills" / name).mkdir(parents=True)
        (ecc / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\nWrite good code.\n")
    (ecc / "LICENSE").write_text("MIT License\nCopyright (c) Affaan Mustafa\n")
    return ecc


class TemplatesTest(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(packs.detect(project(files={"pyproject.toml": ""})).name, "python")
        self.assertEqual(packs.detect(project(files={"package.json": '{"dependencies": {"react": "18"}}'})).name, "react")
        self.assertEqual(packs.detect(project(files={"package.json": "{}"})).name, "typescript")
        self.assertEqual(packs.detect(project(files={"App/App.csproj": ""})).name, "dotnet")
        self.assertEqual(packs.detect(project()).name, "general")

    def test_every_pack_names_real_kinds_of_piece(self):
        for p in packs.PACKS:
            for ref in p.pieces().values():
                self.assertTrue(ref.startswith(("agents/", "skills/")) and (ref.endswith(".md") == ref.startswith("agents/")), ref)

    def test_apply_copies_pieces_and_lists_them(self):
        root = project(files={"pyproject.toml": ""})
        (root / ".team.toml").write_text((root / ".team.toml").read_text() + "\n# kept\n")
        with quiet():
            self.assertEqual(packs.apply(load(root), packs.BY_NAME["python"], str(fake_ecc()), yes=True), 0)
        team = load(root)
        self.assertEqual([str(s) for s in team.agents["Atlas"].skills], ["team/skills/ecc/agents/python-reviewer.md"])
        self.assertEqual([str(s) for s in team.agents["Forge"].skills], ["team/skills/ecc/skills/python-patterns"])
        self.assertTrue((root / "team/skills/ecc/skills/python-patterns/SKILL.md").exists())
        self.assertIn("MIT License", (root / "team/skills/ecc/NOTICE.md").read_text())
        self.assertIn("# kept", (root / ".team.toml").read_text())
        with quiet():   # applying twice changes nothing
            packs.apply(load(root), packs.BY_NAME["python"], str(fake_ecc()), yes=True)
        self.assertEqual(len(load(root).agents["Atlas"].skills), 1)

    def test_add_skill_extends_an_existing_list(self):
        text = '[[agents]]\nname = "Forge"\nrole = "builder"\nskills = ["a.md"]\n\n[[agents]]\nname = "Atlas"\n'
        out = packs.add_skill(text, "Forge", "b.md")
        self.assertIn('skills = ["a.md", "b.md"]', out)
        self.assertTrue(out.endswith('name = "Atlas"\n'))

    def test_not_an_ecc_checkout(self):
        with self.assertRaises(SystemExit):
            ecc.fetch(tempfile.mkdtemp())


if __name__ == "__main__":
    unittest.main()
