"""Hidden oracle for window-merge-suite. Self-contained; reads no seed test.

The prompt forbids editing the tests, so both test files are pinned by sha256
computed from the final seed bytes.
"""

import hashlib
import subprocess
import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PINNED = {
    "tests/test_merge.py": "9c894833d0408503e6db3de71520ae103e0259111de330b3b912e6bf28c4b277",
    "tests/test_cli.py": "6f8f40c4793c92490a75132d881102647f7ce0e84d7f1d28940bffe8781091e9",
}


class OracleTest(unittest.TestCase):
    def test_tests_unchanged(self):
        for rel, expected in PINNED.items():
            with self.subTest(path=rel):
                path = WORKSPACE / rel
                self.assertTrue(path.is_file(), f"{rel} missing")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, f"{rel} modified")

    def test_merge_cases(self):
        from windows.merge import merge

        self.assertEqual(merge([(9, 12), (11, 14), (14, 15)]), [(9, 15)])
        self.assertEqual(merge([(20, 22), (3, 5), (5, 7), (12, 13)]), [(3, 7), (12, 13), (20, 22)])
        self.assertEqual(merge([(1, 10), (2, 3)]), [(1, 10)])
        self.assertEqual(merge([(5, 6)]), [(5, 6)])

    def test_command_line_merges(self):
        done = subprocess.run(
            [sys.executable, "-B", "-m", "windows", "1-3, 2-5 ,7-8,8-9"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "1-5,7-9\n")


if __name__ == "__main__":
    unittest.main()
