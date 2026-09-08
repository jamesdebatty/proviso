import unittest

from notify.render import SUBJECT_LIMIT, subject


class SubjectTest(unittest.TestCase):
    def test_short_subject_unchanged(self):
        self.assertEqual(subject("hello"), "hello")

    def test_long_subject_cut_to_limit(self):
        self.assertEqual(len(subject("x" * 200)), SUBJECT_LIMIT)

    def test_cut_subject_ends_with_ellipsis(self):
        self.assertTrue(subject("x" * 200).endswith("…"))
