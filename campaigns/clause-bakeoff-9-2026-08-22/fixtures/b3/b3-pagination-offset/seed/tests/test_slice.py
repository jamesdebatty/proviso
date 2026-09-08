import unittest

from paging.slice import page_slice

ITEMS = list(range(1, 11))


class PageSliceTest(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page_slice(ITEMS, 1, 3), [1, 2, 3])

    def test_second_page(self):
        self.assertEqual(page_slice(ITEMS, 2, 3), [4, 5, 6])

    def test_partial_last_page(self):
        self.assertEqual(page_slice(ITEMS, 4, 3), [10])

    def test_page_past_the_end_is_empty(self):
        self.assertEqual(page_slice(ITEMS, 5, 3), [])

    def test_page_larger_than_the_list(self):
        self.assertEqual(page_slice(ITEMS, 1, 50), ITEMS)
