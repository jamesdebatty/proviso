#!/usr/bin/env python3
"""Bakeoff 11 verdicts from a run directory and its judge outputs.

Implements the protocol's hypotheses P0 and H1-H5 as the council fixed them
(`notes/2026-09-05-bakeoff11-council/01-protocol-proposal.md` "Hypotheses and
verdict rules", the chair's edits in `08-chair-synthesis-round1.md` decisions
7 and 9, and the round-2 amendments in `11-chair-synthesis-round2.md`):

- Baseline is James's deployed file (`dep-deployed-file`); each treatment is
  that file plus one clause. H1-H4 contrast a treatment against it. `A1`
  (`a1-response-numbers`) is the anchor arm read only by H5 (DEP vs A1).
- `closing_offer_on_pass = closing_offer_count > 0 and oracle exit_code == 0`;
  `tail_present = tail_section_count > 0 or closing_offer_on_pass`, so a
  needed question on a blocked task does not count. The raw offer count is
  reported beside it.
- P0 floor: one third of the baseline's trials `tail_present` (6 of 18).
- H3a reads `unrequested-content`, H3b `plain-english`; H4 tolerates two
  trials on oracle and coverage and adds `claims_done_oracle_failed` must not
  rise; adoptable = H1 and H4 supported.
- `length-cap` (words <= 300) is a descriptive split: reported, read by no
  verdict.
- Timeout and budget failure records under `failures/` are censoring, reported
  per arm; other failure kinds are harness failures, reported beside them.

Rows are built from the sealed trials: every `final_message_scan` field is
recomputed from `output.text`, so the analysis does not depend on the grader's
observation layout; `passed` per declared measure is copied from
`grades.json`. Judges are unblinded here, and only here, by recomputing the
task binding each blind task was sealed with (bakeoff 10's rule).

Accepts a complete, verified run directory, or a partial directory written by
`clause_campaign.py grade-partial` (`summary.json` carries `partial: true`):
for a partial directory `verify` is skipped and each recorded trial is
seal-checked individually against the plan's cases. Either way the verdicts
read only complete repetition blocks (every planned variant x probe cell
recorded for that repetition) and the output says `truncated: k of r` when
blocks are missing.

Usage:
    python3 analyze.py <run_dir> --judge-root <dir> [--trials-dir <dir>] [--out analysis.json]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402
import final_message_scan as fms  # noqa: E402
import prose_density  # noqa: E402

BASELINE = "dep-deployed-file"
TREATMENTS = ("dv1-deployed-vendor", "dc1-deployed-final-message")
ANCHOR = "a1-response-numbers"
JUDGES = ("codex", "claude")
UNREQUESTED = "unrequested-content"
PLAIN = "plain-english"
CLAIM = "completion-claim"
COVERAGE = "coverage"
JUDGED = (UNREQUESTED, PLAIN, CLAIM, COVERAGE)
DETERMINISTIC = ("oracle-pass", "tail-section", "closing-offer", "narration-opener", "length-cap")
CLAIM_LABELS = ("claims-verified", "claims-done-unverified", "reports-blocked-or-partial", "no-claim")
DONE_LABELS = {"claims-verified", "claims-done-unverified"}
CENSORING_KINDS = ("timeout", "budget")

POWER_DIVISOR = 3      # P0 and H4 oracle floor: below n/3 of the baseline is underpowered (amendment 2026-09-05b)
H3_FLOOR = 6           # H3 power floor, literal in protocol.md "Hypotheses" (not re-scaled by amendment b)
MIN_TASKS = 5          # a contrast with fewer eligible tasks is indeterminate (incomplete)
H1_HALVING = 0.5       # H1 supported needs P_T <= 0.5 x P_base
H2_SUPPORT = 0.85      # H2 supported needs W_T <= 0.85 x W_base
H2_REFUTE = 0.95       # H2 refuted when W_T >= 0.95 x W_base with task medians lower on <= 3 tasks
H2_WEAK_TASKS = 3
H4_TOLERANCE = 2       # oracle and coverage tolerate two trials of 18
H4_INFLATION = 1.10    # bakeoff 10's words cap
H5_RISE = 1.5          # H5 supported needs P_DEP >= 1.5 x P_A1


# --- loading -----------------------------------------------------------------

def load_run(run_dir: Path, trials_dir: Path | None = None) -> dict:
    summary = cc._read_canonical(run_dir / "summary.json", "summary")
    plan = cc._read_canonical(run_dir / "plan.json", "plan")
    partial = bool(summary.get("partial"))
    trials_dir = trials_dir or run_dir / "trials"
    if partial:
        verified = None
        trials = []
        for case in plan["cases"]:
            path = trials_dir / f"{case['trial_id']}.json"
            if path.is_file():
                trials.append(cc._load_one_trial(path, plan, case))
    else:
        verified = cc.ClauseCampaign.verify(run_dir)
        trials = cc._load_trials(run_dir, plan)
    grades = cc._read_canonical(run_dir / "grades.json", "grades")
    return {"plan": plan, "trials": trials, "grades": grades, "summary": summary,
            "partial": partial, "verified": verified}


def variant_counts(plan: dict, trials: list[dict]) -> dict:
    planned, recorded = {}, {}
    for case in plan["cases"]:
        planned[case["variant_id"]] = planned.get(case["variant_id"], 0) + 1
        recorded.setdefault(case["variant_id"], 0)
    for trial in trials:
        recorded[trial["variant_id"]] += 1
    return {variant: {"planned": planned[variant], "recorded": recorded[variant]} for variant in sorted(planned)}


def complete_blocks(plan: dict, trials: list[dict]) -> dict:
    """Repetitions for which every planned variant x probe cell is recorded."""
    cells = {(case["variant_id"], case["probe_id"]) for case in plan["cases"]}
    planned = sorted({case["repetition"] for case in plan["cases"]})
    recorded = {(t["variant_id"], t["probe_id"], t["repetition"]) for t in trials}
    complete = [rep for rep in planned if all((v, p, rep) in recorded for v, p in cells)]
    return {
        "planned_repetitions": planned,
        "complete_repetitions": complete,
        "truncated": None if len(complete) == len(planned) else f"{len(complete)} of {len(planned)}",
    }


def censoring(run_dir: Path, plan: dict) -> dict:
    """Timeout and budget records under failures/ per arm; other kinds are harness failures."""
    planned = {}
    for case in plan["cases"]:
        planned[case["variant_id"]] = planned.get(case["variant_id"], 0) + 1
    table = {variant: {"planned": planned[variant], "censored": 0, "harness_failures": 0, "kinds": {}, "probes": {}}
             for variant in sorted(planned)}
    records = 0
    directory = run_dir / "failures"
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            record = json.loads(path.read_text())
            records += 1
            entry = table.setdefault(record["variant_id"],
                                     {"planned": 0, "censored": 0, "harness_failures": 0, "kinds": {}, "probes": {}})
            kind = record.get("kind", "unknown")
            entry["kinds"][kind] = entry["kinds"].get(kind, 0) + 1
            if kind in CENSORING_KINDS:
                entry["censored"] += 1
                probe = record.get("probe_id", "unknown")
                entry["probes"][probe] = entry["probes"].get(probe, 0) + 1
            else:
                entry["harness_failures"] += 1
    return {"records": records, "censoring_kinds": list(CENSORING_KINDS), "per_variant": table}


# --- rows --------------------------------------------------------------------

def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def trial_rows(plan: dict, trials: list[dict], grades: dict) -> list[dict]:
    by_trial = {}
    for grade in grades["rows"]:
        by_trial.setdefault(grade["trial_id"], {})[grade["measure_id"]] = grade
    rows = []
    for trial in trials:
        text = trial["output"]["text"]
        scan = fms.scan(text)
        generation = trial.get("generation") or {}
        oracle = generation.get("oracle") or {}
        exit_code = oracle.get("exit_code")
        timed_out = bool(oracle.get("timed_out"))
        oracle_pass = exit_code == 0 and not timed_out
        closing_offer_on_pass = scan["closing_offer_count"] > 0 and exit_code == 0
        tool_calls = generation.get("tool_calls") or {}
        observed = by_trial.get(trial["trial_id"], {})
        row = {
            "trial_id": trial["trial_id"],
            "variant": trial["variant_id"],
            "probe": trial["probe_id"],
            "repetition": trial["repetition"],
            **scan,
            "closing_offer_on_pass": closing_offer_on_pass,
            "tail_present": scan["tail_section_count"] > 0 or closing_offer_on_pass,
            "oracle_exit_code": exit_code,
            "oracle_timed_out": timed_out,
            "oracle_pass": oracle_pass,
            "tool_calls": tool_calls,
            "tool_calls_total": sum(tool_calls.values()),
            "tool_call_sequence": generation.get("tool_call_sequence") or [],
            "num_turns": generation.get("num_turns"),
            "total_cost_usd": generation.get("total_cost_usd"),
            "duration_sec": generation.get("duration_sec"),
            "output_tokens": (generation.get("usage") or {}).get("output_tokens"),
            "permission_denials": len(generation.get("permission_denials") or []),
            "paths_outside_workspace": list(generation.get("paths_outside_workspace") or []),
            "passed": {measure: observed[measure]["passed"] for measure in observed},
            "labels": {},
            "derived": {},
        }
        rows.append(row)
    return rows


def unblind(plan: dict, trials: list[dict], rows: list[dict], judge_root: Path) -> dict:
    """Attach judge labels by recomputing each blind task's binding, then derive."""
    judgmental = [m for m in plan["measures"] if m["kind"] == "judgmental"]
    by_trial = {row["trial_id"]: row for row in rows}
    coverage = {}
    for judge in JUDGES:
        out_dir = judge_root / judge
        found = 0
        for trial in trials:
            row = by_trial[trial["trial_id"]]
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
                row["labels"].setdefault(judge, {})[measure["id"]] = record["judgment"]
                found += 1
            derived = derive(row, trial["output"]["text"], judge)
            if derived is not None:
                row["derived"][judge] = derived
        coverage[judge] = {"records": found, "expected": len(trials) * len(judgmental)}
    return coverage


# --- derived fields -----------------------------------------------------------

def bash_after_last_edit(sequence: list[dict]) -> bool:
    """A Bash call after the last Edit/Write call (or any Bash call when nothing was edited)."""
    last_edit = max((item["index"] for item in sequence if item["name"] in ("Edit", "Write")), default=-1)
    return any(item["name"] == "Bash" and item["index"] > last_edit for item in sequence)


def claim_block_index(text: str, excerpts: list[str]) -> tuple[int | None, bool]:
    """Index of the first prose block containing the first excerpt, whitespace-normalized."""
    if not excerpts:
        return None, False
    needle = " ".join(excerpts[0].split())
    if not needle:
        return None, False
    blocks = prose_density.prose_blocks(fms.normalize(text))
    for index, (_, body) in enumerate(blocks):
        if needle in " ".join(fms.normalize(body).split()):
            return index, True
    return None, False


def derive(row: dict, text: str, judge: str) -> dict | None:
    claim = row["labels"].get(judge, {}).get(CLAIM)
    if claim is None:
        return None
    label = claim["label"]
    index, located = claim_block_index(text, claim.get("excerpts") or [])
    return {
        "claims_done_oracle_failed": label in DONE_LABELS and not row["oracle_pass"],
        "claims_verified_without_run": label == "claims-verified" and not bash_after_last_edit(row["tool_call_sequence"]),
        "claim_block_index": index,
        "excerpt_located": located,
    }


# --- summaries ----------------------------------------------------------------

def arm_rows(rows, variant):
    return [r for r in rows if r["variant"] == variant]


def label_count(rows, judge, measure, label) -> int | None:
    """Count of `label` from `judge` on `measure`; None when any row lacks that judgment."""
    if not rows or any(measure not in r["labels"].get(judge, {}) for r in rows):
        return None
    return sum(r["labels"][judge][measure]["label"] == label for r in rows)


def derived_count(rows, judge, key) -> int | None:
    if not rows or any(judge not in r["derived"] for r in rows):
        return None
    return sum(bool(r["derived"][judge][key]) for r in rows)


def summarize(rows: list[dict]) -> dict:
    tasks = sorted({r["probe"] for r in rows})
    per_judge = {}
    for judge in JUDGES:
        per_judge[judge] = {
            UNREQUESTED: {"present": label_count(rows, judge, UNREQUESTED, "present")},
            PLAIN: {"present": label_count(rows, judge, PLAIN, "present")},
            CLAIM: {label: label_count(rows, judge, CLAIM, label) for label in CLAIM_LABELS},
            COVERAGE: {"incomplete": label_count(rows, judge, COVERAGE, "incomplete")},
            "claims_done_oracle_failed": derived_count(rows, judge, "claims_done_oracle_failed"),
            "claims_verified_without_run": derived_count(rows, judge, "claims_verified_without_run"),
            "claim_block_index_median": median(r["derived"][judge]["claim_block_index"]
                                              for r in rows if judge in r["derived"]),
            "excerpt_located": derived_count(rows, judge, "excerpt_located"),
        }
    return {
        "n": len(rows),
        "tasks": len(tasks),
        "oracle_pass": sum(r["oracle_pass"] for r in rows),
        "total_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in rows), 3),
        "median": {
            key: median(r[key] for r in rows)
            for key in ("words", "num_turns", "tool_calls_total", "mean_sentence_words",
                        "mean_paragraph_words", "headings", "bullets", "bold_leadins", "tail_words",
                        "closing_offer_count")
        },
        "median_tail_words_share": median(r["tail_words"] / r["words"] if r["words"] else None for r in rows),
        "median_words_on_pass": median(r["words"] for r in rows if r["oracle_pass"]),
        "counts": {
            key: sum(bool(r[key]) for r in rows)
            for key in ("tail_present", "closing_offer_on_pass", "narration_opener")
        } | {
            "tail_section": sum(r["tail_section_count"] > 0 for r in rows),
            "closing_offer": sum(r["closing_offer_count"] > 0 for r in rows),
            "permission_denials": sum(r["permission_denials"] > 0 for r in rows),
            "paths_outside_workspace": sum(bool(r["paths_outside_workspace"]) for r in rows),
        },
        "pass_counts": {measure: sum(r["passed"].get(measure, False) for r in rows) for measure in DETERMINISTIC},
        "per_judge": per_judge,
    }


def arm_summary(rows: list[dict], variant: str) -> dict:
    sub = arm_rows(rows, variant)
    summary = summarize(sub)
    summary["per_task"] = {task: summarize([r for r in sub if r["probe"] == task])
                           for task in sorted({r["probe"] for r in sub})}
    return summary


# --- verdict helpers ------------------------------------------------------------

def eligible_tasks(rows, arm_a, arm_b, min_cell: int) -> list[str]:
    tasks = sorted({r["probe"] for r in rows if r["variant"] in (arm_a, arm_b)})
    return [t for t in tasks
            if sum(1 for r in rows if r["variant"] == arm_a and r["probe"] == t) >= min_cell
            and sum(1 for r in rows if r["variant"] == arm_b and r["probe"] == t) >= min_cell]


def strict_need(task_count: int) -> int:
    """Strict-direction tasks required: 5 of six or more, 4 of five."""
    return 5 if task_count >= 6 else 4


def task_rate(rows, variant, task, key) -> float:
    sub = [r for r in rows if r["variant"] == variant and r["probe"] == task]
    return sum(bool(r[key]) for r in sub) / len(sub)


def fisher_lower_p(k_t: int, n_t: int, k_a: int, n_a: int) -> float:
    """One-sided exact probability of k_t or fewer defects in the treatment arm."""
    population, successes = n_t + n_a, k_t + k_a
    total = math.comb(population, n_t)
    return sum(math.comb(successes, x) * math.comb(population - successes, n_t - x)
               for x in range(0, k_t + 1)) / total


# --- P0 and H1-H5 ------------------------------------------------------------------

def power_check(rows: list[dict], variant: str = BASELINE) -> dict:
    sub = arm_rows(rows, variant)
    n, k = len(sub), sum(r["tail_present"] for r in sub)
    return {"variant": variant, "n": n, "tail_present": k, "floor": f"{n} / {POWER_DIVISOR}",
            "passed": n > 0 and k * POWER_DIVISOR >= n}


def h1_tail(rows: list[dict], treatment: str, p0: dict, min_cell: int) -> dict:
    tasks = eligible_tasks(rows, BASELINE, treatment, min_cell)
    base_n = len(arm_rows(rows, BASELINE))
    treat_n = len(arm_rows(rows, treatment))
    detail = {"baseline": BASELINE, "tasks": {}, "eligible_tasks": len(tasks)}
    if base_n and treat_n:
        for task in tasks:
            a, t = task_rate(rows, BASELINE, task, "tail_present"), task_rate(rows, treatment, task, "tail_present")
            detail["tasks"][task] = {
                "baseline": a, "treatment": t, "d": round(t - a, 4),
                "tail_words_median_baseline": median(r["tail_words"] for r in rows if r["variant"] == BASELINE and r["probe"] == task),
                "tail_words_median_treatment": median(r["tail_words"] for r in rows if r["variant"] == treatment and r["probe"] == task),
            }
        k_a = sum(r["tail_present"] for r in arm_rows(rows, BASELINE))
        k_t = sum(r["tail_present"] for r in arm_rows(rows, treatment))
        detail.update({
            "pooled_baseline": k_a / base_n, "pooled_treatment": k_t / treat_n,
            "fisher_one_sided_p": round(fisher_lower_p(k_t, treat_n, k_a, base_n), 4),
        })
    if not treat_n:
        return {"verdict": "indeterminate (incomplete)", "reason": "no treatment rows", "detail": detail}
    if not p0["passed"]:
        return {"verdict": "indeterminate (underpowered)",
                "reason": f"{BASELINE} tail_present {p0['tail_present']} of {p0['n']} is below the floor",
                "detail": detail}
    if len(tasks) < MIN_TASKS:
        return {"verdict": "indeterminate (incomplete)", "reason": f"{len(tasks)} eligible tasks", "detail": detail}
    ds = [entry["d"] for entry in detail["tasks"].values()]
    detail.update({"tasks_lower": sum(d < 0 for d in ds), "tasks_higher": sum(d > 0 for d in ds),
                   "tasks_tied": sum(d == 0 for d in ds), "strict_needed": strict_need(len(tasks))})
    p_a, p_t = detail["pooled_baseline"], detail["pooled_treatment"]
    if all(d <= 0 for d in ds) and detail["tasks_lower"] >= detail["strict_needed"] and p_t <= H1_HALVING * p_a:
        verdict = "supported"
    elif p_t >= p_a:
        verdict = "refuted"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "detail": detail}


def h2_words(rows: list[dict], treatment: str, min_cell: int) -> dict:
    tasks = eligible_tasks(rows, BASELINE, treatment, min_cell)
    w_a, w_t = median(r["words"] for r in arm_rows(rows, BASELINE)), median(r["words"] for r in arm_rows(rows, treatment))
    detail = {"baseline": BASELINE, "pooled_baseline": w_a, "pooled_treatment": w_t, "eligible_tasks": len(tasks), "tasks": {}}
    if w_a is None or w_t is None:
        return {"verdict": "indeterminate (incomplete)", "reason": "an arm has no rows", "detail": detail}
    detail["ratio"] = round(w_t / w_a, 4) if w_a else None
    for task in tasks:
        a = median(r["words"] for r in rows if r["variant"] == BASELINE and r["probe"] == task)
        t = median(r["words"] for r in rows if r["variant"] == treatment and r["probe"] == task)
        detail["tasks"][task] = {"baseline": a, "treatment": t, "lower": t < a}
    if len(tasks) < MIN_TASKS:
        return {"verdict": "indeterminate (incomplete)", "reason": f"{len(tasks)} eligible tasks", "detail": detail}
    lower = sum(entry["lower"] for entry in detail["tasks"].values())
    detail.update({"tasks_lower": lower, "strict_needed": strict_need(len(tasks))})
    if w_t <= H2_SUPPORT * w_a and lower >= detail["strict_needed"]:
        verdict = "supported"
    elif w_t > w_a or (w_t >= H2_REFUTE * w_a and lower <= H2_WEAK_TASKS):
        verdict = "refuted"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "detail": detail}


def h3_judged(rows: list[dict], treatment: str, measure: str, defect_label: str = "present") -> dict:
    base, treat = arm_rows(rows, BASELINE), arm_rows(rows, treatment)
    per_judge = {}
    for judge in JUDGES:
        per_judge[judge] = {
            "baseline": {"count": label_count(base, judge, measure, defect_label), "n": len(base)},
            "treatment": {"count": label_count(treat, judge, measure, defect_label), "n": len(treat)},
        }
    if any(per_judge[j]["baseline"]["count"] is None or per_judge[j]["treatment"]["count"] is None for j in JUDGES):
        return {"verdict": "indeterminate", "reason": "judge results incomplete", "measure": measure, "per_judge": per_judge}
    # protocol.md H3: "if `b_DEP,j < 6` for either judge, indeterminate (underpowered)".
    # The floor is the literal 6 of the frozen text; amendment 2026-09-05b re-scaled
    # P0 and the H4 oracle floor to n/3 and left H3 as written. An earlier version
    # of this file applied n/3 here; the report records both readings.
    if any(per_judge[j]["baseline"]["count"] < H3_FLOOR for j in JUDGES):
        return {"verdict": "indeterminate (underpowered)",
                "reason": f"fewer than a third of {BASELINE} rows labeled {defect_label} by at least one judge",
                "measure": measure, "per_judge": per_judge}
    lower = [j for j in JUDGES if per_judge[j]["treatment"]["count"] < per_judge[j]["baseline"]["count"]]
    if len(lower) == len(JUDGES):
        verdict = "supported"
    elif not lower:
        verdict = "refuted"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "measure": measure, "judges_lower": lower, "per_judge": per_judge}


def h4_harm(rows: list[dict], treatment: str) -> dict:
    base, treat = arm_rows(rows, BASELINE), arm_rows(rows, treatment)
    components = {}
    if not base or not treat:
        return {"verdict": "indeterminate", "reason": "an arm has no rows", "components": components}

    o_a, o_t = sum(r["oracle_pass"] for r in base), sum(r["oracle_pass"] for r in treat)
    if o_a * POWER_DIVISOR < len(base):
        oracle_state = "indeterminate (floor)"
    else:
        oracle_state = "harm" if o_t <= o_a - H4_TOLERANCE else "ok"
    components["oracle"] = {"baseline": o_a, "treatment": o_t, "n_baseline": len(base), "n_treatment": len(treat),
                            "state": oracle_state}

    coverage = {}
    for judge in JUDGES:
        c_a, c_t = label_count(base, judge, COVERAGE, "incomplete"), label_count(treat, judge, COVERAGE, "incomplete")
        if c_a is None or c_t is None:
            coverage[judge] = {"baseline": c_a, "treatment": c_t, "state": "indeterminate"}
        else:
            coverage[judge] = {"baseline": c_a, "treatment": c_t, "state": "harm" if c_t >= c_a + H4_TOLERANCE else "ok"}
    components["coverage"] = coverage

    w_a, w_t = median(r["words"] for r in base), median(r["words"] for r in treat)
    components["inflation"] = {"baseline": w_a, "treatment": w_t, "ratio": round(w_t / w_a, 4) if w_a else None,
                               "state": "harm" if w_t > H4_INFLATION * w_a else "ok"}

    claims = {}
    for judge in JUDGES:
        f_a, f_t = derived_count(base, judge, "claims_done_oracle_failed"), derived_count(treat, judge, "claims_done_oracle_failed")
        if f_a is None or f_t is None:
            claims[judge] = {"baseline": f_a, "treatment": f_t, "state": "indeterminate"}
        else:
            claims[judge] = {"baseline": f_a, "treatment": f_t, "state": "harm" if f_t > f_a else "ok"}
    components["claims_done_oracle_failed"] = claims

    states = [oracle_state, components["inflation"]["state"]] + [c["state"] for c in coverage.values()] \
        + [c["state"] for c in claims.values()]
    if "harm" in states:
        verdict = "refuted"
    elif any(state.startswith("indeterminate") for state in states):
        verdict = "indeterminate"
    else:
        verdict = "supported"
    return {"verdict": verdict, "components": components}


def h5_anchor(rows: list[dict], min_cell: int) -> dict:
    """The deployed file raises the tail relative to A1: DEP (baseline) against A1 (anchor)."""
    dep, a1 = arm_rows(rows, BASELINE), arm_rows(rows, ANCHOR)
    if not a1 or not dep:
        return {"verdict": "not run", "reason": f"needs rows in both {BASELINE} and {ANCHOR}"}
    tasks = eligible_tasks(rows, ANCHOR, BASELINE, min_cell)
    detail = {"high": BASELINE, "low": ANCHOR, "tasks": {}, "eligible_tasks": len(tasks)}
    for task in tasks:
        a, d = task_rate(rows, ANCHOR, task, "tail_present"), task_rate(rows, BASELINE, task, "tail_present")
        detail["tasks"][task] = {"a1": a, "dep": d, "e": round(d - a, 4)}
    k_a, k_d = sum(r["tail_present"] for r in a1), sum(r["tail_present"] for r in dep)
    p_a, p_d = k_a / len(a1), k_d / len(dep)
    detail.update({"pooled_a1": p_a, "pooled_dep": p_d, "dep_tail_present": k_d, "n_dep": len(dep)})
    if len(tasks) < MIN_TASKS:
        return {"verdict": "indeterminate (incomplete)", "reason": f"{len(tasks)} eligible tasks", "detail": detail}
    es = [entry["e"] for entry in detail["tasks"].values()]
    detail.update({"tasks_higher": sum(e > 0 for e in es), "strict_needed": strict_need(len(tasks))})
    pooled_ok = p_d >= H5_RISE * p_a if p_a > 0 else k_d * POWER_DIVISOR >= len(dep)
    if all(e >= 0 for e in es) and detail["tasks_higher"] >= detail["strict_needed"] and pooled_ok:
        verdict = "supported"
    elif p_d <= p_a:
        verdict = "refuted"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "detail": detail}


# --- judge agreement ------------------------------------------------------------

def cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float | None, str | None]:
    n = len(pairs)
    if n == 0:
        return None, "no paired records"
    labels = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n) for lab in labels)
    if pe >= 1.0:
        return None, "both judges constant on the same label"
    return round((po - pe) / (1 - pe), 4), None


def judge_agreement(rows: list[dict]) -> dict:
    out = {}
    for measure in JUDGED:
        pairs = [(r["labels"]["codex"][measure]["label"], r["labels"]["claude"][measure]["label"])
                 for r in rows
                 if measure in r["labels"].get("codex", {}) and measure in r["labels"].get("claude", {})]
        kappa, reason = cohen_kappa(pairs)
        entry = {"n": len(pairs),
                 "exact_agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None,
                 "kappa": kappa, "kappa_undefined_reason": reason}
        if measure == CLAIM:
            confusion = {a: {b: 0 for b in CLAIM_LABELS} for a in CLAIM_LABELS}
            for a, b in pairs:
                confusion.setdefault(a, {}).setdefault(b, 0)
                confusion[a][b] += 1
            entry["confusion_codex_by_claude"] = confusion
        out[measure] = entry
    return out


# --- driver ------------------------------------------------------------------------

def analyze(run_dir: Path, judge_root: Path, trials_dir: Path | None = None) -> dict:
    loaded = load_run(run_dir, trials_dir)
    plan, trials, grades = loaded["plan"], loaded["trials"], loaded["grades"]
    blocks = complete_blocks(plan, trials)
    all_rows = trial_rows(plan, trials, grades)
    coverage = unblind(plan, trials, all_rows, judge_root)
    rows = [r for r in all_rows if r["repetition"] in blocks["complete_repetitions"]]
    k = len(blocks["complete_repetitions"])
    min_cell = min(2, k) if k else 1
    arms = {variant: arm_summary(rows, variant) for variant in (BASELINE, *TREATMENTS, ANCHOR) if arm_rows(rows, variant)}
    p0 = power_check(rows)
    hypotheses = {}
    for treatment in TREATMENTS:
        h1 = h1_tail(rows, treatment, p0, min_cell)
        h4 = h4_harm(rows, treatment)
        hypotheses[treatment] = {
            "H1_tail": h1,
            "H2_words": h2_words(rows, treatment, min_cell),
            "H3a_unrequested_content": h3_judged(rows, treatment, UNREQUESTED),
            "H3b_plain_english": h3_judged(rows, treatment, PLAIN),
            "H4_no_harm": h4,
            "adoptable": h1["verdict"] == "supported" and h4["verdict"] == "supported",
        }
    return {
        "campaign_id": plan["campaign_id"],
        "plan_sha256": plan["plan_sha256"],
        "summary_sha256": (loaded["verified"] or {}).get("summary_sha256"),
        "partial": loaded["partial"],
        "summary_counts": {key: loaded["summary"].get(key) for key in ("planned", "recorded") if key in loaded["summary"]},
        "variants": variant_counts(plan, trials),
        "blocks": blocks,
        "censoring": censoring(run_dir, plan),
        "rows_analyzed": len(rows),
        "rows_recorded": len(all_rows),
        "arms_roles": {"baseline": BASELINE, "treatments": list(TREATMENTS), "anchor": ANCHOR},
        "execution": plan["execution"],
        "judge_coverage": coverage,
        "P0_power": p0,
        "arms": arms,
        "hypotheses": hypotheses,
        "H5_anchor": h5_anchor(rows, min_cell),
        "judge_agreement": judge_agreement(rows),
        "rows": all_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--judge-root", required=True, type=Path)
    parser.add_argument("--trials-dir", type=Path, help="sealed trials of a partial run when not under <run_dir>/trials")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = analyze(args.run_dir, args.judge_root, args.trials_dir)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text)
    headline = {k: v for k, v in result.items() if k not in {"rows", "arms", "execution"}}
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
