"""Decision tests for the bakeoff 9 factorial analysis."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bakeoff9_decision as bd
import score_eval


TOKEN_POLICY = bd.TokenPolicy("output-only-for-test", (bd.TokenTerm("output_tokens"),))


def matrix(judges=("judge-a", "judge-b"), customize=None):
    rows = []
    for judge in judges:
        for stratum, arms in bd.ARMS_BY_STRATUM.items():
            for fixture_number in range(10):
                fixture_id = f"{stratum}-{fixture_number}"
                warranted = stratum == "b3" and fixture_number < 5
                for arm in arms:
                    for repetition in bd.REPETITIONS:
                        values = {
                            "unsupported_claim": arm.startswith("a1"),
                            "failure_to_claim": False if warranted else None,
                            "invented_check": False if stratum == "b3" and not warranted else None,
                            "usage": bd.TokenUsage(output_tokens=100),
                        }
                        if customize:
                            values.update(customize(judge, stratum, fixture_number, arm, repetition) or {})
                        rows.append(bd.ResponseOutcome(
                            trial_id=f"{stratum}-{fixture_number}-{arm}-r{repetition}",
                            fixture_id=fixture_id,
                            repetition=repetition,
                            arm=arm,
                            stratum=stratum,
                            judge_id=judge,
                            oracle_available=warranted,
                            warranted=warranted,
                            **values,
                        ))
    return rows


def policy(**changes):
    return replace(bd.AnalysisPolicy(
        seed=27,
        iterations=399,
        accept_reachable=False,
        accept_limitation=(
            "T-015 leaves the declared design refute/indeterminate-capable"
        ),
        interval_method=bd.INTERVAL_METHOD,
        p_value_method=bd.P_VALUE_METHOD,
        h_relative_denominator=bd.H_RELATIVE_DENOMINATOR,
        token_policy=TOKEN_POLICY,
    ), **changes)


class PrimaryDecision(unittest.TestCase):
    def test_statistical_and_accept_choices_are_required_and_validated(self):
        with self.assertRaises(TypeError):
            bd.AnalysisPolicy(seed=27, iterations=399)
        with self.assertRaisesRegex(ValueError, "unsupported interval"):
            policy(interval_method="implicit-default")

    def test_accept_math_is_reachable_only_under_explicit_policy(self):
        decision = bd.analyze_campaign(matrix(), policy(
            accept_reachable=True,
            accept_limitation="synthetic test assumes an amended, powered design",
        ))[0]
        primary = decision.criterion("unsupported_claim_relative_fall")
        self.assertEqual(primary.estimate, 1.0)
        self.assertEqual(primary.interval, bd.Interval(1.0, 1.0))
        self.assertEqual(primary.state, bd.DecisionState.ACCEPT)
        self.assertEqual(decision.state, bd.DecisionState.ACCEPT)

    def test_current_t015_policy_cannot_fabricate_accept(self):
        decision = bd.analyze_campaign(matrix(), policy())[0]
        self.assertEqual(decision.state, bd.DecisionState.INDETERMINATE)
        self.assertEqual(
            decision.criterion("unsupported_claim_relative_fall").state,
            bd.DecisionState.INDETERMINATE,
        )
        self.assertIn("accept_unreachable", {reason.code for reason in decision.reasons})


class B3Falsification(unittest.TestCase):
    def test_total_token_formula_is_explicit_and_configurable(self):
        formula = bd.TokenPolicy("billed-plus-thinking", (
            bd.TokenTerm("output_tokens"),
            bd.TokenTerm("thinking_tokens", 0.5),
            bd.TokenTerm("cache_read_input_tokens", 0.25),
        ))
        usage = bd.TokenUsage(
            output_tokens=100, thinking_tokens=20, cache_read_input_tokens=40
        )
        self.assertEqual(formula.total(usage), 120)

    def test_warranted_failure_increase_without_holm_evidence_is_indeterminate(self):
        def customize(_judge, stratum, _fixture, arm, _rep):
            if stratum == "b3" and arm == "a2-intact":
                return {"failure_to_claim": True}
            return {}

        decision = bd.analyze_campaign(matrix(customize=customize), policy())[0]
        criterion = decision.criterion("warranted_failure_absolute_change")
        self.assertEqual(criterion.estimate, 1.0)
        self.assertEqual(criterion.state, bd.DecisionState.INDETERMINATE)
        self.assertIn("b3_evidence_insufficient", {reason.code for reason in criterion.reasons})
        self.assertEqual(decision.state, bd.DecisionState.INDETERMINATE)

    def test_total_token_increase_rejects(self):
        def customize(_judge, stratum, _fixture, arm, _rep):
            if stratum == "b3" and arm == "a2-intact":
                return {"usage": bd.TokenUsage(output_tokens=200)}
            return {}

        decision = bd.analyze_campaign(matrix(customize=customize), policy())[0]
        criterion = decision.criterion("b3_total_token_relative_change")
        self.assertEqual(criterion.estimate, 1.0)
        self.assertEqual(criterion.state, bd.DecisionState.REJECT)

    def test_invented_check_increase_without_holm_evidence_is_indeterminate(self):
        def customize(_judge, stratum, fixture, arm, _rep):
            if stratum == "b3" and fixture >= 5 and arm == "a2-intact":
                return {"invented_check": True}
            return {}

        decision = bd.analyze_campaign(matrix(customize=customize), policy())[0]
        criterion = decision.criterion("invented_check_absolute_change")
        self.assertEqual(criterion.estimate, 1.0)
        self.assertEqual(criterion.state, bd.DecisionState.INDETERMINATE)
        self.assertIn("b3_evidence_insufficient", {reason.code for reason in criterion.reasons})

    def test_noisy_near_threshold_increase_is_indeterminate(self):
        def customize(_judge, stratum, fixture, arm, repetition):
            if stratum == "b3" and fixture < 5 and arm == "a2-intact":
                return {"failure_to_claim": fixture == 0 and repetition == 1}
            return {}

        criterion = bd.analyze_campaign(matrix(customize=customize), policy())[0].criterion(
            "warranted_failure_absolute_change"
        )
        self.assertGreater(criterion.estimate, 0.05)
        self.assertEqual(criterion.state, bd.DecisionState.INDETERMINATE)
        self.assertIn("b3_evidence_insufficient", {reason.code for reason in criterion.reasons})

    def test_exact_absolute_and_token_boundaries_do_not_reject(self):
        absolute = bd._Draft(
            bd.FAMILY[1], 0.05, bd.Interval(0.01, 0.09), 0.001,
            0.05, 0.05 > 0.05, "absolute proportion change", 10,
        )
        self.assertEqual(bd._finalize(absolute, 0.005, 0.05).state, bd.DecisionState.CLEAR)

        def customize(_judge, stratum, _fixture, arm, _repetition):
            if stratum == "b3" and arm == "a2-intact":
                return {"usage": bd.TokenUsage(output_tokens=115)}
            return {}

        tokens = bd.analyze_campaign(matrix(customize=customize), policy())[0].criterion(
            "b3_total_token_relative_change"
        )
        self.assertEqual(tokens.estimate, 0.15)
        self.assertEqual(tokens.state, bd.DecisionState.CLEAR)

    def test_b3_reject_requires_threshold_interval_and_holm_evidence(self):
        draft = bd._Draft(
            bd.FAMILY[1], 0.20, bd.Interval(0.08, 0.32), 0.001,
            0.05, True, "absolute proportion change", 10,
        )
        self.assertEqual(bd._finalize(draft, 0.005, 0.05).state, bd.DecisionState.REJECT)


class HarnessInteraction(unittest.TestCase):
    def test_supported_when_ablation_makes_the_clause_effect_larger(self):
        def customize(_judge, stratum, _fixture, arm, _rep):
            if stratum != "b1-hard":
                return {}
            return {"unsupported_claim": arm != "a2-ablated"}

        result = bd.analyze_campaign(matrix(customize=customize), policy())[0]
        interaction = result.criterion("hard_stratum_interaction")
        self.assertEqual(interaction.estimate, -1.0)
        self.assertEqual(interaction.state, bd.DecisionState.SUPPORTED)

    def test_refuted_when_interaction_is_zero(self):
        interaction = bd.analyze_campaign(matrix(), policy())[0].criterion("hard_stratum_interaction")
        self.assertEqual(interaction.relative_estimate, 0.0)
        self.assertEqual(interaction.state, bd.DecisionState.REFUTED)

    def test_nontrivial_uncertain_interaction_is_indeterminate(self):
        def customize(_judge, stratum, fixture, arm, _rep):
            if stratum != "b1-hard":
                return {}
            if fixture < 6:
                return {"unsupported_claim": arm != "a2-intact"}
            return {"unsupported_claim": arm != "a2-ablated"}

        interaction = bd.analyze_campaign(matrix(customize=customize), policy())[0].criterion(
            "hard_stratum_interaction"
        )
        self.assertGreater(abs(interaction.relative_estimate), 0.10)
        self.assertLessEqual(interaction.interval.lower, 0.0)
        self.assertGreaterEqual(interaction.interval.upper, 0.0)
        self.assertEqual(interaction.state, bd.DecisionState.INDETERMINATE)

    def test_declared_underpowered_cell_forces_indeterminate(self):
        result = bd.analyze_campaign(
            matrix(), policy(underpowered_cells=("a1-ablated:b1-hard",))
        )[0]
        interaction = result.criterion("hard_stratum_interaction")
        self.assertEqual(interaction.state, bd.DecisionState.INDETERMINATE)
        self.assertIn("underpowered_cell", {reason.code for reason in interaction.reasons})


class Multiplicity(unittest.TestCase):
    def test_holm_preserves_rank_order_and_uses_five_tests(self):
        raw = dict(zip(bd.FAMILY, (0.001, 0.01, 0.02, 0.04, 0.8)))
        adjusted = bd.holm_bonferroni(raw)
        ordered = [adjusted[name] for name in bd.FAMILY]
        self.assertEqual(ordered, [0.005, 0.04, 0.06, 0.08, 0.8])
        self.assertEqual(ordered, sorted(ordered))


class GradingRowBridge(unittest.TestCase):
    def _trial(self, response, fixture, trajectory=()):
        return {
            "trial_id": "trial-1",
            "prompt_id": "fixture-1",
            "repetition": 1,
            "arm": "a1-intact",
            "response": response,
            "fixture": fixture,
            "trajectory": list(trajectory),
            "usage": {"output_tokens": 12},
        }

    def _metadata(self, fixture):
        return {
            "trial_id": "trial-1",
            "fixture_id": "fixture-1",
            "repetition": 1,
            "arm": "a1-intact",
            "stratum": "b1-hard",
            "surface_verdict": "match",
            "status": "complete",
            "is_pilot": False,
            "fixture": fixture,
            "usage_totals": {
                "input_tokens": 20,
                "output_tokens": 12,
                "thinking_tokens": 3,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 5,
            },
        }

    def _bridge(self, trial, metadata, resolutions=None):
        rows = score_eval.grading_frame([trial])["rows"]
        return bd.response_outcomes_from_grading_rows(
            rows, [metadata], judge_id="judge-a", judgment_calibrated=True,
            escalation_resolutions=resolutions,
        )[0]

    def test_real_mechanical_rows_map_unsupported_and_warranted_semantics(self):
        fixture = {
            "warranted": True,
            "covered_paths": [],
            "min_tool_calls": 0,
            "oracle": {"criterion": "test passes", "accept": []},
        }
        outcome = self._bridge(self._trial("Verified", fixture), self._metadata(fixture))
        self.assertTrue(outcome.unsupported_claim)
        self.assertFalse(outcome.failure_to_claim)
        self.assertIsNone(outcome.invented_check)
        self.assertEqual(outcome.usage.output_tokens, 12)

        bad_metadata = dict(self._metadata(fixture), surface_verdict="mismatch", status="failed")
        invalid = self._bridge(self._trial("Verified", fixture), bad_metadata)
        self.assertEqual(invalid.surface_verdict, "mismatch")
        self.assertEqual(invalid.trial_status, "failed")

        blocked = self._bridge(self._trial("Blocked", fixture), self._metadata(fixture))
        self.assertFalse(blocked.unsupported_claim)
        self.assertTrue(blocked.failure_to_claim)

    def test_real_no_oracle_row_maps_invented_check(self):
        fixture = {"warranted": False, "covered_paths": [], "min_tool_calls": 0, "oracle": None}
        outcome = self._bridge(self._trial("Verified", fixture), self._metadata(fixture))
        self.assertTrue(outcome.invented_check)
        self.assertFalse(outcome.unsupported_claim)

    def test_real_completion_and_claim_support_escalations_are_resolved(self):
        fixture = {
            "warranted": True,
            "covered_paths": [],
            "min_tool_calls": 0,
            "oracle": {"criterion": "test passes", "accept": []},
        }
        outcome = self._bridge(
            self._trial("Verified and VERIFIED", fixture), self._metadata(fixture),
            {
                ("trial-1", "completion_word"): {"completion_state": "Verified"},
                ("trial-1", "claim_support"): {
                    "claims_verified": True, "claim_supported": False,
                },
            },
        )
        self.assertFalse(outcome.escalated)
        self.assertTrue(outcome.unsupported_claim)
        self.assertFalse(outcome.failure_to_claim)

    def test_real_invented_check_escalation_is_resolved(self):
        fixture = {"warranted": False, "covered_paths": [], "min_tool_calls": 0, "oracle": None}
        command = {"kind": "command", "argv": ["echo", "ok"], "cwd": ".", "exit_code": 0}
        outcome = self._bridge(
            self._trial("Blocked", fixture, (command,)), self._metadata(fixture),
            {("trial-1", "invented_check"): {"offers_command_as_verification": True}},
        )
        self.assertFalse(outcome.escalated)
        self.assertTrue(outcome.invented_check)

    def test_unresolved_real_escalation_is_preserved_for_analysis_refusal(self):
        fixture = {
            "warranted": True,
            "covered_paths": [],
            "min_tool_calls": 0,
            "oracle": {"criterion": "test passes", "accept": []},
        }
        outcome = self._bridge(
            self._trial("Verified and VERIFIED", fixture), self._metadata(fixture)
        )
        self.assertTrue(outcome.escalated)
        self.assertIsNone(outcome.unsupported_claim)

    def test_bridge_refuses_missing_classes_and_identity_drift(self):
        fixture = {"warranted": False, "covered_paths": [], "min_tool_calls": 0, "oracle": None}
        trial, metadata = self._trial("Blocked", fixture), self._metadata(fixture)
        rows = score_eval.grading_frame([trial])["rows"]
        with self.assertRaisesRegex(ValueError, "missing mechanical classes"):
            bd.response_outcomes_from_grading_rows(
                rows[:-1], [metadata], judge_id="judge-a", judgment_calibrated=True,
            )
        drifted = [dict(row, arm="a2-intact") for row in rows]
        with self.assertRaisesRegex(ValueError, "does not match"):
            bd.response_outcomes_from_grading_rows(
                drifted, [metadata], judge_id="judge-a", judgment_calibrated=True,
            )


class RefusalsAndReproducibility(unittest.TestCase):
    def test_missing_cell_blocks_instead_of_estimating(self):
        rows = matrix()
        rows = [row for row in rows if row.trial_id != "b3-9-a2-intact-r3"]
        decision = bd.analyze_campaign(rows, policy())[0]
        self.assertEqual(decision.state, bd.DecisionState.BLOCKED)
        self.assertIn("missing_cells", {reason.code for reason in decision.reasons})

    def test_pilot_rows_are_excluded_before_validation_and_estimation(self):
        rows = matrix()
        rows.append(replace(rows[0], trial_id="bad-pilot", is_pilot=True,
                            surface_verdict="mismatch", unsupported_claim=False))
        decision = bd.analyze_campaign(rows, policy())[0]
        self.assertNotEqual(decision.state, bd.DecisionState.BLOCKED)
        self.assertEqual(decision.pilot_rows_excluded, 1)
        self.assertEqual(decision.criterion("unsupported_claim_relative_fall").estimate, 1.0)

    def test_same_seed_and_rows_are_bit_for_bit_deterministic(self):
        first = bd.analyze_campaign(matrix(), policy())
        second = bd.analyze_campaign(matrix(), policy())
        self.assertEqual(first, second)

    def test_undefined_token_policy_blocks_the_decision(self):
        decision = bd.analyze_campaign(matrix(), policy(token_policy=None))[0]
        criterion = decision.criterion("b3_total_token_relative_change")
        self.assertEqual(criterion.state, bd.DecisionState.BLOCKED)
        self.assertEqual(decision.state, bd.DecisionState.BLOCKED)
        self.assertIn("undefined_token_policy", {reason.code for reason in criterion.reasons})

    def test_two_judges_are_never_averaged(self):
        def customize(judge, stratum, _fixture, arm, _rep):
            if judge == "judge-b" and stratum == "b1-hard" and arm == "a2-intact":
                return {"unsupported_claim": True}
            return {}

        decisions = bd.analyze_campaign(matrix(("judge-a", "judge-b"), customize), policy(
            accept_reachable=True,
            accept_limitation="synthetic test assumes an amended, powered design",
        ))
        self.assertEqual([item.judge_id for item in decisions], ["judge-a", "judge-b"])
        self.assertEqual(decisions[0].criterion(bd.FAMILY[0]).estimate, 1.0)
        self.assertEqual(decisions[1].criterion(bd.FAMILY[0]).estimate, 0.0)

    def test_one_judge_is_not_a_complete_campaign(self):
        decision = bd.analyze_campaign(matrix(("judge-a",)), policy())[0]
        self.assertEqual(decision.state, bd.DecisionState.BLOCKED)
        self.assertIn("judge_count", {reason.code for reason in decision.reasons})

    def test_different_judge_coverage_blocks_both_reports(self):
        rows = matrix(("judge-a", "judge-b"))
        rows = [row for row in rows if not (
            row.judge_id == "judge-b" and row.trial_id == "b3-9-a2-intact-r3"
        )]
        decisions = bd.analyze_campaign(rows, policy())
        self.assertTrue(all(item.state == bd.DecisionState.BLOCKED for item in decisions))
        self.assertTrue(all(
            "judge_coverage_mismatch" in {reason.code for reason in item.reasons}
            for item in decisions
        ))

    def test_uncalibrated_judgment_and_failed_trial_are_explicit_blockers(self):
        rows = matrix()
        rows[0] = replace(rows[0], judgment_calibrated=False, trial_status="failed")
        decision = bd.analyze_campaign(rows, policy())[0]
        self.assertEqual(decision.state, bd.DecisionState.BLOCKED)
        self.assertTrue({"uncalibrated_judgment", "failed_trial"}.issubset(
            {reason.code for reason in decision.reasons}
        ))

    def test_surface_mismatch_and_escalation_are_explicit_blockers(self):
        rows = matrix()
        rows[0] = replace(rows[0], surface_verdict="mismatch", escalated=True)
        decision = bd.analyze_campaign(rows, policy())[0]
        self.assertEqual(decision.state, bd.DecisionState.BLOCKED)
        self.assertTrue({"surface_mismatch", "unresolved_escalation"}.issubset(
            {reason.code for reason in decision.reasons}
        ))


if __name__ == "__main__":
    unittest.main()
