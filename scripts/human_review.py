#!/usr/bin/env python3
"""Create and validate the human adjudication artifact for a campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import judge_eval
from harness_common import safe_trial_file, sha256_file


def required_pairs(sample: dict, qualitative: dict) -> list[dict]:
    ordered = []
    seen = set()
    for pair in sample.get("pairs", []) + qualitative.get("flagged_pairs", []):
        key = (pair.get("prompt_id"), pair.get("repetition"))
        if not isinstance(key[0], str) or not isinstance(key[1], int):
            raise ValueError(f"invalid human-review pair: {pair!r}")
        if key not in seen:
            seen.add(key)
            ordered.append({"prompt_id": key[0], "repetition": key[1]})
    return ordered


def review_evidence_sha256(run_dir: Path, pairs: list[dict]) -> str:
    resolved_run_dir = run_dir.resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    records = {
        (record.get("prompt_id"), record.get("repetition"), record.get("arm")): record
        for record in manifest.get("records", [])
    }
    artifacts = []
    judge_dir = run_dir / "judgments"
    for pair in pairs:
        prompt_id, repetition = pair["prompt_id"], pair["repetition"]
        for arm in ("control", "ste"):
            record = records.get((prompt_id, repetition, arm))
            if not record:
                raise ValueError(f"review pair has no {arm} response: {prompt_id} r{repetition}")
            for filename in ("stdout.jsonl", "stdout.json"):
                path = safe_trial_file(run_dir, record["trial_id"], filename)
                artifacts.append((str(path.relative_to(resolved_run_dir)), sha256_file(path)))
        for suffix in (".json", ".stdout.txt"):
            path = judge_eval.safe_judgment_path(judge_dir, prompt_id, repetition, suffix)
            artifacts.append((str(path.relative_to(resolved_run_dir)), sha256_file(path)))
    encoded = json.dumps(sorted(artifacts), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_template(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    scores_path = run_dir / "deterministic-scores.json"
    manifest = json.loads(manifest_path.read_text())
    scores = json.loads(scores_path.read_text())
    sample = json.loads((run_dir / "inputs" / "human-review-sample.json").read_text())
    pairs = required_pairs(sample, scores.get("qualitative") or {})
    return {
        "schema_version": 1,
        "campaign_manifest_sha256": sha256_file(manifest_path),
        "review_evidence_sha256": review_evidence_sha256(run_dir, pairs),
        "reviewer": "",
        "completed_at": "",
        "reviews": [
            {
                **pair,
                "assessment": "pending",
                "notes": "",
            }
            for pair in pairs
        ],
        "final_verdict": "pending",
        "rationale": "",
    }


def validate(run_dir: Path, qualitative: dict) -> dict:
    path = run_dir / "human-review.json"
    if not path.is_file():
        return {"complete": False, "reason": "human-review.json is missing"}
    item = json.loads(path.read_text())
    manifest_path = run_dir / "manifest.json"
    if item.get("campaign_manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("human review does not match the campaign manifest")
    sample = json.loads((run_dir / "inputs" / "human-review-sample.json").read_text())
    required = required_pairs(sample, qualitative)
    if item.get("review_evidence_sha256") != review_evidence_sha256(run_dir, required):
        raise ValueError("reviewed responses or judgments changed after human review")
    reviews = item.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("human review 'reviews' must be a list")
    by_key = {}
    for review in reviews:
        key = (review.get("prompt_id"), review.get("repetition"))
        if key in by_key:
            raise ValueError(f"duplicate human review pair: {key!r}")
        by_key[key] = review
    expected = {(pair["prompt_id"], pair["repetition"]) for pair in required}
    if set(by_key) != expected:
        raise ValueError("human review pairs do not match the frozen and flagged sample")
    complete = (
        bool(item.get("reviewer"))
        and bool(item.get("completed_at"))
        and item.get("final_verdict") in {"supported", "refuted"}
        and bool(item.get("rationale"))
        and all(
            review.get("assessment") in {"control", "ste", "tie"}
            and bool(review.get("notes"))
            for review in reviews
        )
    )
    return {
        "complete": complete,
        "final_verdict": item.get("final_verdict"),
        "reviewed_pairs": len(reviews),
        "required_pairs": len(required),
        "reason": None if complete else "human review contains pending or incomplete fields",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--init", action="store_true", help="create human-review.json")
    parser.add_argument("--check", action="store_true", help="validate human-review.json")
    args = parser.parse_args()
    if args.init == args.check:
        parser.error("choose exactly one of --init or --check")
    if args.init:
        path = args.run_dir / "human-review.json"
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
        template = build_template(args.run_dir)
        template["initialized_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(template, indent=2) + "\n")
        print(path)
        return 0
    scores = json.loads((args.run_dir / "deterministic-scores.json").read_text())
    result = validate(args.run_dir, scores.get("qualitative") or {})
    print(json.dumps(result, indent=2))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
