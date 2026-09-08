#!/usr/bin/env python3
"""Route canonical bakeoff 9 trial capsules into the offline mechanical grader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bakeoff9_run
import score_eval


OUTPUT_SCHEMA = "bakeoff9-mechanical-grades/1"


def grade_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    plan = bakeoff9_run.load_plan(run_dir / "plan.json")
    artifacts = bakeoff9_run.load_trial_artifacts(run_dir, plan)
    completed = [
        trial for trial in artifacts if isinstance(trial, bakeoff9_run.CompletedTrial)
    ]
    failed = [trial for trial in artifacts if isinstance(trial, bakeoff9_run.FailedTrial)]
    frame = score_eval.grading_frame(
        [bakeoff9_run.trial_to_score_input(trial) for trial in completed], []
    )
    cases = {case.trial_id: case for case in plan.trials}
    metadata = {
        trial.trial_id: {
            "run_kind": plan.run_kind.value,
            "stratum": cases[trial.trial_id].stratum,
            "fixture_id": cases[trial.trial_id].fixture_id,
            "excluded_from_primary_analysis": cases[trial.trial_id].excluded_from_primary_analysis,
        }
        for trial in completed
    }
    rows = [{**row, **metadata[row["trial_id"]]} for row in frame["rows"]]
    pilot = plan.run_kind is bakeoff9_run.RunKind.PILOT
    return {
        "schema": OUTPUT_SCHEMA,
        "source_plan": "plan.json",
        "plan_sha256": plan.plan_sha256,
        "campaign_id": plan.campaign_id,
        "run_kind": plan.run_kind.value,
        "primary_analysis_eligible": not pilot and not failed,
        "decision_status": "excluded-pilot" if pilot else "not-decided-by-mechanical-grading",
        "complete": len(artifacts) == len(plan.trials) and not failed,
        "expected_trials": len(plan.trials),
        "graded_trials": len(completed),
        "failed_trials": [
            {"trial_id": trial.trial_id, "stage": trial.failure["stage"], "code": trial.failure["code"]}
            for trial in failed
        ],
        "rows": rows,
        "census": frame["census"],
        "mechanical_defects": [row for row in rows if row["verdict"] == "defect"],
        "unresolved_escalations": [row for row in rows if row["verdict"] == "escalate"],
    }


def write_grades(path: Path, grades: dict) -> None:
    path.write_text(json.dumps(grades, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        grades = grade_run(args.run_dir)
        if args.out:
            write_grades(args.out, grades)
        else:
            print(json.dumps(grades, indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        print(f"bakeoff9 grade refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
