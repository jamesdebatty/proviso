import io
import json
import tempfile
import unittest
from pathlib import Path

from reporting.cli import main


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "samples.txt"
        self.path.write_text("1\n2\n6\n")

    def run_cli(self, *args):
        stream = io.StringIO()
        code = main([str(self.path), *args], stream=stream)
        return code, stream.getvalue()

    def test_text_output(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "total=9.00 mean=3.00 max=6.00")

    def test_text_output_is_one_line(self):
        _, out = self.run_cli()
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_json_output_carries_the_same_numbers(self):
        code, out = self.run_cli("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"total": 9.0, "mean": 3.0, "max": 6.0})

    def test_json_output_is_a_single_object(self):
        _, out = self.run_cli("--json")
        parsed = json.loads(out)
        self.assertEqual(sorted(parsed), ["max", "mean", "total"])
