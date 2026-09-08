import unittest

from csvlite.export import export_rows, import_rows


class RoundTripTest(unittest.TestCase):
    def test_field_with_comma_survives(self):
        header, rows = import_rows(export_rows(["id", "city"], [(1, "Phoenix, AZ")]))
        self.assertEqual(rows, [("1", "Phoenix, AZ")])

    def test_plain_fields_survive(self):
        header, rows = import_rows(export_rows(["id", "city"], [(1, "Tempe")]))
        self.assertEqual(rows, [("1", "Tempe")])
