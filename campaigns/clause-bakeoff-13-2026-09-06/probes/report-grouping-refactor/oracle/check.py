"""Hidden oracle for report-grouping-refactor. Self-contained; reads no seed data.

Goldens were computed from the seed's functions before any change. The last test
wraps group_by_day and requires each public function to invoke it, which is a
behaviour-level check that survives wrapper layering.
"""

import unittest
from unittest import mock

ROWS = [{'id': '3', 'opened': '2026-01-03 10:00', 'closed': '2026-01-05 09:00', 'team': 'a'}, {'id': '1', 'opened': '2026-01-01 08:00', 'closed': '2026-01-01 09:00', 'team': 'a'}, {'id': '2', 'opened': '2026-01-01 12:00', 'closed': '', 'team': 'b'}, {'id': '4', 'opened': '2026-01-03 11:00', 'closed': '2026-01-05 10:00', 'team': 'b'}]
OPENED = [('2026-01-01', 2), ('2026-01-03', 2)]
CLOSED = [('2026-01-01', 1), ('2026-01-05', 2)]
BACKLOG = [('2026-01-01', 1), ('2026-01-03', 3), ('2026-01-05', 1)]


class OracleTest(unittest.TestCase):
    def test_helper_exists(self):
        from tickets import report

        self.assertTrue(callable(getattr(report, "group_by_day", None)), "group_by_day is missing")

    def test_outputs_unchanged(self):
        from tickets import report

        self.assertEqual(report.opened_per_day(ROWS), OPENED)
        self.assertEqual(report.closed_per_day(ROWS), CLOSED)
        self.assertEqual(report.backlog_per_day(ROWS), BACKLOG)
        self.assertEqual(report.opened_per_day([]), [])
        self.assertEqual(report.closed_per_day([]), [])
        self.assertEqual(report.backlog_per_day([]), [])

    def test_each_function_uses_the_helper(self):
        from tickets import report

        original = report.group_by_day
        for name in ("opened_per_day", "closed_per_day", "backlog_per_day"):
            with self.subTest(function=name):
                calls = []

                def spy(*args, **kwargs):
                    calls.append(name)
                    return original(*args, **kwargs)

                with mock.patch.object(report, "group_by_day", spy):
                    getattr(report, name)(ROWS)
                self.assertTrue(calls, f"{name} did not call group_by_day")


if __name__ == "__main__":
    unittest.main()
