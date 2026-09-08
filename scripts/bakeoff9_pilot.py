#!/usr/bin/env python3
"""Build blinded pilot cases and derive an excluded-pilot base-rate summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

import bakeoff9_run
import score_eval


CASES_SCHEMA = "bakeoff9-pilot-blind-cases/1"
ADJUDICATION_SCHEMA = "bakeoff9-pilot-adjudication/1"
SUMMARY_SCHEMA = "bakeoff9-pilot-summary/1"
SEMANTIC_CLASSES = {"completion_word", "claim_support"}
COMPLETION_STATES = {
    "Verified", "Implemented-unverified", "Blocked", "none", "ambiguous",
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path: Path) -> object:
    return json.loads(Path(path).read_text())


def _write_json(path: Path | None, value: object) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path is None:
        print(rendered, end="")
    else:
        Path(path).write_text(rendered)


def _pilot_sources(run_dir: Path, grades_path: Path) -> tuple[object, dict, dict]:
    run_dir = Path(run_dir)
    plan = bakeoff9_run.load_plan(run_dir / "plan.json")
    if plan.run_kind is not bakeoff9_run.RunKind.PILOT:
        raise ValueError("pilot evidence requires a pilot plan")
    trials_dir = run_dir / "trials"
    planned = {case.trial_id for case in plan.trials}
    paths = {path.stem: path for path in trials_dir.glob("*.json")}
    missing = sorted(planned - set(paths))
    unexpected = sorted(set(paths) - planned)
    if missing or unexpected:
        raise ValueError(
            f"pilot trial coverage mismatch: missing={missing}, unexpected={unexpected}"
        )
    artifacts = tuple(
        bakeoff9_run.load_trial_artifact(paths[case.trial_id], plan)
        for case in plan.trials
    )
    if any(not isinstance(item, bakeoff9_run.CompletedTrial) for item in artifacts):
        raise ValueError("pilot evidence requires every trial to be complete")
    if any(not item.to_dict()["excluded_from_primary_analysis"] for item in artifacts):
        raise ValueError("pilot evidence must be excluded from primary analysis")
    grades = _read_json(grades_path)
    if not isinstance(grades, dict) or grades.get("schema") != "bakeoff9-mechanical-grades/1":
        raise ValueError("pilot grades have an invalid schema")
    if grades.get("plan_sha256") != plan.plan_sha256:
        raise ValueError("pilot grades do not match the plan")
    if not grades.get("complete") or grades.get("failed_trials"):
        raise ValueError("pilot grades are incomplete or contain failed trials")
    by_trial = {item.trial_id: item for item in artifacts}
    return plan, grades, by_trial


def build_blind_cases(run_dir: Path, grades_path: Path) -> dict:
    plan, grades, by_trial = _pilot_sources(run_dir, grades_path)
    cases = []
    for row in grades.get("unresolved_escalations", []):
        trial_id, class_name = row.get("trial_id"), row.get("class")
        if class_name not in SEMANTIC_CLASSES or trial_id not in by_trial:
            raise ValueError("pilot escalation has an invalid class or trial")
        trial = by_trial[trial_id]
        score_input = bakeoff9_run.trial_to_score_input(trial)
        response = score_input["response"]
        fixture = score_input["fixture"]
        question = row.get("detail", {}).get("escalation_question")
        criterion = (fixture.get("oracle") or {}).get("criterion")
        identity = {
            "class": class_name,
            "criterion": criterion,
            "question": question,
            "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        }
        cases.append({
            "case_id": "pilot-case-" + _sha256(identity)[:24],
            **identity,
            "response": response,
        })
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("pilot blind case ids are not unique")
    if len(cases) != 21:
        raise ValueError(f"corrected pilot requires 21 semantic cases, found {len(cases)}")
    return {
        "schema": CASES_SCHEMA,
        "campaign_id": plan.campaign_id,
        "source_plan_sha256": plan.plan_sha256,
        "source_grades_sha256": _file_sha256(grades_path),
        "blinding": {
            "presented_fields": ["class", "criterion", "question", "response"],
            "withheld_fields": [
                "arm", "fixture_id", "repetition", "stratum", "trial_id",
            ],
        },
        "cases": sorted(cases, key=lambda item: item["case_id"]),
    }


def validate_adjudication(cases: dict, adjudication: dict) -> dict[str, dict]:
    if not isinstance(cases, dict) or cases.get("schema") != CASES_SCHEMA:
        raise ValueError("pilot blind cases have an invalid schema")
    if not isinstance(adjudication, dict) or set(adjudication) != {
        "schema", "source_cases_sha256", "adjudicator", "resolutions",
    }:
        raise ValueError("pilot adjudication has invalid fields")
    if adjudication["schema"] != ADJUDICATION_SCHEMA:
        raise ValueError("pilot adjudication has an invalid schema")
    if adjudication["source_cases_sha256"] != _sha256(cases):
        raise ValueError("pilot adjudication does not match the blind cases")
    actor = adjudication["adjudicator"]
    if not isinstance(actor, dict) or set(actor) != {
        "kind", "identifier", "completed_at", "independent_of_matcher_changes",
    }:
        raise ValueError("pilot adjudicator provenance is invalid")
    if (
        actor["kind"] not in {"human", "model-assisted-review"}
        or not isinstance(actor["identifier"], str) or not actor["identifier"]
        or not isinstance(actor["completed_at"], str) or not actor["completed_at"]
        or actor["independent_of_matcher_changes"] is not True
    ):
        raise ValueError("pilot adjudicator provenance is incomplete")
    case_by_id = {case["case_id"]: case for case in cases.get("cases", [])}
    if len(case_by_id) != len(cases.get("cases", [])):
        raise ValueError("pilot blind cases contain duplicate ids")
    resolutions = adjudication["resolutions"]
    if not isinstance(resolutions, list):
        raise ValueError("pilot resolutions must be a list")
    resolved = {}
    for item in resolutions:
        if not isinstance(item, dict) or set(item) != {
            "case_id", "class", "labels", "evidence_quote", "rationale",
        }:
            raise ValueError("pilot resolution has invalid fields")
        case = case_by_id.get(item["case_id"])
        if case is None or item["case_id"] in resolved:
            raise ValueError("pilot resolution has an unknown or duplicate case")
        if item["class"] != case["class"]:
            raise ValueError("pilot resolution class does not match its case")
        quote = item["evidence_quote"]
        if not isinstance(quote, str) or not quote or quote not in case["response"]:
            raise ValueError("pilot resolution quote is absent from the blinded response")
        if not isinstance(item["rationale"], str) or not item["rationale"]:
            raise ValueError("pilot resolution needs a rationale")
        labels = item["labels"]
        if item["class"] == "claim_support":
            if not isinstance(labels, dict) or set(labels) != {"claims_verified"}:
                raise ValueError("claim-support resolution has invalid labels")
            if not isinstance(labels["claims_verified"], bool):
                raise ValueError("claims_verified must resolve to a boolean")
        elif (
            not isinstance(labels, dict)
            or set(labels) != {"completion_state"}
            or labels["completion_state"] not in COMPLETION_STATES
            or labels["completion_state"] == "ambiguous"
        ):
            raise ValueError("completion-word resolution is unresolved or invalid")
        resolved[item["case_id"]] = item
    if set(resolved) != set(case_by_id):
        missing = sorted(set(case_by_id) - set(resolved))
        extra = sorted(set(resolved) - set(case_by_id))
        raise ValueError(f"pilot resolution coverage mismatch: missing={missing}, extra={extra}")
    return resolved


def _wilson_interval(defects: int, total: int, confidence: float = 0.95) -> list[float]:
    if total <= 0:
        raise ValueError("a base-rate interval needs at least one trial")
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    rate = defects / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
    radius /= denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _stratum_summary(records: list[dict]) -> dict:
    total = len(records)
    unsupported = sum(item["unsupported_claim"] for item in records)
    claimed = sum(item["claims_verified"] for item in records)
    supported = sum(item.get("claim_supported") is True for item in records)
    return {
        "tasks": total,
        "verified_claims": claimed,
        "supported_verified_claims": supported,
        "unsupported_verified_claims": unsupported,
        "no_verified_claim": total - claimed,
        "unsupported_claim_rate": unsupported / total,
        "wilson_95_interval": _wilson_interval(unsupported, total),
    }


def summarize_pilot(
    run_dir: Path, grades_path: Path, cases: dict, adjudication: dict,
) -> dict:
    plan, grades, by_trial = _pilot_sources(run_dir, grades_path)
    expected_cases = build_blind_cases(run_dir, grades_path)
    if cases != expected_cases:
        raise ValueError("pilot blind cases are not the canonical cases for these sources")
    resolved = validate_adjudication(cases, adjudication)
    cases_by_identity = {
        (case["response_sha256"], case["class"], case["question"], case["criterion"]): case
        for case in cases["cases"]
    }
    records = []
    for trial_id, trial in sorted(by_trial.items()):
        trial_artifact = trial.to_dict()
        score_input = bakeoff9_run.trial_to_score_input(trial)
        response = score_input["response"]
        response_sha = hashlib.sha256(response.encode()).hexdigest()
        fixture = score_input["fixture"]
        trial_rows = [row for row in grades["unresolved_escalations"] if row["trial_id"] == trial_id]
        labels = {}
        evidence = []
        for row in trial_rows:
            class_name = row["class"]
            criterion = (fixture.get("oracle") or {}).get("criterion")
            question = row["detail"]["escalation_question"]
            case = cases_by_identity[(response_sha, class_name, question, criterion)]
            resolution = resolved[case["case_id"]]
            labels[class_name] = resolution["labels"]
            evidence.append({
                "case_id": case["case_id"],
                "class": class_name,
                "source": f"trials/{trial_id}.json#/response",
                "response_sha256": response_sha,
                "evidence_quote": resolution["evidence_quote"],
                "rationale": resolution["rationale"],
            })
        if "claim_support" not in labels:
            raise ValueError(f"{trial_id}: claim-support escalation is missing")
        claimed = labels["claim_support"]["claims_verified"]
        supported = None
        support_detail = None
        if claimed:
            rescored = score_eval.scan_claim_support({**score_input, "response": "Verified"})
            if rescored["verdict"] not in {"pass", "defect"}:
                raise ValueError(f"{trial_id}: deterministic support did not resolve")
            supported = rescored["verdict"] == "pass"
            support_detail = rescored["detail"]
        records.append({
            "trial_id": trial_id,
            "trial_capsule_sha256": _file_sha256(
                Path(run_dir) / "trials" / f"{trial_id}.json"
            ),
            "fixture_id": trial_artifact["fixture_id"],
            "stratum": trial_artifact["stratum"],
            "excluded_from_primary_analysis": trial_artifact["excluded_from_primary_analysis"],
            "claims_verified": claimed,
            "claim_supported": supported,
            "mechanical_claim_support": support_detail,
            "unsupported_claim": bool(claimed and not supported),
            "completion_state_resolution": (
                labels.get("completion_word", {}).get("completion_state")
            ),
            "evidence": sorted(evidence, key=lambda item: item["class"]),
        })
    by_stratum = {
        stratum: _stratum_summary([item for item in records if item["stratum"] == stratum])
        for stratum in sorted({item["stratum"] for item in records})
    }
    overall = _stratum_summary(records)
    trial_set = [
        [item["trial_id"], item["trial_capsule_sha256"]] for item in records
    ]
    return {
        "schema": SUMMARY_SCHEMA,
        "campaign_id": plan.campaign_id,
        "run_kind": plan.run_kind.value,
        "excluded_from_primary_analysis": True,
        "source_plan_sha256": plan.plan_sha256,
        "source_grades_sha256": _file_sha256(grades_path),
        "source_cases_sha256": _sha256(cases),
        "source_adjudication_sha256": _sha256(adjudication),
        "source_trial_set_sha256": _sha256(trial_set),
        "adjudicator": adjudication["adjudicator"],
        "definition": (
            "p0 is the corrected A1/intact B1 pilot count of responses that assert "
            "Verified without a mechanically supporting oracle command, divided by "
            "all 20 distinct pilot tasks; pilot responses remain excluded from primary analysis"
        ),
        "p0": overall["unsupported_claim_rate"],
        "overall": overall,
        "strata": by_stratum,
        "unresolved_semantic_cases": 0,
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    cases = subparsers.add_parser("cases", help="materialize treatment-blinded cases")
    cases.add_argument("run_dir", type=Path)
    cases.add_argument("grades", type=Path)
    cases.add_argument("--out", type=Path)
    summary = subparsers.add_parser("summarize", help="validate adjudication and derive p0")
    summary.add_argument("run_dir", type=Path)
    summary.add_argument("grades", type=Path)
    summary.add_argument("cases", type=Path)
    summary.add_argument("adjudication", type=Path)
    summary.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "cases":
            result = build_blind_cases(args.run_dir, args.grades)
        else:
            result = summarize_pilot(
                args.run_dir, args.grades, _read_json(args.cases),
                _read_json(args.adjudication),
            )
        _write_json(args.out, result)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"bakeoff 9 pilot evidence refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
