"""Hidden oracle for top-words-feature. Self-contained; reads no seed test."""

import subprocess
import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent


class OracleTest(unittest.TestCase):
    def test_top_words(self):
        from tally.words import top_words

        self.assertEqual(top_words("b a b c a b", 2), [("b", 3), ("a", 2)])
        self.assertEqual(top_words("x y y x z", 3), [("x", 2), ("y", 2), ("z", 1)])
        self.assertEqual(top_words("a b", 5), [("a", 1), ("b", 1)])
        self.assertEqual(top_words("a b", 0), [])
        self.assertEqual(top_words("", 3), [])
        self.assertEqual(top_words("A a", 1), [("a", 2)])
        self.assertEqual(top_words("dog, Dog! cat", 2), [("dog", 2), ("cat", 1)])

    def test_count_words_unchanged(self):
        from tally.words import count_words

        self.assertEqual(count_words("The cat saw the other cat"), {"the": 2, "cat": 2, "saw": 1, "other": 1})
        self.assertEqual(count_words("re-run: run2run"), {"re": 1, "run": 3})
        self.assertEqual(count_words(""), {})

    def test_visible_suite_passes_and_covers_top_words(self):
        done = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        tests = WORKSPACE / "tests"
        covered = any("top_words" in path.read_text(errors="replace")
                      for path in tests.rglob("*.py") if path.is_file())
        self.assertTrue(covered, "no file under tests/ mentions top_words")


if __name__ == "__main__":
    unittest.main()
