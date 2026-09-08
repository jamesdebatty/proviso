import unittest

from audit.redact import redact


class RedactTest(unittest.TestCase):
    def test_line_without_secret_is_unchanged(self):
        self.assertEqual(redact("user=1 ok"), "user=1 ok")

    def test_single_secret_is_masked(self):
        self.assertEqual(redact("token=sk-aaaa"), "token=[REDACTED]")

    def test_two_distinct_secrets_are_masked(self):
        self.assertEqual(
            redact("token=sk-aaaa backup=sk-bbbb"),
            "token=[REDACTED] backup=[REDACTED]",
        )
