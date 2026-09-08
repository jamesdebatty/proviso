import unittest

from inventory.reserve import reserve


class ReserveTest(unittest.TestCase):
    def test_reserve_within_stock(self):
        self.assertEqual(reserve(10, 4), (4, 6))

    def test_reserve_exact_stock(self):
        self.assertEqual(reserve(5, 5), (5, 0))

    def test_reserve_zero(self):
        self.assertEqual(reserve(5, 0), (0, 5))

    def test_rejects_negative_request(self):
        with self.assertRaises(ValueError):
            reserve(5, -1)


class OverdrawTest(unittest.TestCase):
    def test_reserve_more_than_stock_caps_at_stock(self):
        self.assertEqual(reserve(3, 5), (3, 0))

    def test_remaining_never_negative(self):
        _, remaining = reserve(3, 5)
        self.assertGreaterEqual(remaining, 0)
