import unittest

from text.slug import slugify


class SlugifyTest(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(slugify("Release Notes"), "release-notes")

    def test_collapses_runs_of_punctuation(self):
        self.assertEqual(slugify("v2.0 -- final!"), "v2-0-final")

    def test_strips_edges(self):
        self.assertEqual(slugify("  hello  "), "hello")

    def test_empty_input(self):
        self.assertEqual(slugify("!!!"), "")
