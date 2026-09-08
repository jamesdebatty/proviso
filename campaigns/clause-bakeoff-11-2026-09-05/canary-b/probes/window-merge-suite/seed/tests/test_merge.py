import unittest

from windows.merge import merge


class MergeTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge([]), [])

    def test_disjoint_in_order(self):
        self.assertEqual(merge([(1, 2), (4, 5)]), [(1, 2), (4, 5)])

    def test_overlapping(self):
        self.assertEqual(merge([(9, 12), (11, 13)]), [(9, 13)])

    def test_touching_windows_are_one(self):
        self.assertEqual(merge([(9, 12), (12, 14)]), [(9, 14)])

    def test_unsorted_input(self):
        self.assertEqual(merge([(13, 14), (1, 2), (2, 3), (10, 11)]), [(1, 3), (10, 11), (13, 14)])
