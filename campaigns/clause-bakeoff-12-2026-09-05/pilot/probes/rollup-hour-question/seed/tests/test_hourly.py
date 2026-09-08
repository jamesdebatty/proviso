import unittest
from datetime import datetime

from rollup.hourly import bucket, count_by_bucket, render


class BucketTest(unittest.TestCase):
    def test_before_half_past_rounds_down(self):
        self.assertEqual(bucket(datetime(2026, 3, 4, 10, 29, 59)), datetime(2026, 3, 4, 10, 0))

    def test_half_past_rounds_up(self):
        self.assertEqual(bucket(datetime(2026, 3, 4, 10, 30)), datetime(2026, 3, 4, 11, 0))

    def test_late_evening_rounds_into_next_day(self):
        self.assertEqual(bucket(datetime(2026, 3, 4, 23, 59, 59)), datetime(2026, 3, 5, 0, 0))


class ReportTest(unittest.TestCase):
    def test_count_and_render(self):
        events = [datetime(2026, 3, 4, 9, 50), datetime(2026, 3, 4, 10, 10), datetime(2026, 3, 4, 10, 45)]
        self.assertEqual(render(count_by_bucket(events)), "2026-03-04 10:00  2\n2026-03-04 11:00  1")
