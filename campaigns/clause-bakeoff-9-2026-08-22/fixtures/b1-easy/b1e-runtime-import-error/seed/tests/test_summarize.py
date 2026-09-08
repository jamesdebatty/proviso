import unittest

from metrics.summarize import mean, percentiles

SAMPLE = [12, 18, 21, 33, 47, 51, 64, 88, 91, 120]


class SummarizeTest(unittest.TestCase):
    def test_mean_of_sample(self):
        self.assertAlmostEqual(mean(SAMPLE), 54.5)

    def test_median_is_p50(self):
        self.assertAlmostEqual(percentiles(SAMPLE, [50])[0], 49.0)

    def test_tail_percentile(self):
        self.assertGreater(percentiles(SAMPLE, [95])[0], 90.0)
