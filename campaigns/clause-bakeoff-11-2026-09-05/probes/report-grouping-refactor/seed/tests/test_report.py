import unittest

from tickets.report import backlog_per_day, closed_per_day, load_rows, opened_per_day

ROWS = load_rows("data/tickets.csv")


class ReportTest(unittest.TestCase):
    def test_opened_per_day(self):
        self.assertEqual(opened_per_day(ROWS), [('2026-02-02', 3), ('2026-02-03', 3), ('2026-02-04', 2), ('2026-02-05', 3), ('2026-02-06', 1)])

    def test_closed_per_day(self):
        self.assertEqual(closed_per_day(ROWS), [('2026-02-02', 1), ('2026-02-03', 2), ('2026-02-04', 2), ('2026-02-05', 2), ('2026-02-06', 3)])

    def test_backlog_per_day(self):
        self.assertEqual(backlog_per_day(ROWS), [('2026-02-02', 2), ('2026-02-03', 3), ('2026-02-04', 3), ('2026-02-05', 4), ('2026-02-06', 2)])
