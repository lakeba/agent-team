import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_team import files

from helpers import quiet


class WriteFilesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def write(self, text, **kw):
        with quiet():
            return files.write_files(self.root, text, **kw)

    def test_writes_closed_blocks(self):
        self.assertEqual(self.write('<file path="a/b.txt">\nhello\n</file>'), ["a/b.txt"])
        self.assertEqual((self.root / "a/b.txt").read_text(), "hello\n")

    def test_unclosed_block_is_saved_without_the_verdict(self):
        self.write('Review\n<file path="d.txt">\nbody\n\nVERDICT: CHANGES\n')
        self.assertEqual((self.root / "d.txt").read_text(), "body\n")

    def test_unclosed_block_ends_at_the_next_block(self):
        self.assertEqual(self.write('<file path="x">\nX\n\n<file path="y">\nY\n</file>'), ["x", "y"])
        self.assertEqual((self.root / "x").read_text(), "X\n")

    def test_refuses_paths_outside_the_project(self):
        self.assertEqual(self.write('<file path="../escape.txt">\nno\n</file>'), [])
        self.assertFalse((self.root.parent / "escape.txt").exists())

    def test_refuses_git_internals(self):
        self.assertEqual(self.write('<file path=".git/hooks/pre-commit">\nno\n</file>'), [])

    def test_allowed_prefixes(self):
        text = '<file path="PLAN.md">\nok\n</file>\n<file path="todo.py">\nno\n</file>'
        self.assertEqual(self.write(text, allowed=("PLAN.md",)), ["PLAN.md"])
        self.assertFalse((self.root / "todo.py").exists())


class JourneysFileTests(unittest.TestCase):
    """team/behaviour.toml is read with the team file: an invalid one from any member is never saved."""
    GOOD = '[[scenarios]]\nname = "list"\nkind = "terminal"\nrun = "tally list"\n'
    BAD = """[[scenarios]]\nname = "book"\nkind = "browser"\nserve = "flask run"\nurl = "http://127.0.0.1:5000/"\nsteps = [\n  'wait for css "input[value=\\'Jane\\']"',\n]\n"""

    def test_an_invalid_journeys_file_is_held_back(self):
        root = Path(tempfile.mkdtemp())
        with quiet():
            files.write_files(root, f'<file path="team/behaviour.toml">\n{self.GOOD}</file>')
            out = files.write_files(root, f'<file path="team/behaviour.toml">\n{self.BAD}</file>')
        self.assertEqual((root / "team" / "behaviour.toml").read_text(), self.GOOD)   # the old one is kept
        self.assertNotIn("team/behaviour.toml", out)
        self.assertIn("the journeys aren't valid (not valid TOML", out.problems[0])
        with quiet():                                                             # an edit that breaks it too
            out = files.write_files(root, '<edit path="team/behaviour.toml">\n<<<<<<< SEARCH\nrun = "tally list"\n=======\nrun = [\n>>>>>>> REPLACE\n</edit>')
        self.assertEqual((root / "team" / "behaviour.toml").read_text(), self.GOOD)
        self.assertTrue(out.problems)
        with quiet():                                                             # other TOML files aren't its business
            files.write_files(root, '<file path="other.toml">\nnot = [\n</file>')
        self.assertTrue((root / "other.toml").exists())


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for rel in ["app.py", "site/index.html", "node_modules/x.js", ".team/logs/build.md",
                    ".github/workflows/ci.yml", ".env", "img.png"]:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("content", encoding="utf-8")

    def paths(self, text):
        return [line[len('<file path="'):-2] for line in text.splitlines() if line.startswith('<file path="')]

    def test_skips_noise_and_secrets_dirs_but_keeps_github(self):
        self.assertEqual(sorted(self.paths(files.snapshot(self.root))), [".github/workflows/ci.yml", "app.py", "site/index.html"])

    def test_only_and_skip(self):
        self.assertEqual(self.paths(files.snapshot(self.root, only=("site/",))), ["site/index.html"])
        self.assertNotIn("site/index.html", self.paths(files.snapshot(self.root, skip=("site/",))))

    def test_limit(self):
        with self.assertRaisesRegex(ValueError, "over the 10 limit"):
            files.snapshot(self.root, limit=10)


class BuildOutputTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def make(self, *rels):
        for rel in rels:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("content", encoding="utf-8")

    def listed(self):
        return sorted(rel for rel, _ in files.project_files(self.root))

    def test_git_ignored_paths_never_reach_a_prompt(self):
        self.make("src/main.rs", "target/debug/out.d", "notes", "notes-public.md", ".gitignore")
        (self.root / ".gitignore").write_text("target/\nnotes\n")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.assertEqual(self.listed(), [".gitignore", "notes-public.md", "src/main.rs"])

    def test_dotnet_bin_and_obj_are_skipped_without_a_gitignore(self):
        self.make("src/App/App.csproj", "src/App/Program.cs", "src/App/bin/Debug/App.deps.json",
                  "src/App/obj/project.assets.json", "tools/bin/cli.js")
        self.assertEqual(self.listed(), ["src/App/App.csproj", "src/App/Program.cs", "tools/bin/cli.js"])


class MarkerTests(unittest.TestCase):
    def test_last_marker_wins(self):
        text = "VERDICT: CHANGES\n...\nVERDICT: APPROVED\n"
        self.assertEqual(files.last_marker(files.VERDICT_RE, text), "APPROVED")
        self.assertEqual(files.last_marker(files.SIGNOFF_RE, "nothing"), "")


if __name__ == "__main__":
    unittest.main()
