import unittest
from datetime import date

from recur.monthly import next_monthly, schedule


class NextMonthlyTest(unittest.TestCase):
    def test_mid_month(self):
        self.assertEqual(next_monthly(date(2025, 5, 15)), date(2025, 6, 15))

    def test_first_of_month(self):
        self.assertEqual(next_monthly(date(2025, 1, 1)), date(2025, 2, 1))

    def test_december_rolls_the_year(self):
        self.assertEqual(next_monthly(date(2025, 12, 15)), date(2026, 1, 15))

    def test_january_31_lands_on_last_day_of_february(self):
        self.assertEqual(next_monthly(date(2025, 1, 31)), date(2025, 2, 28))

    def test_august_31_lands_on_last_day_of_september(self):
        self.assertEqual(next_monthly(date(2025, 8, 31)), date(2025, 9, 30))


class ScheduleTest(unittest.TestCase):
    def test_three_dates(self):
        self.assertEqual(
            schedule(date(2025, 3, 10), 3),
            [date(2025, 4, 10), date(2025, 5, 10), date(2025, 6, 10)],
        )
