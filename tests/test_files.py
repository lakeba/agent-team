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


class MarkerTests(unittest.TestCase):
    def test_last_marker_wins(self):
        text = "VERDICT: CHANGES\n...\nVERDICT: APPROVED\n"
        self.assertEqual(files.last_marker(files.VERDICT_RE, text), "APPROVED")
        self.assertEqual(files.last_marker(files.SIGNOFF_RE, "nothing"), "")


if __name__ == "__main__":
    unittest.main()
