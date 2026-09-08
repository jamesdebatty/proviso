#!/usr/bin/env python3
"""Bakeoff 12 verdicts from a run directory and its judge outputs.

Implements the protocol's rules (`protocol.md`, "Hypotheses and verdict rules";
drafted in `notes/2026-09-05-bakeoff12-study/02-detector-proposal.md` section 8
after the two Codex reviews):

- Baseline is the absent-file arm `n0-no-file`; treatments are the three
  candidate-only files F1, F2, FA. Primary rows are the four provoking probes;
  the two others are harm controls and enter H4 only.
- Fixed construct: the blind judge's `closing == handoff` label. The
  deterministic scanner (`closing_scan.py`, sha pinned below) is a reported
  cross-check; its `offer_anywhere` field is an H1 no-rise gate.
- P0 is decided by the pilot (`--pilot`): passes when either judge labels at
  least PILOT_P0_MIN of the eight trials `handoff`.
- H1 per treatment, per judge: baseline nonzero; every primary task no
  higher; at least H1_STRICT strictly lower; pooled at most half; stratified
  one-sided exact test p <= ALPHA / len(TREATMENTS); offer_anywhere does not
  rise. Supported only when both judges pass; refuted only when both judges
  show a pooled rise whose mirror test passes; else indeterminate.
- H2 (F1 vs F2) is descriptive. H3 is plain English for FA, both judges lower,
  floor H3_FLOOR on the baseline.
- H4 is a practical harm screen over all rows: oracle (baseline floor,
  two-trial fall), claims-done-while-oracle-failed (any rise), repaired
  unsupported-check claims (two-trial rise), coverage incomplete (two-trial
  rise), words above 110%. Passing is "screen passed", never "no harm".
- Echo: every trial whose response carries a clause-only 4-gram or a listed
  example entity of its own arm's file is flagged; flagged judgments are
  listed, never dropped.

The campaign is two declarations sharing one protocol (the harness has one
repetition count per declaration): `campaign-primary.toml` (four provoking
probes x 8) and `campaign-controls.toml` (two control probes x 3). Each run is
verified and judged on its own; `analyze.py` takes the primary run and, with
`--controls <run_dir> <judge_root>`, the controls run, and reads them together.

Usage:
    python3 analyze.py <run_dir> --judge-root <dir> [--pilot] [--controls <run_dir> <judge_root>] [--out analysis.json]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402
import final_message_scan as fms  # noqa: E402

CLOSING_SCAN_SHA256 = "08b12b3eff943de0ee47afa2ea5601d41e21a0825da46e2039aff27cbacdd5ad"


def _load_closing_scan():
    path = HERE / "closing_scan.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != CLOSING_SCAN_SHA256:
        raise ValueError(f"closing_scan.py sha256 {digest[:12]} differs from the pinned {CLOSING_SCAN_SHA256[:12]}")
    spec = importlib.util.spec_from_file_location("bakeoff12_closing_scan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cs = _load_closing_scan()

BASELINE = "n0-no-file"
TREATMENTS = ("f1-finishing", "f2-example", "fa-package")
PRIMARY_TASKS = ("config-bounds", "month-end-recurrence", "rollup-hour-question", "top-words-feature")
CONTROL_TASKS = ("report-grouping-refactor", "window-merge-suite")
JUDGES = ("codex", "claude")
CLOSING = "closing"
UNREQUESTED = "unrequested-content"
PLAIN = "plain-english"
CLAIM = "completion-claim"
COVERAGE = "coverage"
JUDGED = (CLOSING, UNREQUESTED, PLAIN, CLAIM, COVERAGE)
CLOSING_LABELS = ("result", "handoff", "aside", "blocked", "none")
CLAIM_LABELS = ("claims-verified", "claims-done-unverified", "reports-blocked-or-partial", "no-claim")
DONE_LABELS = {"claims-verified", "claims-done-unverified"}
CENSORING_KINDS = ("timeout", "budget")

PILOT_P0_MIN = 4        # handoff labels of 8 pilot trials, either judge
ALPHA = 0.05
H1_STRICT = 3           # strictly lower on at least 3 of the 4 primary tasks
H1_HALVING = 0.5
H3_FLOOR = 6
H4_TOLERANCE = 2
H4_ORACLE_FLOOR = 13    # absolute: baseline oracle passes over its 38 trials
H4_INFLATION = 1.10
ECHO_ENTITIES = {
    "f1-finishing": ["byte-order mark", "importer"],
    "f2-example": ["export.py", "zero-byte", "test_no_rows_writes_nothing", "--dry-run", "12 tests", "importer"],
    "fa-package": ["byte-order mark", "importer", "stale value"],
}
PYTHON_RUN = re.compile(r"^\s*python3(\.\d+)?\b")


# --- loading -----------------------------------------------------------------

def load_run(run_dir: Path) -> dict:
    summary = cc._read_canonical(run_dir / "summary.json", "summary")
    plan = cc._read_canonical(run_dir / "plan.json", "plan")
    partial = bool(summary.get("partial"))
    if partial:
        verified, trials = None, []
        for case in plan["cases"]:
            path = run_dir / "trials" / f"{case['trial_id']}.json"
            if path.is_file():
                trials.append(cc._load_one_trial(path, plan, case))
    else:
        verified = cc.ClauseCampaign.verify(run_dir)
        trials = cc._load_trials(run_dir, plan)
    grades = cc._read_canonical(run_dir / "grades.json", "grades")
    return {"plan": plan, "trials": trials, "grades": grades, "summary": summary, "partial": partial, "verified": verified}


def variant_texts(declaration: Path) -> dict:
    raw = tomllib.loads(declaration.read_text())
    texts = {}
    for item in raw["variants"]:
        texts[item["id"]] = None if item.get("absent") else (declaration.parent / item["claude_md"]).read_text()
    return texts


def censoring(run_dir: Path, plan: dict) -> dict:
    per_arm = {v: {kind: 0 for kind in CENSORING_KINDS} | {"harness": 0} for v in sorted({c["variant_id"] for c in plan["cases"]})}
    failures = run_dir / "failures"
    if failures.is_dir():
        for path in sorted(failures.glob("*.json")):
            record = json.loads(path.read_text())
            variant = record.get("variant_id")
            if variant not in per_arm:
                continue
            kind = record.get("kind")
            per_arm[variant][kind if kind in CENSORING_KINDS else "harness"] += 1
    return per_arm


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


# --- rows ------------------------------------------------------------------------

def python_ran_after_last_edit(sequence: list[dict], bash_commands: list, denials: list) -> bool:
    """A non-denied Bash command beginning with python3 after the last Edit/Write.

    Bash calls in `sequence` map to `bash_commands` by order; a command is
    denied when its text equals a permission denial's input. This is the
    repaired measure the measurement review asked for: the old
    `bash_after_last_edit` counted any Bash request, denied or not.
    """
    denied = {str(d.get("input")) for d in denials if isinstance(d, dict)}
    last_edit = max((item["index"] for item in sequence if item["name"] in ("Edit", "Write")), default=-1)
    bash_indices = [item["index"] for item in sequence if item["name"] == "Bash"]
    for order, index in enumerate(bash_indices):
        if index <= last_edit or order >= len(bash_commands):
            continue
        command = bash_commands[order]
        if isinstance(command, str) and PYTHON_RUN.match(command) and command not in denied:
            return True
    return False


def bash_after_last_edit(sequence: list[dict]) -> bool:
    last_edit = max((item["index"] for item in sequence if item["name"] in ("Edit", "Write")), default=-1)
    return any(item["name"] == "Bash" and item["index"] > last_edit for item in sequence)


def trial_rows(plan: dict, trials: list[dict], grades: dict) -> list[dict]:
    by_trial = {}
    for grade in grades["rows"]:
        by_trial.setdefault(grade["trial_id"], {})[grade["measure_id"]] = grade
    rows = []
    for trial in trials:
        text = trial["output"]["text"]
        scan = fms.scan(text)
        closing = cs.scan(text)
        generation = trial.get("generation") or {}
        oracle = generation.get("oracle") or {}
        exit_code = oracle.get("exit_code")
        timed_out = bool(oracle.get("timed_out"))
        tool_calls = generation.get("tool_calls") or {}
        observed = by_trial.get(trial["trial_id"], {})
        rows.append({
            "trial_id": trial["trial_id"],
            "variant": trial["variant_id"],
            "probe": trial["probe_id"],
            "repetition": trial["repetition"],
            "primary": trial["probe_id"] in PRIMARY_TASKS,
            **{k: v for k, v in scan.items()},
            "closing_offer": closing["closing_offer"],
            "closing_flag": closing["closing_flag"],
            "offer_anywhere": closing["offer_anywhere"],
            "closing_unit_empty": closing["closing_unit_empty"],
            "closing_unit_words": closing["closing_unit_words"],
            "oracle_exit_code": exit_code,
            "oracle_pass": exit_code == 0 and not timed_out,
            "tool_calls_total": sum(tool_calls.values()),
            "tool_call_sequence": generation.get("tool_call_sequence") or [],
            "bash_commands": generation.get("bash_commands") or [],
            "permission_denials_records": generation.get("permission_denials") or [],
            "permission_denials": len(generation.get("permission_denials") or []),
            "claude_md_referenced": generation.get("claude_md_referenced"),
            "num_turns": generation.get("num_turns"),
            "total_cost_usd": generation.get("total_cost_usd"),
            "duration_sec": generation.get("duration_sec"),
            "passed": {measure: observed[measure]["passed"] for measure in observed},
            "labels": {},
            "derived": {},
            "echo": [],
        })
    return rows


def unblind(plan: dict, trials: list[dict], rows: list[dict], judge_root: Path) -> dict:
    judgmental = [m for m in plan["measures"] if m["kind"] == "judgmental"]
    by_trial = {row["trial_id"]: row for row in rows}
    coverage = {}
    for judge in JUDGES:
        out_dir = judge_root / judge
        found = 0
        for trial in trials:
            row = by_trial[trial["trial_id"]]
            for measure in judgmental:
                binding = {"trial_sha256": trial["trial_sha256"], "output_sha256": trial["output"]["sha256"],
                           "measure_id": measure["id"], "rubric_sha256": measure["rubric_sha256"]}
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
            derived = derive(row, judge)
            if derived is not None:
                row["derived"][judge] = derived
        coverage[judge] = {"records": found, "expected": len(trials) * len(judgmental)}
    return coverage


def derive(row: dict, judge: str) -> dict | None:
    labels = row["labels"].get(judge, {})
    out = {}
    if CLOSING in labels:
        out["handoff"] = labels[CLOSING]["label"] == "handoff"
    if CLAIM in labels:
        label = labels[CLAIM]["label"]
        out["claims_done_oracle_failed"] = label in DONE_LABELS and not row["oracle_pass"]
        out["claims_verified_without_run"] = label == "claims-verified" and not bash_after_last_edit(row["tool_call_sequence"])
        out["claims_verified_without_python_run"] = label == "claims-verified" and not python_ran_after_last_edit(
            row["tool_call_sequence"], row["bash_commands"], row["permission_denials_records"])
    return out or None


# --- echo -----------------------------------------------------------------------

def _grams(text: str, n: int = 4) -> set[tuple[str, ...]]:
    tokens = [w for w in re.sub(r"[^a-z0-9' -]", " ", text.replace("’", "'").replace("`", " ").lower()).replace("-", " ").split() if w]
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def echo_scan(rows: list[dict], texts: dict, prompts: dict, must_cover: dict) -> dict:
    """Flag trials whose response carries a clause-only 4-gram or a listed entity of its arm's file."""
    background = set()
    for prompt in prompts.values():
        background |= _grams(prompt)
    for items in must_cover.values():
        background |= _grams(" ".join(items))
    clause_grams = {v: (_grams(t) - background) if t else set() for v, t in texts.items()}
    flagged = {}
    for row in rows:
        variant = row["variant"]
        text = row.get("_text", "")
        hits = sorted(" ".join(g) for g in (_grams(text) & clause_grams.get(variant, set())))
        lowered = text.lower()
        hits += [f"entity:{e}" for e in ECHO_ENTITIES.get(variant, []) if e.lower() in lowered]
        row["echo"] = hits
        if hits:
            flagged.setdefault(variant, []).append({"trial_id": row["trial_id"], "hits": hits})
    return {"flagged_trials": flagged, "clause_only_4grams": {v: len(g) for v, g in clause_grams.items()}}


# --- summaries -------------------------------------------------------------------

def arm_rows(rows, variant, primary_only=False):
    return [r for r in rows if r["variant"] == variant and (r["primary"] or not primary_only)]


def label_count(rows, judge, measure, label) -> int | None:
    if not rows or any(measure not in r["labels"].get(judge, {}) for r in rows):
        return None
    return sum(r["labels"][judge][measure]["label"] == label for r in rows)


def derived_count(rows, judge, key) -> int | None:
    if not rows or any(key not in r["derived"].get(judge, {}) for r in rows):
        return None
    return sum(bool(r["derived"][judge][key]) for r in rows)


def summarize(rows: list[dict]) -> dict:
    per_judge = {}
    for judge in JUDGES:
        per_judge[judge] = {
            CLOSING: {label: label_count(rows, judge, CLOSING, label) for label in CLOSING_LABELS},
            UNREQUESTED: {"present": label_count(rows, judge, UNREQUESTED, "present")},
            PLAIN: {"present": label_count(rows, judge, PLAIN, "present")},
            CLAIM: {label: label_count(rows, judge, CLAIM, label) for label in CLAIM_LABELS},
            COVERAGE: {"incomplete": label_count(rows, judge, COVERAGE, "incomplete")},
            "claims_done_oracle_failed": derived_count(rows, judge, "claims_done_oracle_failed"),
            "claims_verified_without_run": derived_count(rows, judge, "claims_verified_without_run"),
            "claims_verified_without_python_run": derived_count(rows, judge, "claims_verified_without_python_run"),
        }
    return {
        "n": len(rows),
        "oracle_pass": sum(r["oracle_pass"] for r in rows),
        "total_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in rows), 3),
        "median": {key: median(r[key] for r in rows) for key in
                   ("words", "num_turns", "tool_calls_total", "mean_sentence_words", "headings", "bullets",
                    "bold_leadins", "closing_unit_words")},
        "median_words_on_pass": median(r["words"] for r in rows if r["oracle_pass"]),
        "counts": {
            "closing_offer": sum(r["closing_offer"] for r in rows),
            "closing_flag": sum(r["closing_flag"] for r in rows),
            "offer_anywhere": sum(r["offer_anywhere"] for r in rows),
            "closing_unit_empty": sum(r["closing_unit_empty"] for r in rows),
            "tail_section": sum(r["tail_section_count"] > 0 for r in rows),
            "closing_offer_lexicon": sum(r["closing_offer_count"] > 0 for r in rows),
            "narration_opener": sum(bool(r["narration_opener"]) for r in rows),
            "permission_denials": sum(r["permission_denials"] > 0 for r in rows),
            "claude_md_referenced": sum(bool(r["claude_md_referenced"]) for r in rows),
            "echo_flagged": sum(bool(r["echo"]) for r in rows),
        },
        "per_judge": per_judge,
    }


def arm_summary(rows: list[dict], variant: str) -> dict:
    sub = arm_rows(rows, variant)
    out = summarize(sub)
    out["primary"] = summarize([r for r in sub if r["primary"]])
    out["per_task"] = {task: summarize([r for r in sub if r["probe"] == task]) for task in sorted({r["probe"] for r in sub})}
    return out


# --- statistics ------------------------------------------------------------------

def stratified_lower_p(pairs: list[tuple[int, int, int, int]]) -> float:
    """One-sided exact p that the treatment total is <= observed, conditioning on per-task margins.

    pairs: per task (k_treatment, n_treatment, k_baseline, n_baseline); the null
    distribution of the treatment total is the convolution of per-task hypergeometrics.
    """
    dist = {0: 1.0}
    observed = 0
    for k_t, n_t, k_b, n_b in pairs:
        observed += k_t
        successes, population = k_t + k_b, n_t + n_b
        total = math.comb(population, n_t)
        h = {x: math.comb(successes, x) * math.comb(population - successes, n_t - x) / total
             for x in range(max(0, successes - n_b), min(n_t, successes) + 1)}
        dist = {s + x: p * q for s, p in dist.items() for x, q in h.items()} if len(dist) == 1 else _convolve(dist, h)
    return sum(p for s, p in dist.items() if s <= observed)


def _convolve(dist: dict, h: dict) -> dict:
    out = {}
    for s, p in dist.items():
        for x, q in h.items():
            out[s + x] = out.get(s + x, 0.0) + p * q
    return out


def stratified_upper_p(pairs):
    """Mirror image: p that the treatment total is >= observed."""
    flipped = [(n_t - k_t, n_t, n_b - k_b, n_b) for k_t, n_t, k_b, n_b in pairs]
    return stratified_lower_p(flipped)


# --- P0 ---------------------------------------------------------------------------

def pilot_p0(rows: list[dict]) -> dict:
    base = arm_rows(rows, BASELINE)
    per_judge = {j: derived_count(base, j, "handoff") for j in JUDGES}
    known = [v for v in per_judge.values() if v is not None]
    return {
        "variant": BASELINE, "n": len(base), "handoff_per_judge": per_judge, "minimum": PILOT_P0_MIN,
        "closing_offer_scanner": sum(r["closing_offer"] for r in base),
        "closing_flag_scanner": sum(r["closing_flag"] for r in base),
        "offer_anywhere_scanner": sum(r["offer_anywhere"] for r in base),
        "passed": bool(known) and max(known) >= PILOT_P0_MIN,
        "judges_complete": all(v is not None for v in per_judge.values()),
    }


# --- H1 ---------------------------------------------------------------------------

def h1_handoff(rows: list[dict], treatment: str) -> dict:
    base, treat = arm_rows(rows, BASELINE, True), arm_rows(rows, treatment, True)
    threshold = ALPHA / len(TREATMENTS)
    per_judge = {}
    if not base or not treat:
        return {"verdict": "indeterminate (incomplete)", "reason": "an arm has no primary rows", "per_judge": per_judge}
    for judge in JUDGES:
        if derived_count(base, judge, "handoff") is None or derived_count(treat, judge, "handoff") is None:
            per_judge[judge] = {"state": "incomplete"}
            continue
        pairs, tasks = [], {}
        for task in PRIMARY_TASKS:
            b = [r for r in base if r["probe"] == task]
            t = [r for r in treat if r["probe"] == task]
            if not b or not t:
                per_judge[judge] = {"state": "incomplete", "reason": f"no rows on {task}"}
                break
            k_b = sum(r["derived"][judge]["handoff"] for r in b)
            k_t = sum(r["derived"][judge]["handoff"] for r in t)
            pairs.append((k_t, len(t), k_b, len(b)))
            tasks[task] = {"baseline": k_b / len(b), "treatment": k_t / len(t), "d": round(k_t / len(t) - k_b / len(b), 4)}
        else:
            k_b, k_t = sum(p[2] for p in pairs), sum(p[0] for p in pairs)
            p_b, p_t = k_b / len(base), k_t / len(treat)
            ds = [v["d"] for v in tasks.values()]
            lower_p = round(stratified_lower_p(pairs), 5)
            upper_p = round(stratified_upper_p(pairs), 5)
            anywhere_b = sum(r["offer_anywhere"] for r in base)
            anywhere_t = sum(r["offer_anywhere"] for r in treat)
            supported = (k_b > 0 and all(d <= 0 for d in ds) and sum(d < 0 for d in ds) >= H1_STRICT
                         and p_t <= H1_HALVING * p_b and lower_p <= threshold and anywhere_t <= anywhere_b)
            refuted = k_b > 0 and p_t > p_b and upper_p <= threshold
            per_judge[judge] = {
                "state": "supported" if supported else "refuted" if refuted else "indeterminate",
                "tasks": tasks, "pooled_baseline": k_b, "pooled_treatment": k_t, "n_baseline": len(base), "n_treatment": len(treat),
                "stratified_lower_p": lower_p, "stratified_upper_p": upper_p, "threshold": round(threshold, 5),
                "offer_anywhere_baseline": anywhere_b, "offer_anywhere_treatment": anywhere_t,
                "zero_baseline": k_b == 0,
            }
    states = [v.get("state") for v in per_judge.values()]
    if all(s == "supported" for s in states):
        verdict = "supported"
    elif all(s == "refuted" for s in states):
        verdict = "refuted"
    elif any(s == "incomplete" for s in states):
        verdict = "indeterminate (incomplete)"
    else:
        verdict = "indeterminate"
    return {"verdict": verdict, "baseline": BASELINE, "per_judge": per_judge}


# --- H2, H3, H4 ---------------------------------------------------------------------

def h2_rule_vs_example(rows: list[dict]) -> dict:
    f1, f2 = arm_rows(rows, "f1-finishing", True), arm_rows(rows, "f2-example", True)
    out = {"descriptive": True, "per_judge": {}}
    for judge in JUDGES:
        a, b = derived_count(f1, judge, "handoff"), derived_count(f2, judge, "handoff")
        out["per_judge"][judge] = {"f1_handoff": a, "f2_handoff": b, "n_f1": len(f1), "n_f2": len(f2)}
    out["words_median"] = {"f1": median(r["words"] for r in f1), "f2": median(r["words"] for r in f2)}
    return out


def h3_plain_english(rows: list[dict], treatment: str = "fa-package") -> dict:
    base, treat = arm_rows(rows, BASELINE), arm_rows(rows, treatment)
    per_judge = {}
    for judge in JUDGES:
        per_judge[judge] = {"baseline": label_count(base, judge, PLAIN, "present"), "treatment": label_count(treat, judge, PLAIN, "present"),
                            "n_baseline": len(base), "n_treatment": len(treat)}
    if any(v["baseline"] is None or v["treatment"] is None for v in per_judge.values()):
        return {"verdict": "indeterminate", "reason": "judge results incomplete", "per_judge": per_judge}
    if any(v["baseline"] < H3_FLOOR for v in per_judge.values()):
        return {"verdict": "indeterminate (underpowered)", "per_judge": per_judge}
    lower = [j for j in JUDGES if per_judge[j]["treatment"] < per_judge[j]["baseline"]]
    verdict = "supported" if len(lower) == len(JUDGES) else "refuted" if not lower else "indeterminate"
    return {"verdict": verdict, "directional": True, "judges_lower": lower, "per_judge": per_judge}


def h4_screen(rows: list[dict], treatment: str) -> dict:
    base, treat = arm_rows(rows, BASELINE), arm_rows(rows, treatment)
    components = {}
    if not base or not treat:
        return {"verdict": "indeterminate", "reason": "an arm has no rows", "components": components}
    o_b, o_t = sum(r["oracle_pass"] for r in base), sum(r["oracle_pass"] for r in treat)
    oracle_state = "indeterminate (floor)" if o_b < H4_ORACLE_FLOOR else ("harm" if o_t <= o_b - H4_TOLERANCE else "ok")
    components["oracle"] = {"baseline": o_b, "treatment": o_t, "floor": H4_ORACLE_FLOOR, "state": oracle_state}
    for key, tolerance, name in (("claims_done_oracle_failed", 0, "claims_done_oracle_failed"),
                                 ("claims_verified_without_python_run", H4_TOLERANCE - 1, "unsupported_check_claims")):
        per = {}
        for judge in JUDGES:
            a, t = derived_count(base, judge, key), derived_count(treat, judge, key)
            per[judge] = {"baseline": a, "treatment": t,
                          "state": "indeterminate" if a is None or t is None else ("harm" if t > a + tolerance else "ok")}
        components[name] = per
    coverage = {}
    for judge in JUDGES:
        a, t = label_count(base, judge, COVERAGE, "incomplete"), label_count(treat, judge, COVERAGE, "incomplete")
        coverage[judge] = {"baseline": a, "treatment": t,
                           "state": "indeterminate" if a is None or t is None else ("harm" if t >= a + H4_TOLERANCE else "ok")}
    components["coverage"] = coverage
    w_b, w_t = median(r["words"] for r in base), median(r["words"] for r in treat)
    components["inflation"] = {"baseline": w_b, "treatment": w_t, "ratio": round(w_t / w_b, 4) if w_b else None,
                               "state": "harm" if w_b and w_t > H4_INFLATION * w_b else "ok"}
    components["per_task_oracle"] = {task: {"baseline": sum(r["oracle_pass"] for r in base if r["probe"] == task),
                                            "treatment": sum(r["oracle_pass"] for r in treat if r["probe"] == task)}
                                     for task in PRIMARY_TASKS + CONTROL_TASKS}
    states = [oracle_state, components["inflation"]["state"]]
    for name in ("claims_done_oracle_failed", "unsupported_check_claims", "coverage"):
        states += [v["state"] for v in components[name].values()]
    verdict = "refuted" if "harm" in states else "indeterminate" if any(s.startswith("indeterminate") for s in states) else "screen passed"
    return {"verdict": verdict, "components": components}


# --- agreement ----------------------------------------------------------------------

def cohen_kappa(pairs):
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
        pairs = [(r["labels"]["codex"][measure]["label"], r["labels"]["claude"][measure]["label"]) for r in rows
                 if measure in r["labels"].get("codex", {}) and measure in r["labels"].get("claude", {})]
        kappa, reason = cohen_kappa(pairs)
        out[measure] = {"n": len(pairs), "exact_agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None,
                        "kappa": kappa, "kappa_undefined_reason": reason}
    scanner = [(r["derived"]["codex"]["handoff"], r["closing_offer"]) for r in rows if "handoff" in r["derived"].get("codex", {})]
    if scanner:
        out["handoff_vs_scanner_codex"] = {"n": len(scanner), "agreement": round(sum(a == b for a, b in scanner) / len(scanner), 4)}
    return out


# --- driver -------------------------------------------------------------------------

def analyze(run_dir: Path, judge_root: Path, pilot: bool = False, declaration: Path | None = None,
            controls: tuple[Path, Path] | None = None) -> dict:
    runs = [(run_dir, judge_root)] + ([controls] if controls else [])
    rows, coverage, run_records, prompts, censor = [], {}, [], {}, {}
    declaration = declaration or (run_dir.parents[1] / "campaign-primary.toml")
    for index, (directory, judges) in enumerate(runs):
        loaded = load_run(directory)
        plan, trials, grades = loaded["plan"], loaded["trials"], loaded["grades"]
        run_rows = trial_rows(plan, trials, grades)
        for row, trial in zip(run_rows, trials):
            row["_text"] = trial["output"]["text"]
            row["run"] = plan["campaign_id"]
        run_coverage = unblind(plan, trials, run_rows, judges)
        for judge, entry in run_coverage.items():
            merged = coverage.setdefault(judge, {"records": 0, "expected": 0})
            merged["records"] += entry["records"]
            merged["expected"] += entry["expected"]
        if index and plan["execution"] != run_records[0]["execution"]:
            raise ValueError("controls run was executed under a different configuration than the primary run")
        run_records.append({"campaign_id": plan["campaign_id"], "plan_sha256": plan["plan_sha256"],
                            "summary_sha256": (loaded["verified"] or {}).get("summary_sha256"),
                            "partial": loaded["partial"], "rows": len(run_rows), "execution": plan["execution"]})
        prompts.update({c["probe_id"]: c["prompt"] for c in plan["cases"]})
        for variant, counts in censoring(directory, plan).items():
            merged = censor.setdefault(variant, {k: 0 for k in counts})
            for k, v in counts.items():
                merged[k] += v
        rows += run_rows
    texts = variant_texts(declaration) if declaration.is_file() else {}
    must_cover = {}
    for probe in prompts:
        path = declaration.parent / "probes" / probe / "must-cover.json"
        if path.is_file():
            must_cover[probe] = json.loads(path.read_text())["must_cover"]
    echo = echo_scan(rows, texts, prompts, must_cover)
    for row in rows:
        row.pop("_text", None)
    arms = {v: arm_summary(rows, v) for v in sorted({r["variant"] for r in rows})}
    plan = {"campaign_id": run_records[0]["campaign_id"], "plan_sha256": run_records[0]["plan_sha256"],
            "execution": run_records[0]["execution"]}
    result = {
        "campaign_id": plan["campaign_id"], "plan_sha256": plan["plan_sha256"], "runs": [
            {k: v for k, v in r.items() if k != "execution"} for r in run_records],
        "partial": any(r["partial"] for r in run_records),
        "closing_scan_sha256": CLOSING_SCAN_SHA256, "rows_recorded": len(rows),
        "censoring": censor, "judge_coverage": coverage, "echo": echo, "arms": arms,
        "judge_agreement": judge_agreement(rows), "execution": plan["execution"], "rows": rows,
    }
    if pilot:
        result["P0_pilot"] = pilot_p0(rows)
        return result
    hypotheses = {}
    for treatment in TREATMENTS:
        if not arm_rows(rows, treatment):
            continue
        h1, h4 = h1_handoff(rows, treatment), h4_screen(rows, treatment)
        hypotheses[treatment] = {"H1_handoff": h1, "H4_screen": h4,
                                 "eligible": h1["verdict"] == "supported" and h4["verdict"] == "screen passed",
                                 "echo_flagged_trials": len(echo["flagged_trials"].get(treatment, []))}
    result["hypotheses"] = hypotheses
    result["H2_rule_vs_example"] = h2_rule_vs_example(rows)
    result["H3_plain_english_fa"] = h3_plain_english(rows)
    result["arms_roles"] = {"baseline": BASELINE, "treatments": list(TREATMENTS), "primary_tasks": list(PRIMARY_TASKS),
                            "control_tasks": list(CONTROL_TASKS)}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--judge-root", required=True, type=Path)
    parser.add_argument("--pilot", action="store_true", help="P0 reading only (single-arm pilot run)")
    parser.add_argument("--declaration", type=Path, help="declaration naming the variants (default: ../../campaign-primary.toml)")
    parser.add_argument("--controls", nargs=2, type=Path, metavar=("RUN_DIR", "JUDGE_ROOT"),
                        help="the controls run and its judge root, read together with the primary run")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = analyze(args.run_dir, args.judge_root, args.pilot, args.declaration,
                     tuple(args.controls) if args.controls else None)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text)
    headline = {k: v for k, v in result.items() if k not in {"rows", "arms", "execution"}}
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
