import unittest

from tally.words import count_words


class CountWordsTest(unittest.TestCase):
    def test_counts_and_lowercases(self):
        self.assertEqual(count_words("The cat saw the other cat"), {"the": 2, "cat": 2, "saw": 1, "other": 1})

    def test_punctuation_and_digits_separate_words(self):
        self.assertEqual(count_words("re-run: run2run"), {"re": 1, "run": 3})

    def test_empty_text(self):
        self.assertEqual(count_words(""), {})
