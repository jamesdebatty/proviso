import json
import unittest
from pathlib import Path

from timespan.parse import parse_duration

GOLDEN = Path(__file__).resolve().parent / "golden" / "cases.json"


class SingleUnitTest(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(parse_duration("45m"), 2700)

    def test_seconds(self):
        self.assertEqual(parse_duration("30s"), 30)

    def test_hours(self):
        self.assertEqual(parse_duration("2h"), 7200)

    def test_rejects_unitless(self):
        with self.assertRaises(ValueError):
            parse_duration("10")


class GoldenCompoundTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLDEN.is_file():
            raise unittest.SkipTest(
                "golden corpus absent; run python3 tools/make_golden.py"
            )
        cls.cases = json.loads(GOLDEN.read_text())

    def test_hours_and_minutes(self):
        self.assertEqual(parse_duration("1h30m"), self.cases["1h30m"])

    def test_all_three_units(self):
        self.assertEqual(parse_duration("2h5m30s"), self.cases["2h5m30s"])

    def test_zero_hour_component(self):
        self.assertEqual(parse_duration("0h45m"), self.cases["0h45m"])
