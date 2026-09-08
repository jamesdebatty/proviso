import unittest

from csvlite.export import export_rows


class ExportTest(unittest.TestCase):
    def test_header_is_first_line(self):
        text = export_rows(["id", "name"], [])
        self.assertEqual(text.splitlines()[0], "id,name")

    def test_one_line_per_row(self):
        text = export_rows(["id"], [(1,), (2,), (3,)])
        self.assertEqual(len(text.splitlines()), 4)
