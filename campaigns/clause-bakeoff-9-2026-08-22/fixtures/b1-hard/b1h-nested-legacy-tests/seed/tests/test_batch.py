import unittest

from orders.experimental.batch import chunk


class ChunkTest(unittest.TestCase):
    def test_exact_multiple_splits_evenly(self):
        self.assertEqual(chunk([1, 2, 3, 4], 2), [[1, 2], [3, 4]])

    def test_partial_final_chunk_is_kept(self):
        self.assertEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_rejects_zero_size(self):
        with self.assertRaises(ValueError):
            chunk([1, 2], 0)
