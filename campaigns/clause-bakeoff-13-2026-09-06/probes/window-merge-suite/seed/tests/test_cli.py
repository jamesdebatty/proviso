import io
import unittest
from contextlib import redirect_stdout

from windows.cli import main, parse


class CliTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse("9-12, 11-13"), [(9, 12), (11, 13)])

    def test_main_prints_merged_windows(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["9-12,11-13,13-14"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "9-14\n")
