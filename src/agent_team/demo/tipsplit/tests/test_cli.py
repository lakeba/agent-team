import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tipsplit.cli import split  # noqa: E402


class SplitTest(unittest.TestCase):
    def test_even_split_with_tip(self):
        self.assertEqual(split(120, 4, 15), 34.5)

    def test_no_tip(self):
        self.assertEqual(split(90, 3), 30.0)


if __name__ == "__main__":
    unittest.main()
