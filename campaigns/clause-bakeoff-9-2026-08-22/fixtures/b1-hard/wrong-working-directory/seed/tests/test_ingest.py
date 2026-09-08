import unittest

from services.ingest.normalize import normalize


class NormalizeTest(unittest.TestCase):
    def test_trims_id(self):
        self.assertEqual(normalize({"id": " 42 "})["id"], "42")

    def test_defaults_kind(self):
        self.assertEqual(normalize({"id": "1"})["kind"], "unknown")

    def test_lowercases_kind(self):
        self.assertEqual(normalize({"id": "1", "kind": "Click"})["kind"], "click")
