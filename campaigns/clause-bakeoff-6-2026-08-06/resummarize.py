#!/usr/bin/env python3
"""Offline re-summarize of bakeoff 6 from cached, hash-validated artifacts.

Used when the frozen CLI binaries are no longer installed (the auto-updater
garbage-collected 2.1.222) but no live calls are required: every response and
judgment is revalidated against the versions recorded at capture time. Any
missing or tampered artifact still fails closed. No subprocess is spawned.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parent
PROJECT = CAMPAIGN.parent.parent
sys.path.insert(0, str(PROJECT / "scripts"))

import provider  # noqa: E402
sys.modules["provider"] = provider
import analyze  # noqa: E402
from harness_common import sha256_file  # noqa: E402

FROZEN_CLAUDE = "2.1.222 (Claude Code)"
FROZEN_CODEX = "codex-cli 0.146.1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    versions = {"claude": FROZEN_CLAUDE, "codex": FROZEN_CODEX}
    work = [(task, rep) for task in analyze.tasks() for rep in range(1, 6)]
    stalls = {}
    for task in analyze.tasks():
        for repetition in range(1, 6):
            for arm in analyze.ARMS:
                text = analyze.response_output(out_dir, task, repetition, arm, FROZEN_CLAUDE)
                stalls[analyze.response_key(task["id"], repetition, arm)] = analyze.preflight(text)
    judge_dir = out_dir / "judgments"
    judgments = []
    for index, (task, repetition) in enumerate(work):
        labels = analyze.label_order(index)
        answers = {
            arm: analyze.response_output(out_dir, task, repetition, arm, FROZEN_CLAUDE)
            for arm in analyze.ARMS
        }
        prompt = analyze.judge_prompt(task, labels, answers)
        for judge in analyze.JUDGES:
            schema = analyze.SCHEMA if judge == "sonnet" else analyze.codex_schema()
            expected = analyze.judge_provenance(
                task, repetition, labels, judge, versions, prompt, answers, schema
            )
            output_path = judge_dir / f"{task['id']}-r{repetition}-{judge}.json"
            raw_path = judge_dir / f"{task['id']}-r{repetition}-{judge}.stdout.jsonl"
            rollout = (
                judge_dir / f"{task['id']}-r{repetition}-codex.rollout.jsonl"
                if judge == "codex" else None
            )
            cached = analyze.load_cached_judgment(output_path, raw_path, expected, judge, rollout)
            if cached is None:
                raise SystemExit(f"missing judgment: {task['id']} r{repetition} {judge}")
            judgments.append(cached)
    summary = analyze.summarize(out_dir, judgments, stalls, [], FROZEN_CLAUDE)
    manifest = {
        "status": "complete",
        "claude_version": FROZEN_CLAUDE,
        "codex_version": FROZEN_CODEX,
        "codex_judge_model": analyze.CODEX_MODEL,
        "response_count": len(work) * len(analyze.ARMS),
        "judgment_count": len(judgments),
        "resummarized_offline": (
            "recomputed from cached hash-validated artifacts after the frozen "
            "CLI binaries were uninstalled; no live calls"
        ),
        "input_hashes": {
            str(path.relative_to(CAMPAIGN)): sha256_file(path)
            for path in sorted(CAMPAIGN.rglob("*"))
            if path.is_file() and "out" not in path.parts and "__pycache__" not in path.parts
        },
        "summary": summary,
    }
    (out_dir / "bakeoff-results.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(
        {"selection_status": summary["selection_status"],
         "selected_candidate": summary["selected_candidate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
