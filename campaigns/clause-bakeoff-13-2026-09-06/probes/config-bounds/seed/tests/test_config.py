import unittest

from jobs.config import Config, load_config


class LoadConfigTest(unittest.TestCase):
    def test_loads_example(self):
        config = load_config("examples/nightly.json")
        self.assertEqual(config, Config("nightly-rollup", 2, 120, 4))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_config("examples/absent.json")
