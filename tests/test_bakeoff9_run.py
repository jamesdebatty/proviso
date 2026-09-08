"""Immutable bakeoff 9 plan, authorization, trial, and resume behavior."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_run as run
import score_eval

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
CORRECTED_PILOT = CAMPAIGN / "results" / "pilot-corrected-2026-08-27"
PRIVATE_ARTIFACTS = "requires private lab artifacts that are not included in the public release"


class FakeAdapter:
    kind = run.AdapterKind.SDK_QUERY

    def __init__(self):
        self.calls = 0

    def generate(self, case, workspace, trajectory):
        self.calls += 1
        trajectory.run_command(
            "shell-edit",
            [
                sys.executable,
                "-c",
                "from pathlib import Path; p=Path('scripts/check_auth.py'); p.write_text(p.read_text()+'\\n')",
            ],
        )
        return run.GenerationResult(
            response="Blocked: the staging authentication input is unavailable.",
            usage={"input_tokens": 10, "output_tokens": 8},
            capture={
                "surface_verdict": "fake",
                "mode": "fake",
                "declared_configuration": {},
                "fragment_count": 2,
            },
        )


class CrashingAdapter:
    kind = run.AdapterKind.SDK_QUERY

    def generate(self, case, workspace, trajectory):
        raise RuntimeError("synthetic crash after dispatch")


class ConclusiveFailureAdapter:
    kind = run.AdapterKind.SDK_QUERY

    def generate(self, case, workspace, trajectory):
        return run.GenerationFailure(
            "provider-refused",
            "provider returned a terminal refusal",
            {"surface_verdict": "unrecorded"},
        )


class IncompleteFailureAdapter:
    kind = run.AdapterKind.SDK_QUERY

    def generate(self, case, workspace, trajectory):
        trajectory.begin_command("unfinished", ["cat", "missing"])
        return run.GenerationFailure(
            "adapter-refused",
            "original sanitized adapter failure",
            {"surface_verdict": "unrecorded"},
        )


@unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
class PilotPlanTests(unittest.TestCase):
    def test_plan_is_the_exact_deterministic_twenty_case_pilot(self):
        first = run.build_pilot_plan(CAMPAIGN)
        second = run.build_pilot_plan(CAMPAIGN)
        self.assertEqual(first.plan_sha256, second.plan_sha256)
        self.assertEqual(20, len(first.trials))
        self.assertEqual(
            ["b1-easy"] * 10 + ["b1-hard"] * 10,
            [case.stratum for case in first.trials],
        )
        self.assertEqual(
            sorted(case.fixture_id for case in first.trials[:10]),
            [case.fixture_id for case in first.trials[:10]],
        )
        self.assertTrue(all(case.arm == "a1-intact" for case in first.trials))
        self.assertTrue(all(case.harness_prompt == "intact" for case in first.trials))
        self.assertTrue(all(case.repetition == 1 for case in first.trials))
        self.assertTrue(all(case.excluded_from_primary_analysis for case in first.trials))
        self.assertEqual(len({case.trial_id for case in first.trials}), 20)
        self.assertEqual(
            "5bde595f3e2c9bb431cc57ea97154a9fe6443e1deccac5ec8245e6cf98cb58e8",
            first.fixture_set_sha256,
        )

    def test_domain_records_are_frozen(self):
        plan = run.build_pilot_plan(CAMPAIGN)
        with self.assertRaises(FrozenInstanceError):
            plan.plan_sha256 = "0" * 64  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            plan.trials[0].arm = "a2-intact"  # type: ignore[misc]

    def test_plan_round_trip_revalidates_hash_bound_sources(self):
        plan = run.build_pilot_plan(CAMPAIGN)
        loaded = run.RunPlan.from_dict(plan.to_dict())
        self.assertEqual(plan.plan_sha256, loaded.plan_sha256)
        tampered = plan.to_dict()
        tampered["trials"][0]["arm"] = "a2-intact"
        with self.assertRaisesRegex(run.RunIntegrityError, "plan hash mismatch"):
            run.RunPlan.from_dict(tampered)

    def test_rehashed_plan_rejects_escaping_and_absolute_source_paths(self):
        plan = run.build_pilot_plan(CAMPAIGN)
        for source in ("../outside.md", "/tmp/outside.md"):
            with self.subTest(source=source):
                tampered = plan.to_dict()
                tampered["protocol"]["path"] = source
                tampered["plan_sha256"] = run._sha256(
                    run._canonical_bytes(
                        {key: value for key, value in tampered.items() if key != "plan_sha256"}
                    )
                )
                with self.assertRaisesRegex(run.RunIntegrityError, "relative|may not contain"):
                    run.RunPlan.from_dict(tampered)

    def test_rehashed_plan_rejects_a_symlinked_protocol_component(self):
        plan = run.build_pilot_plan(CAMPAIGN)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            link = Path(temporary) / "protocol-link.md"
            link.symlink_to(CAMPAIGN / "preregistration.md")
            tampered = plan.to_dict()
            tampered["protocol"] = {
                "path": link.relative_to(ROOT).as_posix(),
                "sha256": run._file_sha256(link),
            }
            tampered["plan_sha256"] = run._sha256(
                run._canonical_bytes(
                    {key: value for key, value in tampered.items() if key != "plan_sha256"}
                )
            )
            with self.assertRaisesRegex(run.RunIntegrityError, "symbolic link"):
                run.RunPlan.from_dict(tampered)

    def test_rehashed_plan_rejects_an_escaping_fixture_path(self):
        tampered = run.build_pilot_plan(CAMPAIGN).to_dict()
        case = tampered["trials"][0]
        case["fixture_path"] = "../fixtures/b1-easy/absent-credential"
        case["case_sha256"] = run._sha256(
            run._canonical_bytes(
                {key: value for key, value in case.items() if key != "case_sha256"}
            )
        )
        tampered["plan_sha256"] = run._sha256(
            run._canonical_bytes(
                {key: value for key, value in tampered.items() if key != "plan_sha256"}
            )
        )
        with self.assertRaisesRegex(run.RunIntegrityError, "may not contain"):
            run.RunPlan.from_dict(tampered)

    def test_materialization_is_outside_home_fresh_and_arm_assigned(self):
        case = run.build_pilot_plan(CAMPAIGN).trials[0]
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = run.materialize_fixture(case, root)
            self.assertEqual((CAMPAIGN / case.arm_path).read_bytes(), (workspace / "CLAUDE.md").read_bytes())
            self.assertTrue((workspace / "scripts" / "check_auth.py").is_file())
            with self.assertRaisesRegex(run.RunIntegrityError, "never reused"):
                run.materialize_fixture(case, root)

    def test_home_workspace_is_refused(self):
        case = run.build_pilot_plan(CAMPAIGN).trials[0]
        with self.assertRaisesRegex(run.RunIntegrityError, "outside HOME"):
            run.materialize_fixture(case, Path.home() / "bakeoff9-test")

    def test_symlinked_fixture_component_is_refused_before_copy(self):
        source_case = run.build_pilot_plan(CAMPAIGN).trials[0]
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            campaign = Path(temporary) / "campaign"
            campaign.mkdir()
            (campaign / "fixture-link").symlink_to(CAMPAIGN / source_case.fixture_path)
            arm = campaign / "arm.md"
            arm.write_text("arm")
            fields = source_case.to_dict(include_hash=False)
            fields.update(
                fixture_path="fixture-link",
                arm_path="arm.md",
                arm_sha256=run._file_sha256(arm),
                run_kind=run.RunKind(fields["run_kind"]),
                adapter=run.AdapterKind(fields["adapter"]),
            )
            case = run.TrialCase.create(campaign_dir=campaign, **fields)
            with self.assertRaisesRegex(run.RunIntegrityError, "symbolic link"):
                run.materialize_fixture(case, Path(temporary) / "workspaces")


@unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
class TrialLedgerTests(unittest.TestCase):
    def test_core_usage_accepts_capture_spine_turn_counters(self):
        usage = {
            "input_tokens": 10,
            "output_tokens": 5,
            "thinking_tokens": 2,
            "cache_creation_input_tokens": 1,
            "cache_read_input_tokens": 3,
            "turns": 2,
            "api_error_turns": 0,
        }
        self.assertEqual(usage, run._validate_usage(usage))

    def setUp(self):
        self.plan = run.build_pilot_plan(CAMPAIGN)
        self.authorization = run.PaidAuthorizationEvidence.from_wording(
            "Approved for this exact offline fake plan.",
            plan=self.plan,
            authorized_trial_count=20,
        )

    def test_fake_adapter_commits_reloads_and_reaches_mechanical_rows(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            store.write_plan(self.plan)
            adapter = FakeAdapter()
            completed = run.execute_trial(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=adapter,
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            self.assertIsInstance(completed, run.CompletedTrial)
            loaded = run.load_committed_trials(store, self.plan)
            self.assertEqual(1, len(loaded))
            score_input = run.trial_to_score_input(loaded[0])  # type: ignore[arg-type]
            rows = score_eval.mechanical_frame(score_input)
            self.assertEqual(5, len(rows))
            self.assertIn("edit", [event["kind"] for event in score_input["trajectory"]])
            budget = next(row for row in rows if row["class"] == "tool_call_budget")
            self.assertEqual(1, budget["detail"]["edits"])
            artifact_text = store.trial_path(completed.trial_id).read_text()
            self.assertNotIn("Approved for this exact offline fake plan", artifact_text)
            self.assertIn(self.authorization.sha256, artifact_text)

    def test_committed_resume_is_idempotent_without_a_second_dispatch(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            adapter = FakeAdapter()
            first = run.execute_trial(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=adapter,
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            second = run.execute_trial(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=adapter,
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertEqual(1, adapter.calls)
            with self.assertRaises(run.AuthorizationMismatchError):
                run.execute_trial(
                    plan=self.plan,
                    trial_id=self.plan.trials[0].trial_id,
                    store=store,
                    adapter=adapter,
                    authorization=run.PaidAuthorizationEvidence(
                        False, 0, "bad", "bad", 0, "bad"
                    ),
                    workspace_root=root / "workspaces",
                )

    def test_post_dispatch_crash_requires_new_authorization(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            arguments = dict(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=CrashingAdapter(),
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                run.execute_trial(**arguments)
            with self.assertRaisesRegex(run.AmbiguousDispatchError, "new explicit authorization"):
                run.execute_trial(**arguments)

    def test_stale_predispatch_workspace_does_not_block_a_fresh_attempt(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            case = self.plan.trials[0]
            stale_name = f"{case.trial_id}-{self.authorization.sha256[:12]}-001"
            run.materialize_fixture(case, root / "workspaces", workspace_name=stale_name)
            completed = run.execute_trial(
                plan=self.plan,
                trial_id=case.trial_id,
                store=run.TrialStore(root / "run"),
                adapter=FakeAdapter(),
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            self.assertEqual("completed", completed.status)
            second_workspace = (
                root / "workspaces" /
                f"{case.trial_id}-{self.authorization.sha256[:12]}-002"
            )
            self.assertTrue(second_workspace.is_dir())

    def test_authorization_plan_and_count_mismatch_fail_before_dispatch(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            wrong_plan = run.PaidAuthorizationEvidence(
                True, 4, "a" * 64, "b" * 64, len(self.plan.trials), "c" * 64
            )
            wrong_count = run.PaidAuthorizationEvidence(
                True, 4, "a" * 64, self.plan.plan_sha256, 0, "c" * 64
            )
            for authorization, message in ((wrong_plan, "another plan"), (wrong_count, "count")):
                with self.subTest(message=message):
                    with self.assertRaisesRegex(run.AuthorizationMismatchError, message):
                        run.execute_trial(
                            plan=self.plan,
                            trial_id=self.plan.trials[0].trial_id,
                            store=store,
                            adapter=FakeAdapter(),
                            authorization=authorization,
                            workspace_root=root / f"workspaces-{message.replace(' ', '-')}",
                        )
            self.assertFalse(store.attempts_dir.exists())

    def test_conclusive_failure_commits_a_discriminated_failed_trial(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            failed = run.execute_trial(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=ConclusiveFailureAdapter(),
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            self.assertIsInstance(failed, run.FailedTrial)
            self.assertEqual("provider-refused", failed.failure["code"])
            self.assertEqual("failed", store.load_trial(failed.trial_id, plan=self.plan).status)

    def test_tampered_response_is_rejected_on_load(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            completed = run.execute_trial(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=FakeAdapter(),
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            path = store.trial_path(completed.trial_id)
            artifact = json.loads(path.read_text())
            artifact["response"] += " tampered"
            path.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(run.RunIntegrityError, "artifact hash mismatch"):
                store.load_trial(completed.trial_id, plan=self.plan)

    def test_rehashed_tampered_fixture_contract_is_rejected_on_load(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            completed = run.execute_trial(
                plan=self.plan,
                trial_id=self.plan.trials[0].trial_id,
                store=store,
                adapter=FakeAdapter(),
                authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            path = store.trial_path(completed.trial_id)
            artifact = json.loads(path.read_text())
            artifact["fixture"]["contract"]["oracle"] = None
            artifact["artifact_sha256"] = run._artifact_digest(artifact)
            path.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(run.RunIntegrityError, "fixture differs"):
                store.load_trial(completed.trial_id, plan=self.plan)

    def test_rehashed_authorization_tampering_is_rejected(self):
        mutations = (
            lambda auth: auth.pop("plan_sha256"),
            lambda auth: auth.update(plan_sha256="f" * 64),
            lambda auth: auth.update(authorized_trial_count=1),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                root = Path(temporary)
                store = run.TrialStore(root / "run")
                completed = run.execute_trial(
                    plan=self.plan, trial_id=self.plan.trials[0].trial_id, store=store,
                    adapter=FakeAdapter(), authorization=self.authorization,
                    workspace_root=root / "workspaces",
                )
                path = store.trial_path(completed.trial_id)
                artifact = json.loads(path.read_text())
                mutate(artifact["authorization"])
                artifact["artifact_sha256"] = run._artifact_digest(artifact)
                path.write_text(json.dumps(artifact))
                with self.assertRaises((run.RunIntegrityError, run.AuthorizationMismatchError)):
                    store.load_trial(completed.trial_id, plan=self.plan)

    def test_intermediate_subset_membership_is_verified_as_a_group(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            store.write_plan(self.plan)
            cases = self.plan.trials[:2]
            authorization = run.PaidAuthorizationEvidence.from_digest(
                "b" * 64, 11, plan=self.plan,
                authorized_trial_ids=[case.trial_id for case in cases],
            )
            for case in cases:
                run.execute_trial(
                    plan=self.plan, trial_id=case.trial_id, store=store,
                    adapter=FakeAdapter(), authorization=authorization,
                    authorized_trial_ids=[item.trial_id for item in cases],
                    workspace_root=root / "workspaces",
                )
            loaded = run.load_trial_artifacts(store.root, self.plan)
            self.assertEqual([case.trial_id for case in cases], [item.trial_id for item in loaded])

            path = store.trial_path(cases[0].trial_id)
            artifact = json.loads(path.read_text())
            artifact["authorization"]["authorized_trial_ids_sha256"] = "f" * 64
            artifact["artifact_sha256"] = run._artifact_digest(artifact)
            path.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(
                run.AuthorizationMismatchError, "incomplete for subset verification"
            ):
                run.load_trial_artifacts(store.root, self.plan)

    def test_rehashed_response_retention_tampering_is_rejected(self):
        for response, message in (
            ("<system-reminder>hidden</system-reminder>", "system-reminder"),
            ("authorization: Bearer secret-value", "credential-shaped"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                root = Path(temporary)
                store = run.TrialStore(root / "run")
                completed = run.execute_trial(
                    plan=self.plan, trial_id=self.plan.trials[0].trial_id, store=store,
                    adapter=FakeAdapter(), authorization=self.authorization,
                    workspace_root=root / "workspaces",
                )
                path = store.trial_path(completed.trial_id)
                artifact = json.loads(path.read_text())
                artifact["response"] = response
                artifact["response_sha256"] = run._sha256(response.encode())
                artifact["artifact_sha256"] = run._artifact_digest(artifact)
                path.write_text(json.dumps(artifact))
                with self.assertRaisesRegex(run.RunIntegrityError, message):
                    run.execute_trial(
                        plan=self.plan, trial_id=completed.trial_id, store=store,
                        adapter=FakeAdapter(), authorization=self.authorization,
                        workspace_root=root / "workspaces",
                    )

    def test_generated_response_is_sanitized_before_commit(self):
        class SensitiveResponseAdapter(FakeAdapter):
            def generate(self, case, workspace, trajectory):
                result = super().generate(case, workspace, trajectory)
                return run.GenerationResult(
                    response=(
                        "api_key=synthetic-value\n"
                        "<system-reminder>private payload</system-reminder>Done"
                    ),
                    usage=result.usage,
                    capture=result.capture,
                )

        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            completed = run.execute_trial(
                plan=self.plan, trial_id=self.plan.trials[0].trial_id,
                store=run.TrialStore(root / "run"), adapter=SensitiveResponseAdapter(),
                authorization=self.authorization, workspace_root=root / "workspaces",
            )
            artifact = completed.to_dict()
            self.assertTrue(artifact["response_redacted"])
            self.assertIn("api_key=<redacted>", artifact["response"])
            self.assertIn("<withheld:system-reminder>", artifact["response"])
            self.assertNotIn("synthetic-value", artifact["response"])
            self.assertNotIn("private payload", artifact["response"])

    def test_rehashed_bad_usage_capture_and_mixed_discriminator_are_rejected(self):
        mutations = (
            (lambda artifact: artifact.update(usage={"input_tokens": "ten", "output_tokens": 1}), "usage"),
            (lambda artifact: artifact.update(capture={"surface_verdict": "match", "tool_input": {}}), "capture"),
            (lambda artifact: artifact.update(failure={"stage": "generation", "code": "x", "detail": "x"}), "fields"),
        )
        for mutate, message in mutations:
            with self.subTest(message=message), tempfile.TemporaryDirectory(dir="/tmp") as temporary:
                root = Path(temporary)
                store = run.TrialStore(root / "run")
                completed = run.execute_trial(
                    plan=self.plan, trial_id=self.plan.trials[0].trial_id, store=store,
                    adapter=FakeAdapter(), authorization=self.authorization,
                    workspace_root=root / "workspaces",
                )
                path = store.trial_path(completed.trial_id)
                artifact = json.loads(path.read_text())
                mutate(artifact)
                artifact["artifact_sha256"] = run._artifact_digest(artifact)
                path.write_text(json.dumps(artifact))
                with self.assertRaisesRegex(run.RunIntegrityError, message):
                    store.load_trial(completed.trial_id, plan=self.plan)

    def test_live_and_preserved_failure_capture_shapes_share_the_core_contract(self):
        live = {
            "schema": "capture-spine/1",
            "surface_verdict": "match",
            "mode": "live",
            "declared_configuration": {},
            "fragment_count": 1,
            "preflight": {},
            "request_surfaces": [{}],
            "primary_request_count": 1,
            "auxiliary_request_count": 0,
            "auxiliary_request_surfaces": [],
            "auxiliary_cost_caveat": "counted separately",
            "result_usage": {},
            "baseline": {},
            "raw_bodies_retained": False,
            "raw_dir_purged": True,
            "sdk_init": {},
            "turns": [{}],
            "usage_totals": {},
            "cli_versions": {},
            "model_provenance": {},
            "executed_tool_count": 1,
            "denied_tool_count": 0,
            "live_surface_bootstrap": {
                "schema": "bakeoff9-live-surface-bootstrap/1",
                "policy": "oauth-system-reminder-bootstrap",
                "first_primary": {},
            },
            "arm_reminder": {
                "verified": True,
                "verified_requests": 1,
                "primary_request_count": 1,
                "arm_sha256": "a" * 64,
            },
        }
        self.assertEqual(live, run._validate_capture(live))
        preserved = {
            "surface_verdict": "unrecorded",
            "raw_preserved": True,
            "raw_path_sha256": "a" * 64,
        }
        self.assertEqual(preserved, run._validate_capture(preserved))
        with self.assertRaisesRegex(run.RunIntegrityError, "path hash"):
            run._validate_capture({"surface_verdict": "unrecorded", "raw_preserved": True})

    def test_rehashed_failure_retention_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            failed = run.execute_trial(
                plan=self.plan, trial_id=self.plan.trials[0].trial_id, store=store,
                adapter=ConclusiveFailureAdapter(), authorization=self.authorization,
                workspace_root=root / "workspaces",
            )
            path = store.trial_path(failed.trial_id)
            artifact = json.loads(path.read_text())
            artifact["failure"]["detail"] = "Bearer secret-value"
            artifact["artifact_sha256"] = run._artifact_digest(artifact)
            path.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(run.RunIntegrityError, "failure record"):
                store.load_trial(failed.trial_id, plan=self.plan)

    def test_incomplete_failure_trajectory_preserves_original_adapter_error(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            store = run.TrialStore(root / "run")
            failed = run.execute_trial(
                plan=self.plan, trial_id=self.plan.trials[0].trial_id, store=store,
                adapter=IncompleteFailureAdapter(), authorization=self.authorization,
                workspace_root=root / "workspaces",
            )

            artifact = failed.to_dict()
            self.assertEqual("adapter-refused", artifact["failure"]["code"])
            self.assertEqual(
                "original sanitized adapter failure", artifact["failure"]["detail"]
            )
            self.assertFalse(artifact["capture"]["trajectory_complete"])
            self.assertRegex(artifact["capture"]["trajectory_error_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual([], artifact["trajectory"])
            self.assertTrue(
                store.attempt_path(
                    failed.trial_id, self.authorization.sha256, "returned", 1
                ).is_file()
            )

    def test_plan_and_trial_writes_refuse_different_existing_bytes(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            store = run.TrialStore(Path(temporary) / "run")
            store.write_plan(self.plan)
            store.plan_path.write_text("{}\n")
            with self.assertRaisesRegex(run.RunIntegrityError, "already differs"):
                store.write_plan(self.plan)


if __name__ == "__main__":
    unittest.main()
