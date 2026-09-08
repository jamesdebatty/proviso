import os
import unittest

from schedule.convert import to_utc

TZ_TESTS = unittest.skipUnless(
    os.environ.get("RUN_TZ_TESTS"),
    "timezone conversion tests need RUN_TZ_TESTS=1",
)


class ContractTest(unittest.TestCase):
    def test_result_is_within_a_day(self):
        self.assertTrue(0 <= to_utc(600, -420) < 1440)

    def test_result_is_an_integer(self):
        self.assertIsInstance(to_utc(600, -420), int)


@TZ_TESTS
class ConversionTest(unittest.TestCase):
    def test_phoenix_morning(self):
        self.assertEqual(to_utc(600, -420), 1020)

    def test_wraps_across_midnight(self):
        self.assertEqual(to_utc(60, -420), 480)
