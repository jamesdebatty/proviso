#!/usr/bin/env python3
"""Bakeoff 10 verdicts from a verified run directory and its judge outputs.

Implements protocol.md "Hypotheses and verdict rules" exactly as written:
H1/H2 read the retained per-trial density observations, H3 reads the
mannered-prose labels with its power check first, H4 reads words and the
coverage labels. Judges are unblinded here, and only here, by recomputing the
task binding each blind task was sealed with.

Usage:
    python3 analyze.py <run_dir> --judge-root <dir> [--out analysis.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402
import clause_judge as cj  # noqa: E402

BASELINE = "a1-response-numbers"
TREATMENTS = ("d1-density-long", "d2-density-short")
DENSITY_FIELDS = {"sentence-length": "mean_sentence_words", "paragraph-length": "mean_paragraph_words"}
JUDGES = ("codex", "claude")
MANNERED = "mannered-prose"
COVERAGE = "coverage"
POWER_FLOOR = 5          # protocol H3: fewer than 5 of 25 A1 `present` labels is underpowered
SUPPORT_RELATIVE = 0.10  # protocol H1: pooled median falls at least 10% relative
REFUTE_RELATIVE = 0.05   # protocol H1: falls less than 5% with tasks split 3-2 or worse
HARM_WORDS = 1.10        # protocol H4: pooled median words at or below 110% of A1


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def load_run(run_dir: Path) -> tuple[dict, list[dict], dict]:
    plan = cc._read_canonical(run_dir / "plan.json", "plan")
    trials = cc._load_trials(run_dir, plan)
    grades = cc._read_canonical(run_dir / "grades.json", "grades")
    return plan, trials, grades


def trial_rows(plan: dict, trials: list[dict], grades: dict) -> list[dict]:
    by_trial = {}
    for row in grades["rows"]:
        by_trial.setdefault(row["trial_id"], {})[row["measure_id"]] = row
    rows = []
    for trial in trials:
        observed = by_trial[trial["trial_id"]]
        density = observed["sentence-length"]["observation"]
        row = {
            "trial_id": trial["trial_id"],
            "variant": trial["variant_id"],
            "probe": trial["probe_id"],
            "repetition": trial["repetition"],
            "words": trial["output"]["words"],
            "mean_sentence_words": density["mean_sentence_words"],
            "mean_paragraph_words": density["mean_paragraph_words"],
            "paragraphs": density["paragraphs"],
            "items": density["items"],
            "sentences": density["sentences"],
            "passed": {measure: observed[measure]["passed"] for measure in observed},
            "labels": {},
        }
        if "generation" in trial:
            row["total_cost_usd"] = trial["generation"].get("total_cost_usd")
            row["output_tokens"] = (trial["generation"].get("usage") or {}).get("output_tokens")
        rows.append(row)
    return rows


def unblind(plan: dict, trials: list[dict], rows: list[dict], judge_root: Path) -> dict:
    """Attach judge labels to trial rows by recomputing each blind task's binding."""
    judgmental = [m for m in plan["measures"] if m["kind"] == "judgmental"]
    by_trial = {row["trial_id"]: row for row in rows}
    coverage = {}
    for judge in JUDGES:
        out_dir = judge_root / judge
        if not out_dir.is_dir():
            coverage[judge] = {"records": 0, "expected": len(trials) * len(judgmental)}
            continue
        found = 0
        for trial in trials:
            for measure in judgmental:
                binding = {
                    "trial_sha256": trial["trial_sha256"],
                    "output_sha256": trial["output"]["sha256"],
                    "measure_id": measure["id"],
                    "rubric_sha256": measure["rubric_sha256"],
                }
                task_id = cc._digest(binding)
                path = out_dir / f"{task_id}.json"
                if not path.is_file():
                    continue
                record = cc._read_canonical(path, f"judgment {task_id}")
                cc._verify_seal(record, "record_sha256", f"judgment {task_id}")
                if record["measure_id"] != measure["id"] or record["judge"] != judge:
                    raise ValueError(f"judgment {task_id} does not belong to {measure['id']}/{judge}")
                by_trial[trial["trial_id"]]["labels"].setdefault(judge, {})[measure["id"]] = record["judgment"]
                found += 1
        coverage[judge] = {"records": found, "expected": len(trials) * len(judgmental)}
    return coverage


def arm_summary(rows: list[dict], variant: str) -> dict:
    sub = [r for r in rows if r["variant"] == variant]
    tasks = sorted({r["probe"] for r in sub})
    per_task = {
        task: {
            key: median(r[key] for r in sub if r["probe"] == task)
            for key in ("mean_sentence_words", "mean_paragraph_words", "words")
        }
        for task in tasks
    }
    return {
        "n": len(sub),
        "tasks": len(tasks),
        "pooled_median": {
            key: median(r[key] for r in sub)
            for key in ("mean_sentence_words", "mean_paragraph_words", "words", "paragraphs", "items")
        },
        "pass_counts": {
            measure: sum(r["passed"].get(measure, False) for r in sub)
            for measure in ("sentence-length", "paragraph-length", "length-cap")
        },
        "per_task_median": per_task,
        "total_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in sub), 3),
    }


def density_verdict(base: dict, treat: dict) -> dict:
    tasks = sorted(base["per_task_median"])
    detail = {}
    for key in ("mean_sentence_words", "mean_paragraph_words"):
        lower = [t for t in tasks if treat["per_task_median"][t][key] < base["per_task_median"][t][key]]
        pooled_base, pooled_treat = base["pooled_median"][key], treat["pooled_median"][key]
        relative = (pooled_base - pooled_treat) / pooled_base if pooled_base else None
        detail[key] = {
            "tasks_lower": len(lower),
            "tasks_lower_ids": lower,
            "pooled_baseline": pooled_base,
            "pooled_treatment": pooled_treat,
            "relative_fall": round(relative, 4) if relative is not None else None,
        }
    all_lower_both = all(d["tasks_lower"] == len(tasks) for d in detail.values())
    all_ten = all(d["relative_fall"] is not None and d["relative_fall"] >= SUPPORT_RELATIVE for d in detail.values())
    rises = any(d["relative_fall"] is not None and d["relative_fall"] < 0 for d in detail.values())
    weak_split = any(
        d["relative_fall"] is not None and d["relative_fall"] < REFUTE_RELATIVE and d["tasks_lower"] <= 3
        for d in detail.values()
    )
    if all_lower_both and all_ten:
        verdict = "supported"
    elif rises or weak_split:
        verdict = "refuted"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "detail": detail}


def label_rate(rows: list[dict], variant: str, judge: str, measure: str, label: str) -> dict | None:
    sub = [r for r in rows if r["variant"] == variant and measure in r["labels"].get(judge, {})]
    if not sub:
        return None
    hits = sum(r["labels"][judge][measure]["label"] == label for r in sub)
    return {"count": hits, "n": len(sub), "rate": round(hits / len(sub), 4)}


def mannered_verdict(rows: list[dict]) -> dict:
    per_judge = {}
    for judge in JUDGES:
        base = label_rate(rows, BASELINE, judge, MANNERED, "present")
        treat = {t: label_rate(rows, t, judge, MANNERED, "present") for t in TREATMENTS}
        per_judge[judge] = {"baseline": base, **{t: treat[t] for t in TREATMENTS}}
    complete = [j for j in JUDGES if per_judge[j]["baseline"] and per_judge[j][TREATMENTS[0]]]
    if len(complete) < len(JUDGES):
        return {"verdict": "indeterminate", "reason": "judge results incomplete", "per_judge": per_judge}
    if any(per_judge[j]["baseline"]["count"] < POWER_FLOOR for j in JUDGES):
        return {"verdict": "indeterminate (underpowered)",
                "reason": f"fewer than {POWER_FLOOR} A1 responses labeled present by at least one judge",
                "per_judge": per_judge}
    lower = [j for j in JUDGES if per_judge[j][TREATMENTS[0]]["count"] < per_judge[j]["baseline"]["count"]]
    if len(lower) == len(JUDGES):
        verdict = "supported"
    elif not lower:
        verdict = "refuted"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "judges_lower_for_d1": lower, "per_judge": per_judge}


def harm_verdict(rows: list[dict], arms: dict) -> dict:
    out = {}
    base_words = arms[BASELINE]["pooled_median"]["words"]
    for treatment in TREATMENTS:
        words = arms[treatment]["pooled_median"]["words"]
        words_ok = words <= HARM_WORDS * base_words
        coverage = {}
        judged = True
        for judge in JUDGES:
            base = label_rate(rows, BASELINE, judge, COVERAGE, "incomplete")
            treat = label_rate(rows, treatment, judge, COVERAGE, "incomplete")
            if base is None or treat is None:
                judged = False
                coverage[judge] = None
                continue
            coverage[judge] = {"baseline": base, "treatment": treat, "ok": treat["rate"] <= base["rate"]}
        if not judged:
            verdict = "indeterminate"
        elif words_ok and all(c["ok"] for c in coverage.values()):
            verdict = "supported"
        else:
            verdict = "refuted"
        out[treatment] = {
            "verdict": verdict,
            "words": {"baseline": base_words, "treatment": words, "ratio": round(words / base_words, 4), "ok": words_ok},
            "coverage": coverage,
        }
    return out


def judge_agreement(rows: list[dict]) -> dict:
    out = {}
    for measure in (MANNERED, COVERAGE):
        pairs = [
            (r["labels"]["codex"][measure]["label"], r["labels"]["claude"][measure]["label"])
            for r in rows
            if measure in r["labels"].get("codex", {}) and measure in r["labels"].get("claude", {})
        ]
        if not pairs:
            out[measure] = None
            continue
        agree = sum(a == b for a, b in pairs)
        out[measure] = {"n": len(pairs), "exact_agreement": round(agree / len(pairs), 4)}
    return out


def analyze(run_dir: Path, judge_root: Path) -> dict:
    summary = cc.ClauseCampaign.verify(run_dir)
    plan, trials, grades = load_run(run_dir)
    rows = trial_rows(plan, trials, grades)
    coverage = unblind(plan, trials, rows, judge_root)
    arms = {variant: arm_summary(rows, variant) for variant in (BASELINE, *TREATMENTS)}
    return {
        "campaign_id": plan["campaign_id"],
        "plan_sha256": plan["plan_sha256"],
        "summary_sha256": summary["summary_sha256"],
        "execution": plan["execution"],
        "judge_coverage": coverage,
        "arms": arms,
        "H1_d1_density": density_verdict(arms[BASELINE], arms[TREATMENTS[0]]),
        "H2_d2_density": density_verdict(arms[BASELINE], arms[TREATMENTS[1]]),
        "H3_mannered_prose": mannered_verdict(rows),
        "H4_no_harm": harm_verdict(rows, arms),
        "judge_agreement": judge_agreement(rows),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--judge-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = analyze(args.run_dir, args.judge_root)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text)
    headline = {k: v for k, v in result.items() if k not in {"rows", "arms", "execution"}}
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
