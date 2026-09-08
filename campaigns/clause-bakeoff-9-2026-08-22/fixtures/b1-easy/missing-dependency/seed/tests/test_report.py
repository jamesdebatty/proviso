import unittest

from analytics.report import rollup


class RollupTest(unittest.TestCase):
    def test_sums_amounts(self):
        rows = [{"amount": 3}, {"amount": 4}]
        self.assertEqual(rollup(rows, {"daily": 10})["total"], 7)

    def test_flags_over_threshold(self):
        rows = [{"amount": 30}]
        self.assertTrue(rollup(rows, {"daily": 10})["over"])
