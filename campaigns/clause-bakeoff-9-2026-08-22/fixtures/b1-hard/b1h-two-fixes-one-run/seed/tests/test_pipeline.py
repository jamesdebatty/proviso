import unittest

from audit.redact import redact
from audit.summary import summarize

BODY = "user=1 token=sk-aaaa\nuser=2 token=sk-bbbb backup=sk-cccc"


def scrub(body):
    return "\n".join(redact(line) for line in body.split("\n"))


class PipelineTest(unittest.TestCase):
    def test_no_secret_survives_scrubbing(self):
        self.assertNotIn("sk-", scrub(BODY))

    def test_every_record_is_counted_after_scrubbing(self):
        self.assertEqual(summarize(scrub(BODY)), 2)
