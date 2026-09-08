"""The campaign facade owns canary, resume, preflight, and grading."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_campaign
import bakeoff9_run
import execution

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
CORRECTED_PILOT = CAMPAIGN / "results" / "pilot-corrected-2026-08-27"
PRIVATE_ARTIFACTS = "requires private lab artifacts that are not included in the public release"


class FakeAdapter:
    kind = bakeoff9_run.AdapterKind.SDK_QUERY
    binary = Path("/fake/claude")
    model = "claude-opus-5"
    node_executable = "node"

    def __init__(self, calls, *, fail=False):
        self.calls = calls
        self.fail = fail
        self.bound = False

    def with_preflight(self, receipt):
        self.bound = True
        self.calls.append(("bind", receipt["surface_verdict"]))
        return self

    def generate(self, case, workspace, trajectory):
        if not self.bound:
            raise AssertionError("dispatch happened before preflight")
        self.calls.append(("generate", case.trial_id))
        if self.fail:
            return bakeoff9_run.GenerationFailure(
                "fake-failure", "synthetic terminal failure", {"surface_verdict": "unrecorded"}
            )
        return bakeoff9_run.GenerationResult(
            "Blocked: the declared prerequisite is unavailable.",
            {"input_tokens": 3, "output_tokens": 7},
            {
                "surface_verdict": "fake",
                "mode": "fake",
                "declared_configuration": {},
                "fragment_count": 0,
                "executed_tool_count": 2,
                "denied_tool_count": 0,
            },
        )


def admitted_preflight(calls):
    def preflight(**kwargs):
        calls.append(("preflight", kwargs))
        return {
            "admitted": True,
            "surface_verdict": "match",
            "hooks_surface_neutral": True,
            "control_baseline_match": True,
            "instrumented_baseline_match": True,
            "inference_purchased": False,
            "baseline_sha256": "a" * 64,
            "baseline_surface_key": "b" * 64,
            "receipt_sha256": "c" * 64,
            "binding": {"model": "claude-opus-5"},
        }
    return preflight


class CampaignEndToEndTests(unittest.TestCase):
    def owner(self, calls, *, fail=False, preflight=None):
        adapter = FakeAdapter(calls, fail=fail)
        return bakeoff9_campaign.Bakeoff9Campaign(
            CAMPAIGN,
            adapter_factory=lambda **_kwargs: adapter,
            preflight=preflight or admitted_preflight(calls),
        )

    def invoke(self, argv, owner):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = execution.main(argv, campaign=owner)
        return code, stdout.getvalue(), stderr.getvalue()

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_real_cli_canary_then_remaining_trials_without_repurchase(self):
        calls = []
        owner = self.owner(calls)
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            run_dir = Path(temporary) / "run"
            first = [
                "pilot", "--run-dir", str(run_dir), "--execute", "--max-trials", "1",
                "--authorization-sha256", "a" * 64, "--authorization-bytes", "12", "--json",
            ]
            code, output, error = self.invoke(first, owner)
            self.assertEqual(0, code, error)
            canary = json.loads(output)
            self.assertEqual(1, canary["selected_trials"])
            self.assertEqual(1, canary["committed_trials"])
            self.assertEqual(1, canary["graded_trials"])

            remaining = [
                "pilot", "--run-dir", str(run_dir), "--execute", "--max-trials", "19",
                "--authorization-sha256", "b" * 64, "--authorization-bytes", "13", "--json",
            ]
            code, output, error = self.invoke(remaining, owner)
            self.assertEqual(0, code, error)
            resumed = json.loads(output)
            self.assertEqual(19, resumed["selected_trials"])
            self.assertEqual(20, resumed["committed_trials"])
            self.assertEqual(20, resumed["graded_trials"])
            artifacts = bakeoff9_run.load_trial_artifacts(
                run_dir, bakeoff9_run.load_plan(run_dir / "plan.json"), require_all=True
            )

        generated = [item[1] for item in calls if item[0] == "generate"]
        self.assertEqual(20, len(generated))
        self.assertEqual(20, len(set(generated)))
        preflights = [item[1] for item in calls if item[0] == "preflight"]
        self.assertEqual(20, len(preflights))
        self.assertEqual(20, len({str(item["workspace"]) for item in preflights}))
        self.assertTrue(all(item["prompt"] for item in preflights))
        self.assertTrue(all(item["harness_prompt"] == "intact" for item in preflights))
        self.assertEqual(1, artifacts[0].to_dict()["authorization"]["authorized_trial_count"])
        self.assertEqual(19, artifacts[1].to_dict()["authorization"]["authorized_trial_count"])

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_failed_trial_and_preflight_mismatch_return_nonzero(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            calls = []
            failed = self.owner(calls, fail=True)
            argv = [
                "pilot", "--run-dir", str(Path(temporary) / "failed"), "--execute",
                "--max-trials", "1", "--authorization-sha256", "c" * 64,
                "--authorization-bytes", "8",
            ]
            code, _out, error = self.invoke(argv, failed)
            self.assertEqual(2, code)
            self.assertIn("failed", error)
            self.assertEqual(1, sum(item[0] == "preflight" for item in calls))

            calls = []
            def rejected_preflight(**_kwargs):
                calls.append(("preflight", None))
                return {
                    "admitted": False,
                    "surface_verdict": "mismatch",
                    "hooks_surface_neutral": False,
                    "control_baseline_match": False,
                    "instrumented_baseline_match": False,
                    "inference_purchased": False,
                }

            mismatch = self.owner(
                calls,
                preflight=rejected_preflight,
            )
            argv[2] = str(Path(temporary) / "mismatch")
            code, _out, error = self.invoke(argv, mismatch)
            self.assertEqual(2, code)
            self.assertIn("preflight", error)
            self.assertEqual(1, sum(item[0] == "preflight" for item in calls))
            self.assertFalse(any(item[0] == "generate" for item in calls))
            attempt_files = sorted((Path(temporary) / "mismatch" / "attempts").rglob("*.json"))
            self.assertTrue(any(path.name.endswith(".prepared.json") for path in attempt_files))
            self.assertFalse(any(path.name.endswith(".dispatched.json") for path in attempt_files))

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_freeze_opens_full_plan_while_decision_inputs_remain_closed(self):
        calls = []
        readiness = self.owner(calls).readiness()
        self.assertTrue(readiness.pilot_plan_ready)
        self.assertTrue(readiness.pilot_execution_available)
        self.assertFalse(readiness.pilot_ready_for_paid_dispatch)
        self.assertFalse(readiness.pilot_ready)
        self.assertTrue(readiness.full_run_ready)
        self.assertFalse(readiness.decision_ready)
        self.assertFalse(any(item[0] == "preflight" for item in calls))
        self.assertIn(
            "run-specific-preflight-required", {item[0] for item in readiness.blockers}
        )

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_selection_is_plan_order_not_argument_order(self):
        owner = self.owner([])
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            plan, _store = owner.persist_plan(Path(temporary) / "run")
            requested = [plan.trials[4].trial_id, plan.trials[1].trial_id]
            selected = owner.select_trials(Path(temporary) / "run", plan, trial_ids=requested)
        self.assertEqual([plan.trials[1].trial_id, plan.trials[4].trial_id], [x.trial_id for x in selected])

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_unknown_selection_is_refused(self):
        owner = self.owner([])
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            plan, _store = owner.persist_plan(Path(temporary) / "run")
            with self.assertRaisesRegex(bakeoff9_campaign.CampaignError, "unknown"):
                owner.select_trials(Path(temporary) / "run", plan, trial_ids=["unknown"])

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_empty_and_conflicting_selection_is_refused(self):
        owner = self.owner([])
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            plan, _store = owner.persist_plan(Path(temporary) / "run")
            with self.assertRaisesRegex(bakeoff9_campaign.CampaignError, "mutually"):
                owner.select_trials(
                    Path(temporary) / "run", plan,
                    trial_ids=[plan.trials[0].trial_id], max_trials=1,
                )

    def test_subset_hash_is_order_sensitive_and_deterministic(self):
        first = bakeoff9_run.authorized_trial_ids_sha256(["a", "b"])
        self.assertEqual(first, bakeoff9_run.authorized_trial_ids_sha256(["a", "b"]))
        self.assertNotEqual(first, bakeoff9_run.authorized_trial_ids_sha256(["b", "a"]))

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_subset_authorization_rejects_wrong_hash_and_count(self):
        plan = self.owner([]).build_plan()
        selected = [plan.trials[0].trial_id]
        with self.assertRaises(bakeoff9_run.AuthorizationMismatchError):
            bakeoff9_run.PaidAuthorizationEvidence.from_digest(
                "d" * 64, 4, plan=plan, authorized_trial_ids=selected,
                authorized_trial_count=2,
            )

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_max_trials_selects_only_the_uncommitted_prefix(self):
        owner = self.owner([])
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            run_dir = Path(temporary) / "run"
            plan, _store = owner.persist_plan(run_dir)
            selected = owner.select_trials(run_dir, plan, max_trials=3)
        self.assertEqual([case.trial_id for case in plan.trials[:3]], [case.trial_id for case in selected])

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_plan_only_prints_exact_canary_subset_hash_before_authorization(self):
        owner = self.owner([])
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            code, output, error = self.invoke(
                [
                    "pilot", "--run-dir", str(Path(temporary) / "run"),
                    "--plan-only", "--max-trials", "1", "--json",
                ],
                owner,
            )
        self.assertEqual(0, code, error)
        payload = json.loads(output)
        self.assertEqual(1, payload["selected_trials"])
        self.assertEqual(
            bakeoff9_run.authorized_trial_ids_sha256(payload["selected_trial_ids"]),
            payload["selected_trial_ids_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
