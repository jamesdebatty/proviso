import unittest

from pricing.lines import calc


class CalcTest(unittest.TestCase):
    def test_plain_line(self):
        self.assertEqual(calc(3, 2.50), 7.50)

    def test_discounted_line(self):
        self.assertEqual(calc(2, 10.00, 0.25), 15.00)
