import unittest

from ledger.balance import running_balance


class RunningBalanceTest(unittest.TestCase):
    def test_charges_lower_balance(self):
        self.assertEqual(running_balance([("charge", 500), ("charge", 250)]), [-500, -750])

    def test_refund_raises_balance(self):
        self.assertEqual(running_balance([("charge", 500), ("refund", 200)]), [-500, -300])

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            running_balance([("gift", 1)])
