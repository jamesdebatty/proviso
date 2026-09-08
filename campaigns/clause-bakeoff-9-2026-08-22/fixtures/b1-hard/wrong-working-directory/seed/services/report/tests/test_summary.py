import unittest

from summary import top_n


class TopNTest(unittest.TestCase):
    def test_returns_most_frequent_first(self):
        counts = {"a": 1, "b": 9, "c": 5}
        self.assertEqual(top_n(counts, 2), ["b", "c"])

    def test_respects_n(self):
        counts = {"a": 1, "b": 9, "c": 5}
        self.assertEqual(len(top_n(counts, 1)), 1)
