#!/usr/bin/env python3
"""Canonical offline grade -> judge calibration -> decision pipeline."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

import bakeoff9_decision
import bakeoff9_judge
import bakeoff9_run
import score_eval


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class JudgeBinding:
    config: bakeoff9_judge.JudgeConfig
    sender: Callable[[dict], dict]

    def __post_init__(self) -> None:
        if not callable(self.sender):
            raise ValueError("judge sender must be callable")


@dataclass(frozen=True)
class PipelineResult:
    calibration: tuple[bakeoff9_judge.CalibrationReport, ...]
    decisions: tuple[bakeoff9_decision.CampaignDecision, ...]
    graded_trials: int
    plan_sha256: str

    def to_dict(self) -> dict:
        return _jsonable(self)


def _jsonable(value):
    if dataclasses.is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def trial_capsules_from_run(run_dir: Path) -> tuple[dict, ...]:
    """Load one committed capsule per trial: the decision's only trial input."""
    run_dir = Path(run_dir)
    plan = bakeoff9_run.load_plan(run_dir / "plan.json")
    artifacts = bakeoff9_run.load_trial_artifacts(run_dir, plan, require_all=True)
    capsules = []
    for artifact in artifacts:
        if not isinstance(artifact, bakeoff9_run.CompletedTrial):
            raise PipelineError(f"decision input contains failed trial {artifact.trial_id}")
        capsules.append(artifact.to_dict())
    return tuple(capsules)


def trial_metadata_from_capsules(capsules: Iterable[dict]) -> tuple[dict, ...]:
    """Project the strict metadata consumed by decision's score_eval bridge."""
    return tuple(
        {
            "trial_id": value["trial_id"],
            "fixture_id": value["fixture_id"],
            "repetition": value["repetition"],
            "arm": value["arm"],
            "stratum": value["stratum"],
            "surface_verdict": value["capture"]["surface_verdict"],
            "status": "complete",
            "is_pilot": value["excluded_from_primary_analysis"],
            "fixture": value["fixture"]["contract"],
            "usage_totals": value["usage"],
        }
        for value in capsules
    )


ESCALATION_CLASSES = tuple(bakeoff9_judge.ESCALATION_QUESTIONS)


@dataclass(frozen=True)
class EscalationItem:
    """One mechanically undecidable row, with the blind case that resolves it."""

    trial_id: str
    class_name: str
    case: bakeoff9_judge.JudgeCase
    supporting_command: str | None


def escalation_items(
    grading_rows: Iterable[dict], trials: Iterable[dict]
) -> tuple[EscalationItem, ...]:
    """Build one blind judge case per escalated mechanical row.

    The case carries only task and answer text under opaque ids. The
    deterministic oracle result travels beside it, never inside it, so a judge
    cannot see whether a claim was earned while deciding whether it was made.
    """
    by_trial = {}
    for trial in trials:
        trial_id = trial.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id:
            raise PipelineError("escalation input needs a string trial_id")
        if trial_id in by_trial:
            raise PipelineError(f"duplicate trial capsule: {trial_id}")
        by_trial[trial_id] = trial
    items = []
    seen = set()
    for row in grading_rows:
        if not isinstance(row, dict) or row.get("verdict") != "escalate":
            continue
        if row.get("decided_by") != "mechanical":
            raise PipelineError("only a mechanical row may escalate")
        trial_id, class_name = row.get("trial_id"), row.get("class")
        if class_name not in ESCALATION_CLASSES:
            raise PipelineError(f"class {class_name!r} cannot escalate")
        if (trial_id, class_name) in seen:
            raise PipelineError(f"duplicate escalated row: {(trial_id, class_name)!r}")
        seen.add((trial_id, class_name))
        trial = by_trial.get(trial_id)
        if trial is None:
            raise PipelineError(f"escalated row has no trial capsule: {trial_id!r}")
        expected = bakeoff9_judge.ESCALATION_QUESTIONS[class_name]
        if (row.get("detail") or {}).get("escalation_question") != expected:
            raise PipelineError(
                f"{trial_id} {class_name}: escalated row carries the wrong predeclared question"
            )
        contract = trial["fixture"]["contract"]
        # score_eval reads a flattened trial: its `fixture` is the contract.
        supporting, _ = score_eval.oracle_support({
            "fixture": contract, "trajectory": trial.get("trajectory") or [],
        })
        items.append(EscalationItem(
            trial_id, class_name,
            bakeoff9_judge.escalation_case(
                contract, trial["response"], trial["response_sha256"],
                class_name, namespace="escalation",
            ),
            supporting,
        ))
    items.sort(key=lambda item: (item.trial_id, item.class_name))
    return tuple(items)


def _resolution(item: EscalationItem, answer) -> dict:
    if item.class_name == "completion_word":
        return {"completion_state": answer}
    if item.class_name == "invented_check":
        return {"offers_command_as_verification": answer}
    if answer is not True:
        return {"claims_verified": answer}
    # The judge decided a Verified claim was asserted. Whether it is supported
    # stays mechanical: the oracle answers it, not the model.
    return {"claims_verified": True, "claim_supported": item.supporting_command is not None}


def resolve_escalations(
    items: Iterable[EscalationItem], binding: JudgeBinding
) -> dict[tuple[str, str], dict]:
    """Ask one vendor every predeclared escalation question, separately."""
    resolutions = {}
    for item in items:
        result = bakeoff9_judge.judge_with_sender(item.case, binding.config, binding.sender)
        labels = bakeoff9_judge.result_labels(item.case, result)
        answer = labels[f"escalation:{item.class_name}"]
        resolutions[(item.trial_id, item.class_name)] = _resolution(item, answer)
    return resolutions


def resolve_escalations_by_vendor(
    items: Iterable[EscalationItem], bindings: Iterable[JudgeBinding]
) -> dict[str, dict[tuple[str, str], dict]]:
    """Two vendor views of the same escalations, kept separate and never averaged."""
    materialized = tuple(items)
    resolved = {}
    for binding in bindings:
        vendor = binding.config.vendor
        if vendor in resolved:
            raise PipelineError("each judge vendor resolves escalations once")
        resolved[vendor] = resolve_escalations(materialized, binding)
    if len(resolved) != 2:
        raise PipelineError("bakeoff 9 requires exactly two separate judge vendors")
    return resolved


def judge_gold(
    gold: bakeoff9_judge.GoldSet, bindings: Iterable[JudgeBinding]
) -> tuple[tuple[bakeoff9_judge.JudgeResult, ...], ...]:
    materialized = tuple(bindings)
    if len(materialized) != 2 or len({item.config.vendor for item in materialized}) != 2:
        raise PipelineError("bakeoff 9 requires exactly two separate judge vendors")
    return tuple(
        tuple(
            bakeoff9_judge.judge_with_sender(case, binding.config, binding.sender)
            for case in gold.cases
        )
        for binding in materialized
    )


def analyze_graded_run(
    *,
    grades: dict,
    trial_capsules: Iterable[dict],
    gold: bakeoff9_judge.GoldSet,
    judge_bindings: Iterable[JudgeBinding],
    calibration_policy: bakeoff9_judge.CalibrationPolicy,
    decision_policy: bakeoff9_decision.AnalysisPolicy,
) -> PipelineResult:
    """Run two calibrated vendor views through the one canonical score bridge."""
    if (
        not isinstance(grades, dict)
        or grades.get("schema") != "bakeoff9-mechanical-grades/1"
        or not grades.get("complete")
        or not grades.get("primary_analysis_eligible")
        or grades.get("graded_trials") != grades.get("expected_trials")
        or grades.get("graded_trials") != 240
    ):
        raise PipelineError("decision requires one complete, primary-eligible 240-trial grade set")
    bindings = tuple(judge_bindings)
    capsules = tuple(trial_capsules)
    judged = judge_gold(gold, bindings)
    calibration = bakeoff9_judge.calibrate_vendors(
        gold, judged, calibration_policy
    )
    if any(not report.calibrated for report in calibration):
        detail = "; ".join(
            f"{report.vendor}: {', '.join(report.blockers)}"
            for report in calibration if not report.calibrated
        )
        raise PipelineError("judge calibration failed: " + detail)
    # Only a calibrated judge may be asked an escalation question, so this
    # runs after the gate above and never before it.
    resolutions_by_vendor = resolve_escalations_by_vendor(
        escalation_items(grades["rows"], capsules), bindings
    )
    vendors = {binding.config.vendor for binding in bindings}
    if set(resolutions_by_vendor) != vendors:
        raise PipelineError("escalation resolution coverage does not match judge vendors")
    metadata = trial_metadata_from_capsules(capsules)
    outcomes = []
    report_by_vendor = {report.vendor: report for report in calibration}
    for binding in bindings:
        vendor = binding.config.vendor
        outcomes.extend(bakeoff9_decision.response_outcomes_from_grading_rows(
            grades["rows"], metadata, judge_id=vendor,
            judgment_calibrated=report_by_vendor[vendor].calibrated,
            escalation_resolutions=resolutions_by_vendor[vendor],
        ))
    decisions = bakeoff9_decision.analyze_campaign(outcomes, decision_policy)
    if {decision.judge_id for decision in decisions} != vendors:
        raise PipelineError("decision output lost a judge vendor")
    return PipelineResult(
        calibration, decisions, grades["graded_trials"], grades["plan_sha256"]
    )
