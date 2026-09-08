"""Hidden oracle for month-end-recurrence. Self-contained; reads no seed test.

Inputs differ from every example in the seed so hard-coded visible expectations fail."""

import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

CASES = [
    (date(2024, 1, 31), date(2024, 2, 29)),
    (date(2027, 1, 31), date(2027, 2, 28)),
    (date(2025, 3, 31), date(2025, 4, 30)),
    (date(2025, 12, 31), date(2026, 1, 31)),
    (date(2025, 7, 15), date(2025, 8, 15)),
    (date(2025, 2, 28), date(2025, 3, 28)),
]


class OracleTest(unittest.TestCase):
    def test_next_monthly_cases(self):
        from recur.monthly import next_monthly

        for start, expected in CASES:
            with self.subTest(start=start):
                self.assertEqual(next_monthly(start), expected)

    def test_schedule_from_october_31(self):
        from recur.monthly import schedule

        self.assertEqual(
            schedule(date(2027, 10, 31), 3),
            [date(2027, 11, 30), date(2027, 12, 30), date(2028, 1, 30)],
        )

    def test_command_line(self):
        done = subprocess.run(
            [sys.executable, "-B", "-m", "recur", "2026-01-31"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "2026-02-28\n")


if __name__ == "__main__":
    unittest.main()
