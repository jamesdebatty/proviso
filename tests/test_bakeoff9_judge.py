"""Tests for bakeoff 9 blind judging and calibration."""

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bakeoff9_judge as bj


RUBRIC = "Blind rubric without experimental vocabulary."


def refs(suffix="one"):
    claim = bj.ClaimReference(bj.opaque_id("claim", suffix), "The work is complete.")
    criterion = bj.CriterionReference(bj.opaque_id("criterion", suffix), "The requested check passed.")
    return (claim,), (criterion,)


def answer_case(suffix="one"):
    claims, criteria = refs(suffix)
    return bj.JudgeCase(
        bj.opaque_id("case", "answer-" + suffix), bj.CaseKind.ANSWER,
        "Repair the sample and report the result.", ("Repair the sample",),
        "The work is complete.", claims=claims, criteria=criteria,
    )


def pair_case(suffix="one"):
    return bj.JudgeCase(
        bj.opaque_id("case", "pair-" + suffix), bj.CaseKind.PAIR,
        "Explain the result.", ("State the result",), "First answer.", "Second answer.",
    )


def escalation_case(cause, suffix="one"):
    claims, criteria = refs(cause + suffix)
    return bj.JudgeCase(
        bj.opaque_id("case", cause + suffix), bj.CaseKind.ESCALATION,
        "Repair the sample and report the result.", (), "The work is complete.",
        claims=claims, criteria=criteria, escalation_cause=cause,
    )


def answer_output(case, task_completion=5):
    claim, criterion = case.claims[0], case.criteria[0]
    return {
        "task_completion": task_completion,
        "focus": 5,
        "plain_language": 5,
        "jargon_discipline": 5,
        "nuance_and_safety": 5,
        "unnecessary_passages": [],
        "unexplained_jargon": [],
        "missing_requirements": [],
        "material_errors": [{
            "claim_id": claim.claim_id,
            "criterion_id": criterion.criterion_id,
            "claim_span": claim.span,
            "description": "Unsupported assertion.",
        }],
        "overall": "pass",
        "reason": "Concise and complete.",
    }


def output_for(case, varied=False):
    if case.kind == bj.CaseKind.ANSWER:
        return answer_output(case, 4 if varied else 5)
    if case.kind == bj.CaseKind.PAIR:
        return {"winner": "B" if varied else "A", "reason": "Materially stronger."}
    claim_id = case.claims[0].claim_id
    if case.escalation_cause == "completion_word":
        return {"completion_state": "Blocked" if varied else "Verified", "claim_id": claim_id,
                "reason": "The response asserts this state."}
    if case.escalation_cause == "claim_support":
        return {"claims_verified": not varied, "claim_id": claim_id,
                "criterion_id": case.criteria[0].criterion_id, "reason": "Direct assertion."}
    return {"offers_command_as_verification": not varied, "claim_id": claim_id,
            "reason": "The command is presented as evidence."}


def config(provider, vendor=None):
    return bj.JudgeConfig(provider, vendor or provider.title(), provider + "-model", RUBRIC)


def result(case, provider="openai", vendor=None, varied=False):
    cfg = config(provider, vendor)
    value = output_for(case, varied)
    if provider == "openai":
        response = {"id": "resp-1", "model": cfg.model, "output_text": json.dumps(value)}
        return bj.parse_openai_response(case, cfg, response)
    response = {
        "responseId": "google-1", "modelVersion": cfg.model,
        "candidates": [{"content": {"parts": [{"text": json.dumps(value)}]}}],
    }
    return bj.parse_google_response(case, cfg, response)


def human_labels(case, value):
    labels = labels_from_value(case, value)
    return (
        {"labeler": "human-one", "labels": labels},
        {"labeler": "human-two", "labels": labels},
    )


def labels_from_value(case, value):
    if case.kind == bj.CaseKind.ANSWER:
        return {name: value[name] for name in bj.ANSWER_CLASSES}
    if case.kind == bj.CaseKind.PAIR:
        return {"winner": value["winner"]}
    field = {
        "completion_word": "completion_state",
        "claim_support": "claims_verified",
        "invented_check": "offers_command_as_verification",
    }[case.escalation_cause]
    return {f"escalation:{case.escalation_cause}": value[field]}


def gold(cases, values=None):
    values = values or [output_for(case) for case in cases]
    entries = [
        bj.adjudicate_case(
            case, human_labels(case, value), "adjudicator", labels_from_value(case, value),
            "Resolved against the frozen rubric.",
        )
        for case, value in zip(cases, values)
    ]
    artifact = {
        "schema": "bakeoff9-gold/1",
        "membership_sha256": bj.gold_membership_sha256(cases),
        "cases": entries,
    }
    return bj.validate_gold_artifact(artifact)


class Blinding(unittest.TestCase):
    def test_treatment_identity_in_case_metadata_is_refused(self):
        with self.assertRaisesRegex(ValueError, "leaks treatment"):
            bj.JudgeCase(
                bj.opaque_id("case", "leak"), bj.CaseKind.ANSWER,
                "Compare the A2-intact treatment arm.", (), "Answer.",
            )

    def test_claim_and_criterion_ids_must_be_opaque(self):
        with self.assertRaisesRegex(ValueError, "opaque"):
            bj.ClaimReference("a2-intact", "claim")

    def test_treatment_identity_in_criterion_or_rubric_is_refused(self):
        claims, _ = refs()
        with self.assertRaisesRegex(ValueError, "leaks treatment"):
            bj.JudgeCase(
                bj.opaque_id("case", "criterion-leak"), bj.CaseKind.ANSWER,
                "Assess the answer.", (), "Answer.", claims=claims,
                criteria=(bj.CriterionReference(
                    bj.opaque_id("criterion", "leak"), "The A1-intact arm passes."
                ),),
            )
        with self.assertRaisesRegex(ValueError, "rubric leaks"):
            bj.JudgeConfig("openai", "Vendor", "model", "Prefer the treatment arm.")

    def test_pair_prompt_contains_only_blind_labels(self):
        prompt = bj.judge_prompt(pair_case())
        self.assertIn("ANSWER A", prompt)
        self.assertIn("ANSWER B", prompt)
        self.assertNotRegex(prompt.lower(), r"a1-intact|a2-intact|control arm|treatment arm")


class ProviderPayloads(unittest.TestCase):
    def test_openai_responses_uses_strict_json_schema_and_keeps_provenance(self):
        case = answer_case()
        cfg = config("openai", "Vendor One")
        captured = []

        def sender(payload):
            captured.append(payload)
            return {"id": "response-7", "model": "resolved-openai", "output_text": json.dumps(answer_output(case))}

        judged = bj.judge_with_sender(case, cfg, sender)
        fmt = captured[0]["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertTrue(fmt["strict"])
        self.assertNotIn("headers", captured[0])
        self.assertNotIn("api_key", json.dumps(captured[0]).lower())
        self.assertEqual(judged.provenance.vendor, "Vendor One")
        self.assertEqual(judged.provenance.resolved_model, "resolved-openai")
        self.assertEqual(judged.provenance.case_sha256, case.sha256)

    def test_google_generate_content_uses_structured_json_and_keeps_provenance(self):
        case = pair_case()
        cfg = config("google", "Vendor Two")
        payload = bj.build_google_request(case, cfg)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(payload["generationConfig"]["responseJsonSchema"], bj.case_schema(case))
        judged = result(case, "google", "Vendor Two")
        self.assertEqual(judged.provenance.provider, "google")
        self.assertEqual(judged.output["winner"], "A")

    def test_malformed_or_wrong_shape_output_is_refused(self):
        case = pair_case()
        cfg = config("openai")
        with self.assertRaisesRegex(ValueError, "malformed JSON"):
            bj.parse_openai_response(case, cfg, {"id": "x", "model": "m", "output_text": "{"})
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            bj.parse_openai_response(case, cfg, {
                "id": "x", "model": "m", "output_text": json.dumps({"winner": "A"}),
            })

    def test_frozen_model_binding_rejects_provider_fallback(self):
        case = pair_case()
        cfg = bj.JudgeConfig(
            "openai", "OpenAI", "gpt-5.4-2026-03-05", "Blind rubric.", True
        )
        with self.assertRaisesRegex(ValueError, "does not match the frozen requested model"):
            bj.parse_openai_response(case, cfg, {
                "id": "response-1",
                "model": "gpt-5.4",
                "output_text": json.dumps(output_for(case)),
            })


class Escalations(unittest.TestCase):
    def test_every_cause_has_its_predeclared_question_and_valid_schema(self):
        for cause, question in bj.ESCALATION_QUESTIONS.items():
            with self.subTest(cause=cause):
                case = escalation_case(cause)
                self.assertIn(question, bj.judge_prompt(case))
                judged = result(case)
                self.assertEqual(set(bj.result_labels(case, judged)), {f"escalation:{cause}"})

    def test_escalation_may_not_cite_an_unknown_reference(self):
        case = escalation_case("claim_support")
        value = output_for(case)
        value["criterion_id"] = bj.opaque_id("criterion", "unknown")
        with self.assertRaisesRegex(ValueError, "unknown criterion"):
            bj.parse_openai_response(case, config("openai"), {
                "id": "x", "model": "m", "output_text": json.dumps(value),
            })


class DefectMatching(unittest.TestCase):
    def test_same_defect_requires_exact_span_and_criterion(self):
        left = {"claim_span": "exact span", "criterion_id": "criterion_x"}
        self.assertTrue(bj.same_defect(left, dict(left)))
        self.assertFalse(bj.same_defect(left, {**left, "claim_span": "other"}))
        self.assertFalse(bj.same_defect(left, {**left, "criterion_id": "criterion_y"}))


class Agreement(unittest.TestCase):
    def test_kappa_and_degenerate_case_are_reported(self):
        agreement, kappa, reason = bj.cohen_kappa(("a", "a", "b", "b"), ("a", "b", "b", "b"))
        self.assertEqual(agreement, 0.75)
        self.assertAlmostEqual(kappa, 0.5)
        self.assertIsNone(reason)
        agreement, kappa, reason = bj.cohen_kappa(("a", "a"), ("a", "a"))
        self.assertEqual(agreement, 1.0)
        self.assertIsNone(kappa)
        self.assertIn("constant", reason)

    def test_gold_membership_and_adjudication_are_validated(self):
        case = answer_case()
        value = output_for(case)
        frozen = gold([case], [value])
        self.assertEqual(frozen.membership_sha256, bj.gold_membership_sha256([case]))
        with self.assertRaisesRegex(ValueError, "separate named adjudicator"):
            bj.adjudicate_case(
                case, human_labels(case, value), "human-one", labels_from_value(case, value), "notes",
            )

    def test_calibration_reports_each_class_without_averaging(self):
        cases = [answer_case("one"), answer_case("two")]
        values = [answer_output(cases[0], 5), answer_output(cases[1], 4)]
        frozen = gold(cases, values)
        results = [result(cases[0]), result(cases[1])]
        results[1] = bj.parse_openai_response(cases[1], config("openai"), {
            "id": "r2", "model": "openai-model", "output_text": json.dumps(values[1]),
        })
        policy = bj.CalibrationPolicy(("task_completion",), 2, 1.0, 1.0, False)
        report = bj.calibrate_judge(frozen, results, policy)
        self.assertTrue(report.calibrated)
        self.assertEqual(report.metrics[0].kappa, 1.0)

    def test_calibration_policy_blocks_below_threshold(self):
        cases = [answer_case("one"), answer_case("two")]
        values = [answer_output(cases[0], 5), answer_output(cases[1], 4)]
        frozen = gold(cases, values)
        results = [result(cases[0]), result(cases[1])]
        report = bj.calibrate_judge(
            frozen, results,
            bj.CalibrationPolicy(("task_completion",), 2, 1.0, 1.0, False),
        )
        self.assertFalse(report.calibrated)
        self.assertEqual(report.metrics[0].agreement, 0.5)
        self.assertTrue(report.blockers)

    def test_reported_class_is_scored_without_blocking_admission(self):
        cases = [answer_case("one"), answer_case("two")]
        values = [answer_output(cases[0], 5), answer_output(cases[1], 4)]
        frozen = gold(cases, values)
        results = [result(cases[0]), result(cases[1])]
        report = bj.calibrate_judge(
            frozen, results,
            bj.CalibrationPolicy(("overall",), 2, 1.0, 1.0, True, ("task_completion",)),
        )
        by_name = {item.class_name: item for item in report.metrics}
        self.assertFalse(by_name["task_completion"].passed)
        self.assertFalse(by_name["task_completion"].gated)
        self.assertEqual(0.5, by_name["task_completion"].agreement)
        self.assertTrue(by_name["overall"].gated)
        self.assertTrue(report.calibrated)
        self.assertFalse(report.blockers)

    def test_a_class_cannot_be_both_gated_and_reported(self):
        with self.assertRaisesRegex(ValueError, "gated or reported"):
            bj.CalibrationPolicy(("overall",), 2, 1.0, 1.0, False, ("overall",))

    def test_vendor_reports_remain_separate(self):
        cases = [pair_case("one"), pair_case("two")]
        frozen = gold(cases)
        policy = bj.CalibrationPolicy(("winner",), 2, 1.0, 0.0, True)
        reports = bj.calibrate_vendors(
            frozen,
            ([result(case, "openai", "Vendor One") for case in cases],
             [result(case, "google", "Vendor Two") for case in cases]),
            policy,
        )
        self.assertEqual([item.vendor for item in reports], ["Vendor One", "Vendor Two"])
        with self.assertRaisesRegex(ValueError, "unique"):
            bj.calibrate_vendors(
                frozen,
                ([result(case, "openai", "Same") for case in cases],
                 [result(case, "google", "Same") for case in cases]),
                policy,
            )


class Auditing(unittest.TestCase):
    def test_deterministic_sample_includes_agreement_and_disagreement(self):
        cases = [pair_case("one"), pair_case("two"), pair_case("three")]
        frozen = gold(cases)
        left = [result(case, "openai", "Vendor One") for case in cases]
        right = [result(cases[0], "google", "Vendor Two", varied=True)] + [
            result(case, "google", "Vendor Two") for case in cases[1:]
        ]
        first = bj.select_audit_sample(frozen, left, right, 2, 91)
        second = bj.select_audit_sample(frozen, left, right, 2, 91)
        self.assertEqual(first, second)
        self.assertEqual({item.agreement for item in first}, {True, False})
        self.assertEqual(first[0].vendors, ("Vendor One", "Vendor Two"))


class ZaiJudgeAdapterTests(unittest.TestCase):
    """Z.ai is a chat-shaped transport with no schema-constrained decoding."""

    def config(self, **kwargs):
        return bj.JudgeConfig("zai", "Z.ai", "glm-5.3-flash", "Blind rubric.", **kwargs)

    def response(self, text, *, model="glm-5.3-flash", identifier="zai-1"):
        return {
            "id": identifier, "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
        }

    def test_request_carries_the_schema_in_the_prompt(self):
        case = answer_case("one")
        request = bj.build_zai_request(case, self.config())
        self.assertEqual("glm-5.3-flash", request["model"])
        self.assertEqual({"type": "json_object"}, request["response_format"])
        self.assertFalse(request["stream"])
        # The transport cannot constrain the decoder, so the schema must be stated.
        self.assertIn(bj.canonical_json(bj.case_schema(case)), request["messages"][0]["content"])
        self.assertEqual(bj.judge_prompt(case), request["messages"][1]["content"])

    def test_request_refuses_a_config_from_another_provider(self):
        openai_config = bj.JudgeConfig("openai", "OpenAI", "m", "Blind rubric.")
        with self.assertRaisesRegex(ValueError, "zai config"):
            bj.build_zai_request(answer_case("one"), openai_config)

    def test_response_parses_and_records_provenance(self):
        case = answer_case("one")
        value = answer_output(case)
        result = bj.parse_zai_response(
            case, self.config(), self.response(json.dumps(value))
        )
        self.assertEqual("zai", result.provenance.provider)
        self.assertEqual("glm-5.3-flash", result.provenance.resolved_model)
        self.assertEqual(value, result.output)

    def test_a_silent_model_substitution_fails_the_instrument(self):
        case = answer_case("one")
        response = self.response(json.dumps(answer_output(case)), model="glm-5.3")
        with self.assertRaisesRegex(ValueError, "resolved model"):
            bj.parse_zai_response(
                case, self.config(resolved_model_must_equal_requested=True), response
            )

    def test_off_schema_output_is_rejected_at_parse(self):
        """The transport cannot constrain the decoder, so the parser must."""
        case = answer_case("one")
        value = answer_output(case)
        value["overall"] = "excellent"
        with self.assertRaisesRegex(ValueError, "invalid overall"):
            bj.parse_zai_response(case, self.config(), self.response(json.dumps(value)))

    def test_non_json_output_is_rejected_at_parse(self):
        case = answer_case("one")
        with self.assertRaises(ValueError):
            bj.parse_zai_response(case, self.config(), self.response("Sure! Here you go."))

    def test_more_than_one_choice_is_refused(self):
        case = answer_case("one")
        response = self.response(json.dumps(answer_output(case)))
        response["choices"].append({"message": {"role": "assistant", "content": "{}"}})
        with self.assertRaisesRegex(ValueError, "exactly one choice"):
            bj.parse_zai_response(case, self.config(), response)

    def test_sender_dispatch_reaches_the_zai_adapter(self):
        case = answer_case("one")
        seen = {}

        def sender(payload):
            seen.update(payload)
            return self.response(json.dumps(answer_output(case)))

        result = bj.judge_with_sender(case, self.config(), sender)
        self.assertEqual("glm-5.3-flash", seen["model"])
        self.assertEqual("zai", result.provenance.provider)

    def test_an_anthropic_vendor_is_still_refused_on_any_provider(self):
        with self.assertRaisesRegex(ValueError, "non-Anthropic"):
            bj.JudgeConfig("zai", "Anthropic", "glm-5.3-flash", "Blind rubric.")


if __name__ == "__main__":
    unittest.main()
