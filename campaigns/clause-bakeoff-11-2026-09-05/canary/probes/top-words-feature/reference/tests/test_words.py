import unittest

from tally.words import count_words, top_words


class CountWordsTest(unittest.TestCase):
    def test_counts_and_lowercases(self):
        self.assertEqual(count_words("The cat saw the other cat"), {"the": 2, "cat": 2, "saw": 1, "other": 1})

    def test_punctuation_and_digits_separate_words(self):
        self.assertEqual(count_words("re-run: run2run"), {"re": 1, "run": 3})

    def test_empty_text(self):
        self.assertEqual(count_words(""), {})


class TopWordsTest(unittest.TestCase):
    def test_most_frequent_first(self):
        self.assertEqual(top_words("b a b c a b", 2), [("b", 3), ("a", 2)])

    def test_ties_alphabetical(self):
        self.assertEqual(top_words("x y y x z", 3), [("x", 2), ("y", 2), ("z", 1)])

    def test_n_larger_than_vocabulary(self):
        self.assertEqual(top_words("a b", 5), [("a", 1), ("b", 1)])

    def test_zero_and_empty(self):
        self.assertEqual(top_words("a b", 0), [])
        self.assertEqual(top_words("", 3), [])
