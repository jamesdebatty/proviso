import unittest

from batch import chunk


class BatchSmokeTest(unittest.TestCase):
    def test_exact_multiple_splits_evenly(self):
        self.assertEqual(chunk([1, 2, 3, 4], 2), [[1, 2], [3, 4]])

    def test_empty_input(self):
        self.assertEqual(chunk([], 2), [])
