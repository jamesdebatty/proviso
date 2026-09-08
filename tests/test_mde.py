"""Tests for the bakeoff 9 design-sensitivity model (T-015)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import mde


class BetaParams(unittest.TestCase):
    def test_mean_and_icc_round_trip(self):
        a, b = mde.beta_params(0.3, 0.15)
        self.assertAlmostEqual(a / (a + b), 0.3)
        self.assertAlmostEqual(1.0 / (1.0 + a + b), 0.15)

    def test_degenerate_inputs_are_refused(self):
        for mean, icc in ((0.0, 0.1), (1.0, 0.1), (0.3, 0.0), (0.3, 1.0)):
            with self.assertRaises(ValueError):
                mde.beta_params(mean, icc)


class CriticalValues(unittest.TestCase):
    def test_declared_design_uses_nine_degrees_of_freedom(self):
        self.assertEqual(mde.t_crit(mde.TASKS, 0.05), mde.T_CRIT[9][0.05])

    def test_stricter_alpha_is_a_larger_critical_value(self):
        self.assertGreater(mde.t_crit(10, 0.01), mde.t_crit(10, 0.05))

    def test_untabulated_task_count_is_refused(self):
        with self.assertRaises(ValueError):
            mde.t_crit(12, 0.05)


class Power(unittest.TestCase):
    def test_false_positive_rate_matches_the_nominal_level(self):
        """No true effect: the one-sided rejection rate sits at about alpha/2."""
        result = mde.power(0.3, 0.15, 0.0, sims=4000)
        self.assertLess(result["detect_power"], 0.05)

    def test_power_rises_with_the_true_effect(self):
        weak = mde.power(0.3, 0.15, 0.3, sims=1500)["detect_power"]
        strong = mde.power(0.3, 0.15, 0.9, sims=1500)["detect_power"]
        self.assertGreater(strong, weak)

    def test_accept_is_never_more_likely_than_detection(self):
        result = mde.power(0.3, 0.15, 0.5, sims=1500)
        self.assertLessEqual(result["accept_power"], result["detect_power"])

    def test_accept_power_at_the_threshold_stays_near_half_however_large_the_cell(self):
        """The rule needs the estimate to clear the bar the true value sits on."""
        result = mde.power(0.3, 0.15, mde.THRESHOLD, tasks=50, reps=10, sims=2000)
        self.assertGreater(result["detect_power"], 0.90)
        self.assertLess(result["accept_power"], 0.60)

    def test_same_seed_gives_the_same_answer(self):
        first = mde.power(0.3, 0.15, 0.5, sims=500)
        second = mde.power(0.3, 0.15, 0.5, sims=500)
        self.assertEqual(first, second)


class MinimumDetectableEffect(unittest.TestCase):
    def test_declared_design_cannot_resolve_a_low_base_rate(self):
        self.assertIsNone(mde.mde(0.10, 0.15, sims=1000))

    def test_more_repetitions_lower_the_detectable_effect(self):
        few = mde.mde(0.4, 0.15, sims=1000)
        many = mde.mde(0.4, 0.15, reps=10, sims=1000)
        self.assertIsNotNone(few)
        self.assertIsNotNone(many)
        self.assertLess(many, few)


class Heterogeneity(unittest.TestCase):
    def test_identical_tasks_carry_no_between_task_variance(self):
        rates = {f"t{i}": [1, 0, 1, 0] for i in range(5)}
        self.assertEqual(mde.icc_anova(rates)["icc"], 0.0)

    def test_fully_separated_tasks_carry_all_of_it(self):
        rates = {"a": [1, 1, 1], "b": [0, 0, 0], "c": [1, 1, 1], "d": [0, 0, 0]}
        result = mde.icc_anova(rates)
        self.assertAlmostEqual(result["icc"], 1.0)
        self.assertAlmostEqual(result["p0"], 0.5)

    def test_unequal_repetitions_are_refused(self):
        with self.assertRaises(ValueError):
            mde.icc_anova({"a": [1, 0], "b": [1]})


class Bakeoff8Anchor(unittest.TestCase):
    def test_anchor_reads_the_published_judgments(self):
        result = mde.bakeoff8_anchor(judge="sonnet")
        self.assertEqual(result["tasks"], 5)
        self.assertEqual(result["reps"], 5)
        self.assertEqual(result["regime"], "incomparable-to-bakeoff-9")
        self.assertGreaterEqual(result["icc"], 0.0)


if __name__ == "__main__":
    unittest.main()
