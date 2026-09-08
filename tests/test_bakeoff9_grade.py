"""Mechanical grading consumes only the canonical bakeoff 9 loaders."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_grade as grade
import bakeoff9_run as run

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"


class FakeAdapter:
    kind = run.AdapterKind.SDK_QUERY

    def generate(self, case, workspace, trajectory):
        return run.GenerationResult(
            "Blocked: the declared prerequisite is unavailable.",
            {"input_tokens": 4, "output_tokens": 6},
            {
                "surface_verdict": "fake",
                "mode": "fake",
                "declared_configuration": {},
                "fragment_count": 0,
            },
        )


class CanonicalGradeBridgeTests(unittest.TestCase):
    def make_one(self, root: Path):
        plan = run.build_pilot_plan(CAMPAIGN, CAMPAIGN / "pilot.toml")
        store = run.TrialStore(root)
        store.write_plan(plan)
        selected = [plan.trials[0].trial_id]
        authorization = run.PaidAuthorizationEvidence.from_digest(
            "a" * 64, 12, plan=plan, authorized_trial_ids=selected
        )
        run.execute_trial(
            plan=plan,
            trial_id=selected[0],
            store=store,
            adapter=FakeAdapter(),
            authorization=authorization,
            authorized_trial_ids=selected,
            workspace_root=root.parent / "workspaces",
        )
        return plan

    def test_partial_canary_reaches_real_score_rows(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary) / "run"
            plan = self.make_one(root)
            result = grade.grade_run(root)
        self.assertEqual(plan.plan_sha256, result["plan_sha256"])
        self.assertEqual(1, result["graded_trials"])
        self.assertEqual(5, len(result["rows"]))
        self.assertFalse(result["complete"])
        self.assertEqual("excluded-pilot", result["decision_status"])

    def test_grade_run_calls_the_core_without_public_middle_men(self):
        self.assertIs(grade.grade_run.__globals__["bakeoff9_run"], run)
        public_functions = {
            name for name, value in vars(grade).items()
            if callable(value) and not name.startswith("_") and value.__module__ == grade.__name__
        }
        self.assertEqual({"grade_run", "write_grades", "main"}, public_functions)

    def test_unexpected_trial_file_is_refused_by_core(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary) / "run"
            self.make_one(root)
            (root / "trials" / "unexpected.json").write_text("{}")
            with self.assertRaisesRegex(run.RunIntegrityError, "unexpected"):
                grade.grade_run(root)


if __name__ == "__main__":
    unittest.main()
