import unittest

from audit.summary import summarize


class SummarizeTest(unittest.TestCase):
    def test_empty_body(self):
        self.assertEqual(summarize(""), 0)

    def test_trailing_newline(self):
        self.assertEqual(summarize("a\nb\n"), 2)

    def test_no_trailing_newline(self):
        self.assertEqual(summarize("a\nb"), 2)
