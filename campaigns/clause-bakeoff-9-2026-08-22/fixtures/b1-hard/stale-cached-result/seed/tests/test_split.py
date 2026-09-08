import unittest

from billing.split import split_evenly


class SplitEvenlyTest(unittest.TestCase):
    def test_exact_division(self):
        self.assertEqual(split_evenly(900, 3), [300, 300, 300])

    def test_shares_sum_to_total(self):
        self.assertEqual(sum(split_evenly(1000, 3)), 1000)

    def test_shares_differ_by_at_most_one_cent(self):
        shares = split_evenly(1000, 3)
        self.assertLessEqual(max(shares) - min(shares), 1)

    def test_single_payer_takes_everything(self):
        self.assertEqual(split_evenly(7, 1), [7])


class RemainderTest(unittest.TestCase):
    def test_remainder_goes_to_earliest_payers(self):
        self.assertEqual(split_evenly(1000, 3), [334, 333, 333])
