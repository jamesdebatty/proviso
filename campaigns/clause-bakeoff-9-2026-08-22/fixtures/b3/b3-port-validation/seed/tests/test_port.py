import unittest

from netconf.port import parse_port


class ParsePortTest(unittest.TestCase):
    def test_ordinary_port(self):
        self.assertEqual(parse_port("8080"), 8080)

    def test_highest_port(self):
        self.assertEqual(parse_port("65535"), 65535)

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            parse_port("eighty")

    def test_zero_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_port("0")

    def test_negative_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_port("-1")

    def test_above_range_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_port("70000")
