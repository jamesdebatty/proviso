from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import execution  # noqa: E402

CORRECTED_PILOT = (ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
                   / "results" / "pilot-corrected-2026-08-27")
# The public release replaces README.md with the overlay one; only the lab
# README carries the historical-adapter contract these statements come from.
LAB_README = "## Historical adapters" in (ROOT / "README.md").read_text()
PRIVATE_ARTIFACTS = "requires private lab artifacts that are not included in the public release"


class ExecutionInterfaceTests(unittest.TestCase):
    def test_status_names_the_active_protocol_on_the_default_interface(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "execution.py"), "status"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("active campaign: clause-bakeoff-9-2026-08-22", completed.stdout)
        self.assertIn(
            "protocol: campaigns/clause-bakeoff-9-2026-08-22/preregistration.md",
            completed.stdout,
        )
        self.assertIn("pilot-execution-available:", completed.stdout)
        self.assertIn("pilot-ready-for-paid-dispatch: no", completed.stdout)
        self.assertIn("run-specific-preflight-required", completed.stdout)

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_check_runs_the_active_path_through_the_cli(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "execution.py"), "check", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("clause-bakeoff-9-2026-08-22", payload["active_campaign"])
        self.assertTrue(payload["passed"])
        scopes = {result["scope"]: result for result in payload["results"]}
        self.assertEqual(set(execution.CHECK_SCOPES), set(scopes))
        self.assertNotIn("problems", scopes["campaign-declaration"]["detail"])
        self.assertTrue(scopes["pilot-declaration"]["passed"])

    def test_status_separates_pilot_full_run_and_decision_readiness(self):
        class FakeStore:
            def write_plan(self, _plan):
                pass

        class FakeAuthorization:
            @classmethod
            def from_digest(cls, *_args, **_kwargs):
                return cls()

        class FakeCompleted:
            pass

        class FakeFailed:
            pass

        class FakeAdapter:
            def with_preflight(self, _receipt):
                return self

        runner = SimpleNamespace(
            build_pilot_plan=lambda *_args: None,
            TrialStore=FakeStore,
            CompletedTrial=FakeCompleted,
            execute_trial=lambda **_kwargs: None,
            FailedTrial=FakeFailed,
            load_committed_trials=lambda *_args: (),
            PaidAuthorizationEvidence=FakeAuthorization,
        )
        sdk = SimpleNamespace(
            AgentSDKAdapter=FakeAdapter,
            build_generation_adapter=lambda **_kwargs: None,
            synthetic_401_preflight=lambda **_kwargs: None,
        )
        decision = SimpleNamespace(analyze_campaign=lambda *_args: ())
        owner = SimpleNamespace(readiness=lambda: SimpleNamespace(
            pilot_plan_ready=True,
            pilot_execution_available=True,
            pilot_ready_for_paid_dispatch=False,
            full_run_ready=False,
            decision_ready=False,
            blockers=(("protocol-draft", "full-run", "draft"),),
        ))
        status = execution.execution_status(
            campaign=owner,
            runner_module=runner,
            sdk_module=sdk,
            decision_module=decision,
        )

        self.assertTrue(status.pilot_plan_ready)
        self.assertTrue(status.pilot_execution_available)
        self.assertFalse(status.pilot_ready_for_paid_dispatch)
        self.assertFalse(status.pilot_ready)
        self.assertFalse(status.full_run_ready)
        self.assertFalse(status.decision_ready)
        self.assertEqual(execution.ProtocolState.FROZEN, status.protocol_state)

    def test_status_has_no_stale_t013_blocker(self):
        serialized = json.dumps(execution.status_payload()).lower()

        self.assertNotIn("t-013", serialized)
        self.assertNotIn("oracle-integrity-open", serialized)

    @unittest.skipUnless(CORRECTED_PILOT.exists(), PRIVATE_ARTIFACTS)
    def test_pilot_declaration_is_exact_and_self_validating(self):
        self.assertEqual([], execution.pilot_declaration_problems())
        declaration = execution.tomllib.loads(execution.PILOT_DECLARATION.read_text())

        self.assertEqual(20, len(declaration["fixture_ids"]))
        self.assertEqual(20, len(set(declaration["fixture_ids"])))
        self.assertEqual("a1-intact", declaration["arm"])
        self.assertEqual(1, declaration["repetitions"])
        self.assertTrue(declaration["excluded_from_primary_analysis"])
        self.assertEqual("stratum-then-fixture-id", declaration["ordering"])
        self.assertEqual(0, declaration["seed"])

    def test_failing_fixture_check_fails_the_report(self):
        def fake_run(_command, **_kwargs):
            return SimpleNamespace(
                returncode=2,
                stdout="",
                stderr="fixture validation failed",
            )

        report = execution.check_current(run=fake_run)

        self.assertFalse(report.passed)
        fixture = next(
            result
            for result in report.results
            if result.scope == "fixture-contracts-and-preconditions"
        )
        self.assertFalse(fixture.passed)
        self.assertEqual("fixture validation failed", fixture.detail)

    def test_failing_check_exits_nonzero_through_the_cli_interface(self):
        failed = execution.CheckReport(
            campaign_id="clause-bakeoff-9-2026-08-22",
            results=(execution.CheckResult("fixture", False, "broken"),),
            does_not_prove=execution.DOES_NOT_PROVE,
        )
        output = io.StringIO()
        with mock.patch.object(execution, "check_current", return_value=failed):
            with redirect_stdout(output):
                exit_code = execution.main(["check", "--json"])

        self.assertEqual(1, exit_code)
        self.assertFalse(json.loads(output.getvalue())["passed"])

    @unittest.skipUnless(LAB_README, PRIVATE_ARTIFACTS)
    def test_legacy_safety_contract_is_documented(self):
        readme = " ".join((ROOT / "README.md").read_text().split())
        for statement in (
            "checks the Claude Code version before every response",
            "failures exceed 10%",
            "Any response failure makes the campaign indeterminate",
            "no command-line model or effort overrides",
            "reconstruct the response from the raw stream",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, readme)

    def test_legacy_namespace_forwards_to_the_historical_script(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=7)

        result = execution.run_legacy(
            "judge",
            ["results/runs/demo", "--execute"],
            run=fake_run,
        )

        self.assertEqual(7, result)
        self.assertEqual(
            [
                sys.executable,
                str(ROOT / "scripts" / "judge_eval.py"),
                "results/runs/demo",
                "--execute",
            ],
            calls[0][0],
        )
        self.assertEqual(ROOT, calls[0][1]["cwd"])

    def test_plan_only_writes_the_plan_but_never_executes(self):
        calls = []
        plan = SimpleNamespace(
            plan_sha256="a" * 64,
            trials=(SimpleNamespace(trial_id="trial-1"),),
        )

        class FakeStore:
            def __init__(self, root):
                calls.append(("store", root))

            def write_plan(self, received):
                calls.append(("write-plan", received))

        runner = SimpleNamespace(
            build_pilot_plan=lambda *args: calls.append(("build", args)) or plan,
            TrialStore=FakeStore,
            execute_trial=lambda **_kwargs: calls.append(("execute", None)),
            load_committed_trials=lambda *_args: (),
            PaidAuthorizationEvidence=lambda *_args: None,
        )
        sdk = SimpleNamespace(
            build_generation_adapter=lambda **_kwargs: self.fail("plan-only loaded the SDK adapter")
        )
        owner = SimpleNamespace(
            persist_plan=lambda _run_dir: (calls.append(("persist-plan", plan)) or (plan, None)),
            selection_sha256=lambda _trials: "e" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            payload = execution.run_pilot(
                Path(directory) / "run",
                execute=False,
                campaign=owner,
            )

        self.assertEqual("plan-only", payload["mode"])
        self.assertFalse(any(call[0] == "execute" for call in calls))
        self.assertEqual(["persist-plan"], [call[0] for call in calls])

    def test_execute_requires_authorization_hash_and_size(self):
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", stderr):
            result = execution.main(
                ["pilot", "--run-dir", "/tmp/bakeoff9-test-run", "--execute"]
            )

        self.assertEqual(2, result)
        self.assertIn("requires --authorization-sha256 and --authorization-bytes", stderr.getvalue())

    def test_grade_command_routes_through_campaign_facade(self):
        owner = SimpleNamespace(grade=lambda path: {
            "schema": "bakeoff9-mechanical-grades/1",
            "graded_trials": 3,
            "run_dir": str(path),
        })
        output = io.StringIO()
        with redirect_stdout(output):
            result = execution.main(
                ["grade", "--run-dir", "/tmp/offline-run", "--json"], campaign=owner
            )
        self.assertEqual(0, result)
        self.assertEqual(3, json.loads(output.getvalue())["graded_trials"])

    def test_execute_routes_through_the_runner_contract(self):
        calls = []
        trials = (SimpleNamespace(trial_id="trial-1"), SimpleNamespace(trial_id="trial-2"))
        plan = SimpleNamespace(plan_sha256="b" * 64, trials=trials)

        class FakeCompleted:
            def __init__(self, trial_id):
                self.trial_id = trial_id

        class FakeFailed:
            pass

        class FakeStore:
            def __init__(self, root):
                self.root = root

            def write_plan(self, received):
                self.plan = received

        class FakeAuthorization:
            @classmethod
            def from_digest(cls, sha256, byte_count, **kwargs):
                calls.append(("authorization", sha256, byte_count, kwargs))
                return "authorization"

        class FakeAdapter:
            binary = Path("/pinned/claude")
            model = "claude-opus-5"
            node_executable = "node"

            def __init__(self, *, bound=False):
                self.bound = bound

            def with_preflight(self, receipt):
                calls.append(("bind-preflight", receipt))
                return FakeAdapter(bound=True)

            def generate(self, *_args):
                return None

        runner = SimpleNamespace(
            build_pilot_plan=lambda *_args: plan,
            TrialStore=FakeStore,
            CompletedTrial=FakeCompleted,
            FailedTrial=FakeFailed,
            PaidAuthorizationEvidence=FakeAuthorization,
            execute_trial=lambda **kwargs: calls.append(("execute", kwargs)),
            load_committed_trials=lambda _store, _plan: tuple(
                FakeCompleted(trial.trial_id) for trial in trials
            ),
        )
        sdk = SimpleNamespace(
            AgentSDKAdapter=FakeAdapter,
            build_generation_adapter=lambda **kwargs: calls.append(("adapter", kwargs)) or FakeAdapter(),
            synthetic_401_preflight=lambda **kwargs: calls.append(("preflight", kwargs))
            or {
                "surface_verdict": "match",
                "hooks_surface_neutral": True,
                "inference_purchased": False,
            },
        )
        owner = SimpleNamespace(
            execute_pilot=lambda _run_dir, **kwargs: (
                calls.append(("campaign-execute", kwargs))
                or {
                    "plan": plan,
                    "selected_trials": 2,
                    "selected_trial_ids": [trial.trial_id for trial in trials],
                    "selected_trial_ids_sha256": "d" * 64,
                    "committed_trials": 2,
                    "grades": {"graded_trials": 2},
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            payload = execution.run_pilot(
                Path(directory) / "run",
                execute=True,
                authorization_sha256="c" * 64,
                authorization_bytes=12,
                campaign=owner,
            )

        executions = [call for call in calls if call[0] == "campaign-execute"]
        self.assertEqual(1, len(executions))
        self.assertEqual("c" * 64, executions[0][1]["authorization_sha256"])
        self.assertEqual(2, payload["committed_trials"])

    def test_preflight_failure_dispatches_no_trial(self):
        calls = []
        plan = SimpleNamespace(
            plan_sha256="d" * 64,
            trials=(SimpleNamespace(trial_id="trial-1"),),
        )

        class FakeStore:
            def __init__(self, _root):
                pass

            def write_plan(self, _plan):
                pass

        class FakeAuthorization:
            @classmethod
            def from_digest(cls, *_args, **_kwargs):
                return cls()

        class FakeCompleted:
            pass

        class FakeFailed:
            pass

        class FakeAdapter:
            binary = Path("/pinned/claude")
            model = "claude-opus-5"
            node_executable = "node"

            def with_preflight(self, _receipt):
                return self

            def generate(self, *_args):
                return None

        runner = SimpleNamespace(
            build_pilot_plan=lambda *_args: plan,
            TrialStore=FakeStore,
            CompletedTrial=FakeCompleted,
            FailedTrial=FakeFailed,
            PaidAuthorizationEvidence=FakeAuthorization,
            execute_trial=lambda **_kwargs: calls.append("execute"),
            load_committed_trials=lambda *_args: (),
        )
        sdk = SimpleNamespace(
            AgentSDKAdapter=FakeAdapter,
            build_generation_adapter=lambda **_kwargs: FakeAdapter(),
            synthetic_401_preflight=lambda **_kwargs: {
                "surface_verdict": "mismatch",
                "hooks_surface_neutral": False,
                "inference_purchased": False,
            },
        )
        owner = SimpleNamespace(
            execute_pilot=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("synthetic-401 preflight surface verdict is 'mismatch'")
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "surface verdict is 'mismatch'"):
                execution.run_pilot(
                    Path(directory) / "run",
                    execute=True,
                    authorization_sha256="e" * 64,
                    authorization_bytes=12,
                    campaign=owner,
                )

        self.assertEqual([], calls)

    def test_failed_trial_artifact_fails_the_pilot_and_cli(self):
        plan = SimpleNamespace(
            plan_sha256="f" * 64,
            trials=(SimpleNamespace(trial_id="trial-1"),),
        )

        class FakeStore:
            def __init__(self, _root):
                pass

            def write_plan(self, _plan):
                pass

        class FakeAuthorization:
            @classmethod
            def from_digest(cls, *_args, **_kwargs):
                return cls()

        class FakeCompleted:
            pass

        class FakeFailed:
            trial_id = "trial-1"
            failure = {"stage": "generation", "code": "sdk-adapter-refused"}

        class FakeAdapter:
            binary = Path("/pinned/claude")
            model = "claude-opus-5"
            node_executable = "node"

            def with_preflight(self, _receipt):
                return self

            def generate(self, *_args):
                return None

        runner = SimpleNamespace(
            build_pilot_plan=lambda *_args: plan,
            TrialStore=FakeStore,
            CompletedTrial=FakeCompleted,
            FailedTrial=FakeFailed,
            PaidAuthorizationEvidence=FakeAuthorization,
            execute_trial=lambda **_kwargs: None,
            load_committed_trials=lambda *_args: (FakeFailed(),),
        )
        sdk = SimpleNamespace(
            AgentSDKAdapter=FakeAdapter,
            build_generation_adapter=lambda **_kwargs: FakeAdapter(),
            synthetic_401_preflight=lambda **_kwargs: {
                "surface_verdict": "match",
                "hooks_surface_neutral": True,
                "inference_purchased": False,
            },
        )
        owner = SimpleNamespace(
            execute_pilot=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("trial-1: sdk-adapter-refused")
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "trial-1: sdk-adapter-refused"):
                execution.run_pilot(
                    Path(directory) / "run",
                    execute=True,
                    authorization_sha256="a" * 64,
                    authorization_bytes=12,
                    campaign=owner,
                )

        ready = execution.CurrentExecution(
            campaign_id="x",
            campaign_dir=ROOT,
            protocol=ROOT / "protocol.md",
            declaration=ROOT / "campaign.toml",
            fixture_validator=ROOT / "validate.py",
            protocol_state=execution.ProtocolState.DRAFT,
            pilot_planning=execution.Availability.AVAILABLE,
            pilot_execution=execution.Availability.AVAILABLE,
            live_generation=execution.Availability.UNAVAILABLE,
            decision_analysis=execution.Availability.UNAVAILABLE,
            blockers=(),
        )
        stderr = io.StringIO()
        with mock.patch.object(execution, "execution_status", return_value=ready):
            with mock.patch.object(
                execution,
                "run_pilot",
                side_effect=RuntimeError(
                    "pilot has failed trial artifacts: trial-1: sdk-adapter-refused (generation)"
                ),
            ):
                with mock.patch("sys.stderr", stderr):
                    result = execution.main(
                        [
                            "pilot",
                            "--run-dir",
                            "/tmp/bakeoff9-test-run",
                            "--execute",
                            "--authorization-sha256",
                            "a" * 64,
                            "--authorization-bytes",
                            "12",
                        ]
                    )
        self.assertEqual(2, result)
        self.assertIn("failed trial artifacts", stderr.getvalue())

    def test_draft_allows_pilot_but_not_full_generation(self):
        status = execution.CurrentExecution(
            campaign_id="x",
            campaign_dir=ROOT,
            protocol=ROOT / "protocol.md",
            declaration=ROOT / "campaign.toml",
            fixture_validator=ROOT / "validate.py",
            protocol_state=execution.ProtocolState.DRAFT,
            pilot_planning=execution.Availability.AVAILABLE,
            pilot_execution=execution.Availability.AVAILABLE,
            live_generation=execution.Availability.UNAVAILABLE,
            decision_analysis=execution.Availability.UNAVAILABLE,
            blockers=(),
        )

        self.assertTrue(status.pilot_execution_available)
        self.assertFalse(status.pilot_ready_for_paid_dispatch)
        self.assertFalse(status.pilot_ready)
        self.assertFalse(status.full_run_ready)

    def test_unsupported_full_run_and_decide_fail_truthfully(self):
        for command, expected in (
            ("run", "full run route is not implemented"),
            ("decide", "decision unavailable"),
        ):
            with self.subTest(command=command):
                stderr = io.StringIO()
                with mock.patch("sys.stderr", stderr):
                    argv = [command, "--run-dir", "/tmp/missing"] if command == "decide" else [command]
                    result = execution.main(argv)
                self.assertEqual(2, result)
                self.assertIn(expected, stderr.getvalue())

    def test_decision_analysis_cannot_be_available_without_a_runner(self):
        with self.assertRaisesRegex(ValueError, "decision analysis requires"):
            execution.CurrentExecution(
                campaign_id="x",
                campaign_dir=ROOT,
                protocol=ROOT / "protocol.md",
                declaration=ROOT / "campaign.toml",
                fixture_validator=ROOT / "validate.py",
                protocol_state=execution.ProtocolState.FROZEN,
                live_generation=execution.Availability.UNAVAILABLE,
                decision_analysis=execution.Availability.AVAILABLE,
                blockers=(),
            )


if __name__ == "__main__":
    unittest.main()
