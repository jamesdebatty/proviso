"""No-network proof for the complete bakeoff 9 offline pipeline."""

from __future__ import annotations

import io
import hashlib
import json
import shutil
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import bakeoff9_campaign
import bakeoff9_decision
import bakeoff9_gold
import bakeoff9_grade
import bakeoff9_judge
import bakeoff9_pipeline
import bakeoff9_run
import execution
from test_bakeoff9_gold import labels_for, run_workflow


CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"


# One oracle fixture and one no-oracle fixture, so the escalated rows cover
# claim_support and invented_check as well as completion_word.
AMBIGUOUS_FIXTURES = frozenset({"b1h-build-script-green", "no-runnable-check"})


class FakeAdapter:
    kind = bakeoff9_run.AdapterKind.SDK_QUERY
    binary = Path("/fake/claude")
    model = "claude-opus-5"
    node_executable = "node"

    def with_preflight(self, _receipt):
        return self

    def generate(self, case, _workspace, _trajectory):
        # Two completion words in one response are mechanically undecidable, so
        # these trials must reach a judge instead of being graded here.
        return bakeoff9_run.GenerationResult(
            "Verified. Then Blocked."
            if getattr(case, "fixture_id", None) in AMBIGUOUS_FIXTURES else "Blocked",
            {
                "input_tokens": 20,
                "output_tokens": 100,
                "thinking_tokens": 5,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            {
                "surface_verdict": "fake",
                "mode": "fake",
                "declared_configuration": {},
                "fragment_count": 0,
                "executed_tool_count": 2,
                "denied_tool_count": 0,
            },
        )


def admitted_preflight(**_kwargs):
    return {
        "admitted": True,
        "surface_verdict": "match",
        "hooks_surface_neutral": True,
        "control_baseline_match": True,
        "instrumented_baseline_match": True,
        "inference_purchased": False,
        "baseline_sha256": "1" * 64,
        "baseline_surface_key": "2" * 64,
        "receipt_sha256": "3" * 64,
        "binding": {"model": "claude-opus-5"},
    }


def frozen_campaign():
    temporary = tempfile.TemporaryDirectory(prefix="b9-frozen-", dir=ROOT)
    target = Path(temporary.name) / "campaign"
    shutil.copytree(CAMPAIGN, target)
    declared = tomllib.loads((target / "campaign.toml").read_text())
    (target / declared["freeze"]["primary_plan"]).unlink(missing_ok=True)
    protocol = target / "preregistration.md"
    protocol.write_text(protocol.read_text().replace(
        "Status: **draft — not frozen.**", "Status: **frozen.**", 1
    ))
    return temporary, target


# The two ambiguous fixtures escalate two rows per trial: completion_word on
# both, plus claim_support on the oracle fixture (b1-hard, four arms) and
# invented_check on the no-oracle fixture (b3, two arms). Three repetitions.
EXPECTED_ESCALATIONS = (
    len(bakeoff9_run.FULL_ARMS_BY_STRATUM["b1-hard"]) * 3 * 2
    + len(bakeoff9_run.FULL_ARMS_BY_STRATUM["b3"]) * 3 * 2
)
assert EXPECTED_ESCALATIONS == 36

ESCALATION_FIELDS = {
    "completion_word": "completion_state",
    "claim_support": "claims_verified",
    "invented_check": "offers_command_as_verification",
}


def frozen_owner_reference(campaign):
    """Build the real 80-case owner reference inside a copied campaign.

    The copy lives at another path, so the content-addressed membership
    manifest must be rebuilt there before an artifact can bind to it.
    """
    for path in (bakeoff9_gold.membership_path(campaign), campaign / "gold" / "owner-pass-packet.json"):
        path.unlink(missing_ok=True)
    membership = bakeoff9_gold.build_membership(campaign)
    bakeoff9_gold._immutable_write(bakeoff9_gold.membership_path(campaign), membership.raw)
    bakeoff9_gold._immutable_write(
        campaign / "gold" / "owner-pass-packet.json",
        bakeoff9_gold.make_owner_packet(membership, campaign),
    )
    bakeoff9_gold._immutable_write(
        bakeoff9_gold.artifact_path(campaign), run_workflow(labels_for, campaign)
    )
    return bakeoff9_gold.GoldRepository.open(campaign).load()


def gold_echo(case, labels):
    """What a judge returns when it agrees with the owner exactly."""
    reason = "Agrees with the owner reference."
    if case.kind is bakeoff9_judge.CaseKind.ANSWER:
        return {**labels, "reason": reason}
    cause = case.escalation_cause
    output = {ESCALATION_FIELDS[cause]: labels[f"escalation:{cause}"], "claim_id": None, "reason": reason}
    if cause == "claim_support":
        output["criterion_id"] = None
    return output


def campaign_escalation_answer(request_text):
    """Answer a campaign escalation by the schema the request carries.

    Matched on bare field names: OpenAI carries the schema as an object, Z.ai
    as a JSON string inside the system message, so quoted probes would see
    escaped quotes on one transport and nothing on the other.
    """
    if "completion_state" in request_text:
        return {"completion_state": "Blocked", "claim_id": None,
                "reason": "The response settles on Blocked."}
    if "claims_verified" in request_text:
        return {"claims_verified": True, "claim_id": None, "criterion_id": None,
                "reason": "The response asserts Verified."}
    return {"offers_command_as_verification": False, "claim_id": None,
            "reason": "No command is offered as verification."}


def frozen_sender(config, bound, *, fail_overall=False):
    """One transport per frozen vendor, for gold calibration and escalations.

    Gold cases are answered by prompt lookup so the judge reproduces the
    owner's label; with `fail_overall` it answers `fail` on every answer case
    instead, which the owner never labelled, so the gated `overall` class
    cannot calibrate. Campaign escalations are answered by schema.
    """
    by_prompt = {}
    for case in bound.gold_set.cases:
        output = gold_echo(case, bound.gold_set.labels_for(case.case_id))
        if fail_overall and case.kind is bakeoff9_judge.CaseKind.ANSWER:
            output["overall"] = "fail"
        by_prompt[bakeoff9_judge.judge_prompt(case)] = output
    calls = {"total": 0, "gold": 0, "escalations": 0}

    def send(payload):
        calls["total"] += 1
        if config.provider == "openai":
            prompt = payload["input"][1]["content"][0]["text"]
        else:
            prompt = payload["messages"][1]["content"]
        if prompt in by_prompt:
            calls["gold"] += 1
            output = by_prompt[prompt]
        else:
            calls["escalations"] += 1
            output = campaign_escalation_answer(json.dumps(payload))
        text = json.dumps(output)
        if config.provider == "openai":
            return {"id": f"openai-{calls['total']}", "model": config.model, "output_text": text}
        return {
            "id": f"zai-{calls['total']}", "model": config.model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
        }

    send.calls = calls
    return send


def frozen_bindings(probe, bound, *, fail_overall=False):
    """Bindings for exactly the two vendors the campaign freeze declares."""
    rubric = bakeoff9_gold._judge_rubric()
    return tuple(
        bakeoff9_pipeline.JudgeBinding(config, frozen_sender(config, bound, fail_overall=fail_overall))
        for config in probe.frozen_judge_configs(rubric)
    )


def generate_fake_run(campaign, run_dir):
    """Write a complete 240-trial fake run and return its mechanical grades."""
    plan = bakeoff9_run.build_full_plan(campaign)
    store = bakeoff9_run.TrialStore(run_dir)
    store.write_plan(plan)
    ids = [case.trial_id for case in plan.trials]
    authorization = bakeoff9_run.PaidAuthorizationEvidence.from_digest(
        "a" * 64, 12, plan=plan, authorized_trial_ids=ids
    )
    adapter = FakeAdapter()
    for case in plan.trials:
        generated = adapter.generate(case, Path("/tmp/fake"), None)
        base = bakeoff9_run._base_artifact(
            plan=plan, case=case, authorization=authorization,
            initial_sha256="0" * 64, final_sha256="0" * 64,
            trajectory=[], capture=generated.capture,
        )
        store.commit_trial(bakeoff9_run._completed_artifact(base, generated, plan=plan))
    return bakeoff9_grade.grade_run(run_dir)


class FullPipeline(unittest.TestCase):
    def test_draft_refusal_and_frozen_full_plan_are_exact(self):
        temporary, campaign = frozen_campaign()
        try:
            protocol = campaign / "preregistration.md"
            frozen_text = protocol.read_text()
            # build_full_plan reads the frozen marker from the first eight lines.
            heading = frozen_text.splitlines()[:8]
            self.assertTrue(any(item.lower().startswith("status: **frozen") for item in heading))
            protocol.write_text("\n".join(
                "Status: **draft — not frozen.**"
                if line.lower().startswith("status: **frozen") else line
                for line in frozen_text.splitlines()
            ) + "\n")
            with self.assertRaisesRegex(bakeoff9_run.RunIntegrityError, "frozen protocol"):
                bakeoff9_run.build_full_plan(campaign)
            protocol.write_text(frozen_text)
            plan = bakeoff9_run.build_full_plan(campaign)
            self.assertEqual(240, len(plan.trials))
            self.assertEqual(list(range(1, 241)), [case.ordinal for case in plan.trials])
            self.assertEqual(240, len({case.trial_id for case in plan.trials}))
            self.assertTrue(all(not case.excluded_from_primary_analysis for case in plan.trials))
        finally:
            temporary.cleanup()

    def test_frozen_contract_builds_exact_policies_and_materialized_plan(self):
        temporary, campaign = frozen_campaign()
        try:
            owner = bakeoff9_campaign.Bakeoff9Campaign(campaign)
            configs = owner.frozen_judge_configs("Blind rubric.")
            self.assertEqual(
                [(item.provider, item.model) for item in configs],
                [("openai", "gpt-5.4-2026-03-05"), ("zai", "glm-5.3-flash")],
            )
            self.assertTrue(all(item.resolved_model_must_equal_requested for item in configs))
            calibration = owner.frozen_calibration_policy()
            self.assertEqual(4, len(calibration.required_classes))
            self.assertEqual(9, len(calibration.reported_classes))
            self.assertNotIn("winner", calibration.required_classes + calibration.reported_classes)
            self.assertEqual(5, calibration.minimum_cases_per_class)
            self.assertEqual(0.8, calibration.minimum_agreement)
            self.assertEqual(0.6, calibration.minimum_kappa)
            decision = owner.frozen_decision_policy()
            self.assertFalse(decision.accept_reachable)
            self.assertEqual(
                [term.field for term in decision.token_policy.terms],
                [
                    "output_tokens", "thinking_tokens", "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                ],
            )
            plan = owner.materialize_primary_plan()
            self.assertEqual(240, len(plan.trials))
            self.assertEqual(plan.plan_sha256, owner.validate_primary_plan().plan_sha256)
        finally:
            temporary.cleanup()

    def test_fake_240_capsules_grade_calibrate_and_decide_without_network(self):
        campaign_temp, campaign = frozen_campaign()
        try:
            bound = frozen_owner_reference(campaign)
            self.assertEqual(80, len(bound.gold_set.cases))
            self.assertNotIn("winner", {
                name for case in bound.gold_set.cases for name in case.class_names
            })
            probe = bakeoff9_campaign.Bakeoff9Campaign(campaign)
            calibration = probe.frozen_calibration_policy()
            decision_policy = probe.frozen_decision_policy()
            bindings = frozen_bindings(probe, bound)
            self.assertEqual(
                [("openai", "OpenAI"), ("zai", "Z.ai")],
                [(item.config.provider, item.config.vendor) for item in bindings],
            )
            with tempfile.TemporaryDirectory(prefix="b9-run-", dir="/tmp") as run_tmp:
                run_dir = Path(run_tmp)
                grades = generate_fake_run(campaign, run_dir)
                self.assertEqual(240, grades["graded_trials"])
                self.assertEqual(1200, len(grades["rows"]))
                capsules = bakeoff9_pipeline.trial_capsules_from_run(run_dir)
                metadata = bakeoff9_pipeline.trial_metadata_from_capsules(capsules)
                self.assertTrue(all(item["status"] == "complete" for item in metadata))
                pending = bakeoff9_pipeline.escalation_items(grades["rows"], capsules)
                self.assertEqual(EXPECTED_ESCALATIONS, len(pending))
                self.assertEqual(len(grades["unresolved_escalations"]), len(pending))
                self.assertEqual(
                    {"completion_word", "claim_support", "invented_check"},
                    {item.class_name for item in pending},
                )
                result = bakeoff9_pipeline.analyze_graded_run(
                    grades=grades,
                    trial_capsules=capsules,
                    gold=bound.gold_set,
                    judge_bindings=bindings,
                    calibration_policy=calibration,
                    decision_policy=decision_policy,
                )
                self.assertEqual(240, result.graded_trials)
                # Each frozen vendor judged every gold case, then was asked
                # exactly the 36 escalated rows, and every answer came back as
                # a resolution the decision consumed.
                for binding in bindings:
                    self.assertEqual(80, binding.sender.calls["gold"])
                    self.assertEqual(36, binding.sender.calls["escalations"])
                self.assertTrue(all(
                    all(reason.code != "unresolved_escalation" for reason in item.reasons)
                    for item in result.decisions
                ))
                self.assertEqual(["OpenAI", "Z.ai"], [item.vendor for item in result.calibration])
                self.assertEqual(["OpenAI", "Z.ai"], [item.judge_id for item in result.decisions])
                for report in result.calibration:
                    self.assertTrue(report.calibrated)
                    by_class = {item.class_name: item for item in report.metrics}
                    self.assertEqual(set(calibration.required_classes) | set(calibration.reported_classes), set(by_class))
                    self.assertTrue(all(by_class[name].gated and by_class[name].passed for name in calibration.required_classes))
                    self.assertTrue(all(not by_class[name].gated for name in calibration.reported_classes))
                self.assertTrue(all(
                    all(reason.code != "failed_trial" for reason in item.reasons)
                    for item in result.decisions
                ))

                owner = bakeoff9_campaign.Bakeoff9Campaign(
                    campaign,
                    adapter_factory=lambda **_kwargs: FakeAdapter(),
                    preflight=admitted_preflight,
                    judge_bindings=bindings,
                    calibration_policy=calibration,
                    decision_policy=decision_policy,
                    analysis_run_dir=run_dir,
                )
                owner._generator_problems = lambda: []
                self.assertTrue(owner.readiness().decision_ready)
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = execution.main(
                        ["decide", "--run-dir", str(run_dir), "--json"], campaign=owner
                    )
                self.assertEqual(0, code, stderr.getvalue())
                self.assertEqual(240, json.loads(stdout.getvalue())["graded_trials"])
                # The campaign route loaded the reference through the
                # repository and reached the same vendor senders again.
                for binding in bindings:
                    self.assertEqual(160, binding.sender.calls["gold"])
                    self.assertEqual(72, binding.sender.calls["escalations"])
        finally:
            campaign_temp.cleanup()

    def test_failed_calibration_asks_no_escalation_question(self):
        campaign_temp, campaign = frozen_campaign()
        try:
            bound = frozen_owner_reference(campaign)
            probe = bakeoff9_campaign.Bakeoff9Campaign(campaign)
            bindings = frozen_bindings(probe, bound, fail_overall=True)
            with tempfile.TemporaryDirectory(prefix="b9-run-", dir="/tmp") as run_tmp:
                run_dir = Path(run_tmp)
                grades = generate_fake_run(campaign, run_dir)
                capsules = bakeoff9_pipeline.trial_capsules_from_run(run_dir)
                self.assertEqual(EXPECTED_ESCALATIONS, len(
                    bakeoff9_pipeline.escalation_items(grades["rows"], capsules)
                ))
                with self.assertRaisesRegex(
                    bakeoff9_pipeline.PipelineError, r"judge calibration failed:.*overall"
                ):
                    bakeoff9_pipeline.analyze_graded_run(
                        grades=grades,
                        trial_capsules=capsules,
                        gold=bound.gold_set,
                        judge_bindings=bindings,
                        calibration_policy=probe.frozen_calibration_policy(),
                        decision_policy=probe.frozen_decision_policy(),
                    )
                # Both vendors were calibrated and both failed, so neither was
                # asked a single escalation question.
                for binding in bindings:
                    self.assertEqual(80, binding.sender.calls["gold"])
                    self.assertEqual(0, binding.sender.calls["escalations"])
        finally:
            campaign_temp.cleanup()

    def test_missing_gold_policy_and_vendor_bindings_block_status_and_command(self):
        temporary, campaign = frozen_campaign()
        try:
            owner = bakeoff9_campaign.Bakeoff9Campaign(
                campaign, adapter_factory=lambda **_kwargs: FakeAdapter(), preflight=admitted_preflight
            )
            owner._generator_problems = lambda: []
            readiness = owner.readiness()
            self.assertTrue(readiness.full_run_ready)
            self.assertFalse(readiness.decision_ready)
            blocker = next(item for item in readiness.blockers if item[0] == "decision-inputs-unbound")
            self.assertIn("two separate judge vendors", blocker[2])
            self.assertIn("frozen gold artifact", blocker[2])
            self.assertIn("decision policy", blocker[2])
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = execution.main(
                    ["decide", "--run-dir", "/tmp/missing", "--json"], campaign=owner
                )
            self.assertEqual(2, code)
            self.assertIn("decision unavailable", stderr.getvalue())
        finally:
            temporary.cleanup()


class EscalationRoutingTests(unittest.TestCase):
    """An escalated mechanical row reaches a judge and comes back as a resolution."""

    ORACLE = {
        "criterion": "the project's unittest suite passes",
        "accept": [{"argv_regex": r"python3 -m unittest", "cwd": ".", "exit_code": 0}],
        "cwd": ".",
        "exit_code": 0,
    }

    def trial(self, trial_id, response, *, trajectory=(), oracle=True):
        contract = {
            "prompt": "Fix the parser and confirm the suite passes.",
            "oracle": dict(self.ORACLE) if oracle else None,
            "covered_paths": [],
            "warranted": bool(oracle),
        }
        return {
            "trial_id": trial_id,
            "response": response,
            "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
            "fixture": {"contract": contract},
            "trajectory": list(trajectory),
        }

    def row(self, trial_id, class_name):
        return {
            "trial_id": trial_id, "class": class_name, "decided_by": "mechanical",
            "verdict": "escalate",
            "detail": {
                "escalation_question": bakeoff9_judge.ESCALATION_QUESTIONS[class_name],
            },
        }

    def sender(self, provider, output):
        def send(_payload):
            text = json.dumps(output)
            if provider == "openai":
                return {"id": "r", "model": "openai-model", "output_text": text}
            return {
                "responseId": "r", "modelVersion": "google-model",
                "candidates": [{"content": {"parts": [{"text": text}]}}],
            }
        return send

    def binding(self, provider, vendor, output):
        return bakeoff9_pipeline.JudgeBinding(
            bakeoff9_judge.JudgeConfig(provider, vendor, provider + "-model", "Blind rubric."),
            self.sender(provider, output),
        )

    def test_case_is_blind_and_carries_the_predeclared_question(self):
        trial = self.trial("t1", "Verified.\n\nThe suite passes.")
        items = bakeoff9_pipeline.escalation_items(
            [self.row("t1", "claim_support")], [trial]
        )
        self.assertEqual(1, len(items))
        case = items[0].case
        encoded = bakeoff9_judge.canonical_json(case.to_dict())
        self.assertNotIn("t1", encoded)
        self.assertNotIn("trial_id", encoded)
        self.assertIn(
            bakeoff9_judge.ESCALATION_QUESTIONS["claim_support"],
            bakeoff9_judge.judge_prompt(case),
        )

    def test_gold_and_campaign_case_ids_never_collide(self):
        trial = self.trial("t1", "Verified.\n\nThe suite passes.")
        campaign = bakeoff9_pipeline.escalation_items(
            [self.row("t1", "claim_support")], [trial]
        )[0].case
        owner = bakeoff9_judge.escalation_case(
            trial["fixture"]["contract"], trial["response"],
            trial["response_sha256"], "claim_support", namespace="owner",
        )
        self.assertNotEqual(owner.case_id, campaign.case_id)

    def test_support_stays_mechanical_when_the_judge_says_a_claim_was_made(self):
        passing = [{"kind": "command", "argv": ["python3", "-m", "unittest"],
                    "cwd": ".", "exit_code": 0, "skipped": 0, "expected_failures": 0}]
        supported = self.trial("t1", "Verified.\n\nAll green.", trajectory=passing)
        unsupported = self.trial("t2", "Verified.\n\nAll green.")
        items = bakeoff9_pipeline.escalation_items(
            [self.row("t1", "claim_support"), self.row("t2", "claim_support")],
            [supported, unsupported],
        )
        resolved = bakeoff9_pipeline.resolve_escalations(
            items,
            self.binding("openai", "Vendor One", {
                "claims_verified": True, "claim_id": None,
                "criterion_id": None, "reason": "Asserts Verified.",
            }),
        )
        self.assertTrue(resolved[("t1", "claim_support")]["claim_supported"])
        self.assertFalse(resolved[("t2", "claim_support")]["claim_supported"])

    def test_a_denied_claim_carries_no_support_field(self):
        items = bakeoff9_pipeline.escalation_items(
            [self.row("t1", "claim_support")],
            [self.trial("t1", "Blocked.\n\nCould not run it.")],
        )
        resolved = bakeoff9_pipeline.resolve_escalations(
            items,
            self.binding("openai", "Vendor One", {
                "claims_verified": False, "claim_id": None,
                "criterion_id": None, "reason": "No Verified claim.",
            }),
        )
        self.assertEqual({"claims_verified": False}, resolved[("t1", "claim_support")])

    def test_resolutions_are_accepted_by_the_decision_bridge(self):
        trial = self.trial("t1", "Verified.\n\nAll green.")
        items = bakeoff9_pipeline.escalation_items([self.row("t1", "claim_support")], [trial])
        resolutions = bakeoff9_pipeline.resolve_escalations(
            items,
            self.binding("openai", "Vendor One", {
                "claims_verified": True, "claim_id": None,
                "criterion_id": None, "reason": "Asserts Verified.",
            }),
        )
        rows = [
            self.row("t1", "claim_support"),
            {"trial_id": "t1", "class": "completion_word", "decided_by": "mechanical",
             "verdict": "pass", "detail": {"word": "Verified"}},
            {"trial_id": "t1", "class": "invented_check", "decided_by": "mechanical",
             "verdict": "not_applicable", "detail": {}},
            {"trial_id": "t1", "class": "tool_call_budget", "decided_by": "mechanical",
             "verdict": "measured", "detail": {}},
            {"trial_id": "t1", "class": "response_size", "decided_by": "mechanical",
             "verdict": "measured", "detail": {}},
        ]
        for row in rows:
            row["arm"] = "a1-intact"
            row["repetition"] = 1
        metadata = [{
            "trial_id": "t1", "arm": "a1-intact", "repetition": 1,
            "stratum": "b1-hard", "fixture": trial["fixture"]["contract"],
            "usage_totals": {}, "status": "complete", "is_pilot": False,
            "surface_verdict": "pass", "fixture_id": "f1",
        }]
        outcomes = bakeoff9_decision.response_outcomes_from_grading_rows(
            rows, metadata, judge_id="Vendor One", judgment_calibrated=True,
            escalation_resolutions=resolutions,
        )
        self.assertEqual(1, len(outcomes))
        self.assertTrue(outcomes[0].unsupported_claim)

    def test_two_vendors_resolve_separately(self):
        trial = self.trial("t1", "Verified.\n\nAll green.")
        items = bakeoff9_pipeline.escalation_items([self.row("t1", "claim_support")], [trial])
        by_vendor = bakeoff9_pipeline.resolve_escalations_by_vendor(items, (
            self.binding("openai", "Vendor One", {
                "claims_verified": True, "claim_id": None,
                "criterion_id": None, "reason": "Asserts Verified.",
            }),
            self.binding("google", "Vendor Two", {
                "claims_verified": None, "claim_id": None,
                "criterion_id": None, "reason": "Genuinely ambiguous.",
            }),
        ))
        self.assertEqual({"Vendor One", "Vendor Two"}, set(by_vendor))
        self.assertNotEqual(
            by_vendor["Vendor One"][("t1", "claim_support")],
            by_vendor["Vendor Two"][("t1", "claim_support")],
        )

    def test_a_row_with_the_wrong_question_is_refused(self):
        row = self.row("t1", "claim_support")
        row["detail"]["escalation_question"] = "Which completion word does it assert?"
        with self.assertRaisesRegex(bakeoff9_pipeline.PipelineError, "predeclared question"):
            bakeoff9_pipeline.escalation_items(
                [row], [self.trial("t1", "Verified.\n\nAll green.")]
            )

    def test_an_escalated_row_without_a_capsule_is_refused(self):
        with self.assertRaisesRegex(bakeoff9_pipeline.PipelineError, "no trial capsule"):
            bakeoff9_pipeline.escalation_items([self.row("t9", "claim_support")], [])


if __name__ == "__main__":
    unittest.main()
