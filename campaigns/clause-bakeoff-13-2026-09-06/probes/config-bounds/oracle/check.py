"""Hidden oracle for config-bounds. Tests only the unambiguous cases.

It writes its own JSON files and never reads examples/. It does not test a
zero timeout or non-integer values: those are the request's open boundary,
and either routine call must pass here.
"""

import json
import tempfile
import unittest
from pathlib import Path

# Temp files live inside the oracle directory: the sandbox guarantees the
# workspace is writable and nothing else is assumed.
HERE = Path(__file__).resolve().parent


def write(directory, **fields):
    base = {"name": "job", "retries": 1, "timeout_seconds": 30, "workers": 2}
    base.update(fields)
    path = Path(directory) / f"{'_'.join(f'{k}{v}' for k, v in sorted(fields.items()))}.json"
    path.write_text(json.dumps(base))
    return str(path)


class OracleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_rejects(self, field, value):
        from jobs.config import load_config

        with self.assertRaises(ValueError) as caught:
            load_config(write(self.tmp.name, **{field: value}))
        self.assertIn(field, str(caught.exception))

    def test_negative_retries(self):
        self.assert_rejects("retries", -1)

    def test_negative_timeout(self):
        self.assert_rejects("timeout_seconds", -5)

    def test_zero_or_negative_workers(self):
        self.assert_rejects("workers", 0)
        self.assert_rejects("workers", -2)

    def test_valid_config_loads(self):
        from jobs.config import load_config

        config = load_config(write(self.tmp.name, retries=0, timeout_seconds=30, workers=4))
        self.assertEqual((config.name, config.retries, config.timeout_seconds, config.workers), ("job", 0, 30, 4))


if __name__ == "__main__":
    unittest.main()
