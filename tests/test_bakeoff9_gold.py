"""Solo-owner membership, delayed repeat, and reference validation."""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_gold as gold
import bakeoff9_judge as judge


CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
T0 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def labels_for(case, varied):
    if case.kind is judge.CaseKind.ANSWER:
        errors = []
        if varied:
            errors = [{
                "claim_id": case.claims[0].claim_id,
                "criterion_id": case.criteria[0].criterion_id,
                "claim_span": case.claims[0].span,
                "description": "The passage conflicts with the task.",
            }]
        return {
            "task_completion": 4 if varied else 5,
            "focus": 4 if varied else 5,
            "plain_language": 4 if varied else 5,
            "jargon_discipline": 4 if varied else 5,
            "nuance_and_safety": 4 if varied else 5,
            "unnecessary_passages": [case.claims[0].span] if varied else [],
            "unexplained_jargon": ["opaque term"] if varied else [],
            "missing_requirements": ["one required idea"] if varied else [],
            "material_errors": errors,
            "overall": "borderline" if varied else "pass",
        }
    if case.escalation_cause == "completion_word":
        return {"escalation:completion_word": "Verified" if varied else "Blocked"}
    if case.escalation_cause == "claim_support":
        return {"escalation:claim_support": varied}
    return {"escalation:invented_check": varied}


def fill_draft(draft, cases, *, invert=False):
    case_map = {case.case_id: case for case in cases}
    for index, item in enumerate(draft["labels"]):
        item["labels"] = labels_for(case_map[item["case_id"]], (index % 2 == 1) ^ invert)
    return draft


def assert_unfinished_draft_rejected(test, draft, finalize):
    test.assertTrue(all(item["labels"] is None for item in draft["labels"]))
    with test.assertRaises(ValueError):
        finalize(draft)


class SoloOwnerWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.membership = gold.build_membership(CAMPAIGN)
        cls.packet = gold.make_owner_packet(cls.membership, CAMPAIGN)
        cls.owner_id = gold.human_id("owner")
        owner_draft = fill_draft(
            gold.make_owner_draft(cls.membership, cls.packet, cls.owner_id, T0),
            cls.membership.cases,
        )
        cls.owner_raw = gold.finalize_owner_draft(
            owner_draft, cls.membership, cls.packet, T0 + timedelta(minutes=30)
        )
        cls.owner = gold.validate_owner_pass(cls.owner_raw, cls.membership, cls.packet)
        cls.repeat_open = T0 + timedelta(minutes=30, hours=72)
        cls.repeat_packet = gold.make_repeat_packet(
            cls.membership, cls.owner, cls.repeat_open
        )
        repeat_cases = tuple(
            judge.JudgeCase.from_dict(item["case"])
            for item in cls.repeat_packet["cases"]
        )
        repeat_draft = fill_draft(
            gold.make_repeat_draft(cls.membership, cls.owner, cls.repeat_packet),
            repeat_cases, invert=True,
        )
        cls.repeat_raw = gold.finalize_repeat_draft(
            repeat_draft, cls.membership, cls.owner, cls.repeat_packet,
            cls.repeat_open + timedelta(minutes=30),
        )
        cls.repeat = gold.validate_repeat_pass(
            cls.repeat_raw, cls.membership, cls.owner, cls.repeat_packet
        )
        adjudication_draft = gold.make_adjudication_draft(
            cls.membership, cls.owner, cls.repeat
        )
        for item in adjudication_draft["resolutions"]:
            if item["disagreements"]:
                item["rationale"] = "Re-read both observations and retained pass one."
        cls.adjudication_raw = gold.finalize_adjudication_draft(
            adjudication_draft, cls.membership, cls.owner, cls.repeat,
            cls.repeat_open + timedelta(hours=1),
        )
        cls.adjudication = gold.validate_adjudication(
            cls.adjudication_raw, cls.membership, cls.owner, cls.repeat
        )

    def test_membership_is_deterministic_and_repeat_is_exactly_class_balanced(self):
        self.assertEqual(self.membership.raw, gold.build_membership(CAMPAIGN).raw)
        self.assertEqual(80, len(self.membership.cases))
        plan = self.membership.raw["repeat_plan"]
        self.assertEqual(20, len(plan["aliases"]))
        self.assertEqual(
            {
                "answer": 5,
                "escalation:completion_word": 5,
                "escalation:claim_support": 5,
                "escalation:invented_check": 5,
            },
            {name: len(ids) for name, ids in plan["cases_by_cohort"].items()},
        )

    def test_packets_are_blind_and_repeat_uses_fresh_aliases(self):
        gold.validate_owner_packet(self.packet, self.membership, CAMPAIGN)
        encoded = judge.canonical_json(self.packet)
        for field in ("trial_id", "fixture_id", "stratum", "capsule_path", "provenance"):
            self.assertNotIn(f'"{field}"', encoded)
        canonical = {item["canonical_case_id"] for item in self.membership.raw["repeat_plan"]["aliases"]}
        repeated = {item["case"]["case_id"] for item in self.repeat_packet["cases"]}
        self.assertTrue(canonical.isdisjoint(repeated))
        self.assertNotIn("labels", judge.canonical_json(self.repeat_packet))

    def test_repeat_refuses_before_exact_72_hour_gate(self):
        with self.assertRaisesRegex(gold.GoldIntegrityError, "not available before"):
            gold.make_repeat_packet(
                self.membership, self.owner,
                T0 + timedelta(minutes=30, hours=72) - timedelta(seconds=1),
            )
        exact = gold.make_repeat_packet(self.membership, self.owner, self.repeat_open)
        self.assertEqual(self.repeat_packet, exact)

    def test_unanswered_is_distinct_from_an_explicit_ambiguous_label(self):
        owner_draft = gold.make_owner_draft(
            self.membership, self.packet, self.owner_id, T0
        )
        assert_unfinished_draft_rejected(
            self, owner_draft,
            lambda raw: gold.finalize_owner_draft(raw, self.membership, self.packet, T0),
        )
        repeat_draft = gold.make_repeat_draft(
            self.membership, self.owner, self.repeat_packet
        )
        assert_unfinished_draft_rejected(
            self, repeat_draft,
            lambda raw: gold.finalize_repeat_draft(
                raw, self.membership, self.owner, self.repeat_packet, self.repeat_open
            ),
        )

    def test_final_artifact_preserves_originals_and_reports_intra_rater_metrics(self):
        artifact = gold.assemble(
            self.membership, self.packet, self.owner, self.repeat_packet,
            self.repeat, self.adjudication, CAMPAIGN,
        )
        bound = gold.validate_artifact(CAMPAIGN, artifact)
        self.assertEqual(self.owner_raw, artifact["owner_pass"])
        self.assertEqual(self.repeat_raw, artifact["owner_repeat"])
        self.assertEqual(80, len(bound.gold_set.cases))
        self.assertEqual(13, len(bound.intra_rater_report["metrics"]))
        self.assertTrue(all(item["cases"] >= 5 for item in bound.intra_rater_report["metrics"]))
        self.assertTrue(all("undefined_reason" in item for item in bound.intra_rater_report["metrics"]))

    def test_invalid_owner_timing_adjudication_and_hashes_fail_closed(self):
        model = copy.deepcopy(self.owner_raw)
        model["actor"] = {"kind": "model", "id": self.owner_id}
        model["pass_sha256"] = gold._self_hash(model, "pass_sha256")
        with self.assertRaisesRegex(gold.GoldIntegrityError, "human owner"):
            gold.validate_owner_pass(model, self.membership, self.packet)
        early = copy.deepcopy(self.repeat_packet)
        early["opened_at"] = gold._timestamp(self.repeat_open - timedelta(seconds=1))
        early["packet_sha256"] = gold._self_hash(early, "packet_sha256")
        early_repeat = copy.deepcopy(self.repeat_raw)
        early_repeat["packet_sha256"] = early["packet_sha256"]
        early_repeat["repeat_sha256"] = gold._self_hash(early_repeat, "repeat_sha256")
        with self.assertRaisesRegex(gold.GoldIntegrityError, "72-hour"):
            gold.validate_repeat_pass(
                early_repeat, self.membership, self.owner, early
            )
        bad_adjudication = copy.deepcopy(self.adjudication_raw)
        disputed = next(
            item for item in bad_adjudication["resolutions"] if item["disagreements"]
        )
        disputed["disagreements"] = []
        bad_adjudication["adjudication_sha256"] = gold._self_hash(
            bad_adjudication, "adjudication_sha256"
        )
        with self.assertRaisesRegex(gold.GoldIntegrityError, "disagreement"):
            gold.validate_adjudication(
                bad_adjudication, self.membership, self.owner, self.repeat
            )
        drift = copy.deepcopy(self.membership.raw)
        drift["repeat_plan"]["seed"] = 1
        drift["membership_sha256"] = gold._self_hash(drift, "membership_sha256")
        with self.assertRaises(gold.GoldIntegrityError):
            gold.validate_membership(CAMPAIGN, drift)


def run_workflow(labels_fn, campaign_dir=CAMPAIGN):
    """Drive one complete owner chain with a caller-supplied label function."""
    membership = gold.build_membership(campaign_dir)
    packet = gold.make_owner_packet(membership, campaign_dir)
    owner_id = gold.human_id("owner")

    def fill(draft, cases, *, invert=False):
        case_map = {case.case_id: case for case in cases}
        for index, item in enumerate(draft["labels"]):
            item["labels"] = labels_fn(case_map[item["case_id"]], (index % 2 == 1) ^ invert)
        return draft

    owner_raw = gold.finalize_owner_draft(
        fill(gold.make_owner_draft(membership, packet, owner_id, T0), membership.cases),
        membership, packet, T0 + timedelta(minutes=30),
    )
    owner = gold.validate_owner_pass(owner_raw, membership, packet)
    opened = T0 + timedelta(minutes=30, hours=72)
    repeat_packet = gold.make_repeat_packet(membership, owner, opened)
    repeat_cases = tuple(
        judge.JudgeCase.from_dict(item["case"]) for item in repeat_packet["cases"]
    )
    repeat_raw = gold.finalize_repeat_draft(
        fill(gold.make_repeat_draft(membership, owner, repeat_packet), repeat_cases, invert=True),
        membership, owner, repeat_packet, opened + timedelta(minutes=30),
    )
    repeat = gold.validate_repeat_pass(repeat_raw, membership, owner, repeat_packet)
    draft = gold.make_adjudication_draft(membership, owner, repeat)
    for item in draft["resolutions"]:
        if item["disagreements"]:
            item["rationale"] = "Re-read both observations and retained pass one."
    adjudication = gold.validate_adjudication(
        gold.finalize_adjudication_draft(
            draft, membership, owner, repeat, opened + timedelta(hours=1)
        ),
        membership, owner, repeat,
    )
    return gold.assemble(
        membership, packet, owner, repeat_packet, repeat, adjudication, campaign_dir
    )


def pinned(class_name, value):
    def labels_fn(case, varied):
        labels = labels_for(case, varied)
        if class_name in labels:
            labels[class_name] = value
        return labels
    return labels_fn


class DegenerateClassTests(unittest.TestCase):
    """Only the four gated classes must vary; the nine reported ones may not."""

    def test_constant_reported_class_still_assembles(self):
        artifact = run_workflow(pinned("unexplained_jargon", []))
        bound = gold.validate_artifact(CAMPAIGN, artifact)
        metric = next(
            item for item in bound.intra_rater_report["metrics"]
            if item["class_name"] == "unexplained_jargon"
        )
        self.assertEqual(1.0, metric["exact_agreement"])
        self.assertIsNone(metric["cohen_kappa"])
        self.assertIsNotNone(metric["undefined_reason"])

    def test_constant_gated_class_fails_closed(self):
        artifact = run_workflow(pinned("overall", "pass"))
        with self.assertRaisesRegex(gold.GoldIntegrityError, "gated class is degenerate"):
            gold.validate_artifact(CAMPAIGN, artifact)

if __name__ == "__main__":
    unittest.main()
