#!/usr/bin/env python3
"""Bakeoff 13 verdicts from a run directory and its judge outputs.

Implements the protocol's rules (`protocol.md`, "Hypotheses and verdict rules";
drafted in `notes/2026-09-05-bakeoff13-study/02-measurement-proposal.md` v2
after the two Codex reviews):

- Baseline is the absent-file arm `n0-no-file`; treatments are G1 and G2;
  F2R is bakeoff 12's F2 byte-identical, a replication arm. Primary rows are
  the four provoking probes; the two others are harm controls.
- H1 per treatment, per judge: bakeoff 12's rule at threshold ALPHA / 2
  (one confirmatory direction per family, two treatments).
- H2 length: geometric-mean ratio over tasks, stratified permutation test
  (PERM_B draws, fixed seed) with p = (extreme + 1) / (B + 1), and a
  one-sided 97.5% upper percentile-bootstrap bound (BOOT_B draws, fixed
  seed) for the separate `non_inferior` flag. Zero-word trials are excluded
  and reported.
- H3: F2R replication checklist with fixed references from bakeoff 12.
- H4: harm screen per screened arm: oracle, false completion, the renamed
  check proxy `no_python_command_after_last_edit`, coverage with the missing
  items listed, and inflation in three parts (primary upper bound, controls
  median ratio, per-task median cap). Passing is "screen passed", never "no
  harm".
- Completeness and echo sensitivity gate eligibility; the descriptive set
  (word roles, per-task distributions, chronology, cross-tabs, frame count)
  reads no verdict.

Usage:
    python3 analyze.py <run_dir> --judge-root <dir> [--controls <run_dir> <judge_root>] [--out analysis.json]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import random
import re
import statistics
import sys
import tomllib
from collections import defaultdict
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
    spec = importlib.util.spec_from_file_location("bakeoff13_closing_scan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cs = _load_closing_scan()

BASELINE = "n0-no-file"
REPLICATION = "f2r-example"
TREATMENTS = ("g1-terse-example", "g2-diff-reader")
SCREENED = (REPLICATION, *TREATMENTS)
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
CHECK_PROXY = "no_python_command_after_last_edit"

ALPHA = 0.05
H1_THRESHOLD = ALPHA / len(TREATMENTS)   # one confirmatory direction per family, Bonferroni within family
H1_STRICT = 3                            # strictly lower on at least 3 of the 4 primary tasks
H1_HALVING = 0.5
H2_SHORTER = 0.90
H2_LONGER = 1.10
H2_MARGIN = 1.10                         # non-inferiority margin on the upper bootstrap bound
H2_MIN_PER_CELL = 2
PERM_B = 20_000
PERM_SEED = 13
BOOT_B = 10_000
BOOT_SEED = 131
BOOT_QUANTILE = 0.975
H3_GMR_REFERENCE = 1.10                  # bakeoff 12 primary median ratio 1.21; all-38 ratio 1.29
H4_TOLERANCE = 2
H4_ORACLE_FLOOR = 13                     # absolute: baseline oracle passes over its 38 trials
H4_CONTROLS_INFLATION = 1.10
H4_TASK_CAP = 1.30
ECHO_ENTITIES = {
    REPLICATION: ["export.py", "zero-byte", "test_no_rows_writes_nothing", "--dry-run", "12 tests", "importer"],
    "g1-terse-example": ["export.py", "--dry-run", "12 tests", "empty query", "missing header", "row count"],
    "g2-diff-reader": [],
}
FRAME = re.compile(r"ran \d+ tests?, all passing", re.I)
COMMAND_SPLIT = re.compile(r"&&|\|\||;|\||\n")
ASSIGNMENT_PREFIX = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")
PYTHON_WORD = re.compile(r"python3(?:\.\d+)?(?:\s|$)")

# Word-role heuristic (descriptive only): the first matching role wins, in this order.
ROLES = [
    ("offer", re.compile(r"say the word|if you(?:'d| would)? (?:rather|want|like|prefer)|happy to|i can (?:add|make|wire)|tell me if|let me know|(?:one|two|a)[- ]line (?:change|revert)|small change|is the line to change|revert", re.I)),
    ("verification", re.compile(r"\btests?\b.*\b(?:pass|passing|green)|all \d+ tests|unittest|verif(?:y|ied|ication)|ran \d+ tests|\bran the (?:cli|suite)|confirmed|checked by hand|i (?:also )?ran|exercised", re.I)),
    ("scope_negative", re.compile(r"\bi (?:left|did not|didn't|have not|haven't)\b|left (?:alone|unchanged|untouched|as[- ]is)|\buntouched\b|out of scope|not (?:part of|in) (?:the|scope)|beyond (?:the|what)|wasn't part of the ask|not asked", re.I)),
    ("decision", re.compile(r"judg[e]?ment call|worth (?:flagging|naming|knowing|your attention|deciding|surfacing)|left open|didn't pin|did not pin|pin down|decided|choice|chose|one thing (?:to|worth)|things? (?:to|worth) flag|caveat|consequence|assum", re.I)),
    ("test_enum", re.compile(r"\bcover(?:s|ing|ed)?\b|cases? for|test_[a-z_]+|`?TopWordsTest|ValidationTest", re.I)),
]
ROLE_NAMES = ("body", "decision", "scope_negative", "verification", "test_enum", "offer", "code")


# --- loading -----------------------------------------------------------------

def load_run(run_dir: Path) -> dict:
    summary = cc._read_canonical(run_dir / "summary.json", "summary")
    plan = cc._read_canonical(run_dir / "plan.json", "plan")
    partial = bool(summary.get("partial"))
    if partial:
        verified = None
        recorded = {case["trial_id"] for case in plan["cases"] if (run_dir / "trials" / f"{case['trial_id']}.json").is_file()}
        trials = [cc._load_one_trial(run_dir / "trials" / f"{case['trial_id']}.json", plan, case)
                  for case in complete_block_cases(plan, recorded)]
    else:
        verified = cc.ClauseCampaign.verify(run_dir)
        trials = cc._load_trials(run_dir, plan)
    grades = cc._read_canonical(run_dir / "grades.json", "grades")
    return {"plan": plan, "trials": trials, "grades": grades, "summary": summary, "partial": partial, "verified": verified}


def complete_block_cases(plan: dict, recorded: set[str]) -> list[dict]:
    """The plan's cases whose whole repetition block is recorded (a partial run reads complete blocks only)."""
    blocks = {}
    for case in plan["cases"]:
        blocks.setdefault(case["repetition"], []).append(case)
    return [case for repetition, cases in sorted(blocks.items()) if all(c["trial_id"] in recorded for c in cases) for case in cases]


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


def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.fmean(values), 3) if values else None


def percentile(values, q):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(q * len(values)))]


# --- rows ------------------------------------------------------------------------

def python_command(command: str) -> bool:
    """python3 (or python3.N) is the first word of any simple command in the line.

    A command-presence rule: the line is split on &&, ||, ;, | and newlines,
    a leading VAR=value prefix is stripped, and the first word is compared.
    Documented limits (protocol.md, "Instruments"): quoted text is split as
    if it were shell syntax, short-circuit execution is ignored, `python3
    --version` counts, and edits made through Bash are not seen.
    """
    for part in COMMAND_SPLIT.split(command):
        part = ASSIGNMENT_PREFIX.sub("", part.strip())
        if PYTHON_WORD.match(part):
            return True
    return False


def python_command_after_last_edit(sequence: list[dict], bash_commands: list, denials: list) -> bool:
    """A non-denied Bash call after the last Edit/Write whose text carries a python3 command."""
    denied = {str(d.get("input")) for d in denials if isinstance(d, dict)}
    last_edit = max((item["index"] for item in sequence if item["name"] in ("Edit", "Write")), default=-1)
    bash_indices = [item["index"] for item in sequence if item["name"] == "Bash"]
    for order, index in enumerate(bash_indices):
        if index <= last_edit or order >= len(bash_commands):
            continue
        command = bash_commands[order]
        if isinstance(command, str) and python_command(command) and command not in denied:
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
            "words": trial["output"]["words"],
            "closing_offer": closing["closing_offer"],
            "closing_flag": closing["closing_flag"],
            "offer_anywhere": closing["offer_anywhere"],
            "closing_unit_empty": closing["closing_unit_empty"],
            "closing_unit_words": closing["closing_unit_words"],
            "frame": bool(FRAME.search(text)),
            "roles": word_roles(text),
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
            "started_utc": generation.get("started_utc"),
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
        out[CHECK_PROXY] = label == "claims-verified" and not python_command_after_last_edit(
            row["tool_call_sequence"], row["bash_commands"], row["permission_denials_records"])
    return out or None


# --- word roles (descriptive) -------------------------------------------------------

def _units(text: str):
    out = []
    for para in re.split(r"\n\s*\n", text):
        lines = para.strip().splitlines()
        if not lines:
            continue
        if lines[0].startswith(("```", "~~~", "|")):
            out.append(("code", para))
            continue
        if any(l.lstrip().startswith(("- ", "* ", "1.", "2.", "3.", "4.")) for l in lines):
            out.extend(("bullet", l) for l in lines)
            continue
        out.extend(("sentence", s) for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*])", para) if s.strip())
    return out


def word_roles(text: str) -> dict:
    counts = {role: 0 for role in ROLE_NAMES}
    for kind, unit in _units(text):
        role = "code"
        if kind != "code":
            role = next((name for name, rx in ROLES if rx.search(unit)), "body")
        counts[role] += len(unit.split())
    return counts


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
            CHECK_PROXY: derived_count(rows, judge, CHECK_PROXY),
        }
    return {
        "n": len(rows),
        "oracle_pass": sum(r["oracle_pass"] for r in rows),
        "total_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in rows), 3),
        "median": {key: median(r[key] for r in rows) for key in
                   ("words", "num_turns", "tool_calls_total", "mean_sentence_words", "paragraphs", "items",
                    "headings", "bullets", "bold_leadins", "closing_unit_words")},
        "words": {"mean": mean(r["words"] for r in rows), "p90": percentile([r["words"] for r in rows], 0.9),
                  "max": max((r["words"] for r in rows), default=None), "zero": sum(r["words"] == 0 for r in rows)},
        "median_words_on_pass": median(r["words"] for r in rows if r["oracle_pass"]),
        "roles_mean": {role: mean(r["roles"][role] for r in rows) for role in ROLE_NAMES},
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
            "frame": sum(r["frame"] for r in rows),
        },
        "per_judge": per_judge,
    }


def arm_summary(rows: list[dict], variant: str) -> dict:
    sub = arm_rows(rows, variant)
    out = summarize(sub)
    out["primary"] = summarize([r for r in sub if r["primary"]])
    out["controls"] = summarize([r for r in sub if not r["primary"]])
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
        dist = _convolve(dist, h)
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


def log_words_by_task(rows: list[dict], variant: str) -> dict:
    return {task: [math.log(r["words"]) for r in rows if r["variant"] == variant and r["probe"] == task and r["words"] > 0]
            for task in PRIMARY_TASKS}


def gmr_stat(base: dict, treat: dict) -> float:
    """Mean over tasks of (mean log-words treatment - mean log-words baseline)."""
    return sum(statistics.fmean(treat[t]) - statistics.fmean(base[t]) for t in base) / len(base)


def permutation_p(base: dict, treat: dict, observed: float, draws: int = PERM_B, seed: int = PERM_SEED) -> tuple[float, float]:
    rng = random.Random(seed)
    pools = [(base[t] + treat[t], len(base[t])) for t in base]
    lower = upper = 0
    for _ in range(draws):
        stat = 0.0
        for pool, n_b in pools:
            rng.shuffle(pool)
            stat += statistics.fmean(pool[n_b:]) - statistics.fmean(pool[:n_b])
        stat /= len(pools)
        lower += stat <= observed + 1e-12
        upper += stat >= observed - 1e-12
    return (lower + 1) / (draws + 1), (upper + 1) / (draws + 1)


def bootstrap_upper(base: dict, treat: dict, draws: int = BOOT_B, seed: int = BOOT_SEED) -> float:
    rng = random.Random(seed)
    values = []
    for _ in range(draws):
        rb = {t: [rng.choice(v) for _ in v] for t, v in base.items()}
        rt = {t: [rng.choice(v) for _ in v] for t, v in treat.items()}
        values.append(gmr_stat(rb, rt))
    values.sort()
    return math.exp(values[min(draws - 1, int(BOOT_QUANTILE * draws))])


# --- H1 ---------------------------------------------------------------------------

def h1_handoff(rows: list[dict], treatment: str, threshold: float = H1_THRESHOLD) -> dict:
    base, treat = arm_rows(rows, BASELINE, True), arm_rows(rows, treatment, True)
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


# --- H2 ---------------------------------------------------------------------------

def h2_length(rows: list[dict], treatment: str, baseline: str = BASELINE, perm_draws: int = PERM_B,
              boot_draws: int = BOOT_B) -> dict:
    base, treat = log_words_by_task(rows, baseline), log_words_by_task(rows, treatment)
    excluded = [r["trial_id"] for r in rows if r["variant"] in (baseline, treatment) and r["primary"] and r["words"] == 0]
    out = {"baseline": baseline, "treatment": treatment, "excluded_zero_words": excluded,
           "n_baseline": sum(len(v) for v in base.values()), "n_treatment": sum(len(v) for v in treat.values())}
    if any(len(base[t]) < H2_MIN_PER_CELL or len(treat[t]) < H2_MIN_PER_CELL for t in PRIMARY_TASKS):
        return {**out, "verdict": "indeterminate (incomplete)", "non_inferior": False, "gmr": None, "upper_bound": None}
    observed = gmr_stat(base, treat)
    gmr = math.exp(observed)
    p_lower, p_upper = permutation_p(base, treat, observed, perm_draws)
    upper = bootstrap_upper(base, treat, boot_draws)
    # Decisions read the unrounded statistics; rounding is for presentation only.
    verdict = ("shorter" if gmr <= H2_SHORTER and p_lower <= ALPHA / 2
               else "longer" if gmr >= H2_LONGER and p_upper <= ALPHA / 2 else "indeterminate")
    words_b = {t: [r["words"] for r in arm_rows(rows, baseline, True) if r["probe"] == t] for t in PRIMARY_TASKS}
    words_t = {t: [r["words"] for r in arm_rows(rows, treatment, True) if r["probe"] == t] for t in PRIMARY_TASKS}
    per_task = {t: {"median_baseline": median(words_b[t]), "median_treatment": median(words_t[t]),
                    "median_ratio": round(median(words_t[t]) / median(words_b[t]), 4) if median(words_b[t]) else None,
                    "gmr": round(math.exp(statistics.fmean(treat[t]) - statistics.fmean(base[t])), 4)}
                for t in PRIMARY_TASKS}
    all_b, all_t = [w for v in words_b.values() for w in v], [w for v in words_t.values() for w in v]
    return {**out, "verdict": verdict, "gmr": round(gmr, 4), "p_lower": round(p_lower, 5), "p_upper": round(p_upper, 5),
            "threshold": ALPHA / 2, "upper_bound": round(upper, 4), "non_inferior": upper < H2_MARGIN, "margin": H2_MARGIN,
            "permutations": perm_draws, "bootstrap_draws": boot_draws,
            "median_ratio": round(median(all_t) / median(all_b), 4) if median(all_b) else None,
            "mean_difference_words": round(statistics.fmean(all_t) - statistics.fmean(all_b), 2),
            "per_task": per_task}


# --- H3 ---------------------------------------------------------------------------

def h3_replication(rows: list[dict], h1: dict, h2: dict, complete: bool) -> dict:
    base, f2r = arm_rows(rows, BASELINE), arm_rows(rows, REPLICATION)
    components = {"a_h1_supported": h1["verdict"] == "supported",
                  "b_gmr_at_least_reference": h2.get("gmr") is not None and h2["gmr"] >= H3_GMR_REFERENCE,
                  "c_coverage_no_higher": None}
    coverage = {}
    for judge in JUDGES:
        a, t = label_count(base, judge, COVERAGE, "incomplete"), label_count(f2r, judge, COVERAGE, "incomplete")
        coverage[judge] = {"baseline": a, "treatment": t, "holds": None if a is None or t is None else t <= a}
    if all(v["holds"] is not None for v in coverage.values()):
        components["c_coverage_no_higher"] = all(v["holds"] for v in coverage.values())
    if not complete:
        outcome = "not evaluable"
    elif all(components.values()):
        outcome = "replicated"
    else:
        failing = [k for k, v in components.items() if not v]
        outcome = f"not replicated (component {', '.join(failing)})"
    g1 = arm_rows(rows, "g1-terse-example")
    descriptive = {"gmr_f2r_vs_g1": None, "closing": {}, "verification_words_mean": {}, "frame": {}}
    lg1, lf2 = log_words_by_task(rows, "g1-terse-example"), log_words_by_task(rows, REPLICATION)
    if g1 and f2r and all(lg1[t] and lf2[t] for t in PRIMARY_TASKS):
        descriptive["gmr_f2r_vs_g1"] = round(math.exp(gmr_stat(lg1, lf2)), 4)
    for arm, sub in ((REPLICATION, f2r), ("g1-terse-example", g1)):
        descriptive["closing"][arm] = {j: {lab: label_count(sub, j, CLOSING, lab) for lab in ("handoff", "aside", "result")} for j in JUDGES}
        descriptive["verification_words_mean"][arm] = mean(r["roles"]["verification"] for r in sub)
        descriptive["frame"][arm] = sum(r["frame"] for r in sub)
    return {"outcome": outcome, "components": components, "coverage": coverage, "gmr_reference": H3_GMR_REFERENCE,
            "gmr": h2.get("gmr"), "f2r_vs_g1": descriptive}


# --- H4 ---------------------------------------------------------------------------

def missing_items(rows: list[dict]) -> dict:
    out = {}
    for judge in JUDGES:
        per_task = defaultdict(lambda: defaultdict(int))
        for r in rows:
            judgment = r["labels"].get(judge, {}).get(COVERAGE)
            if judgment and judgment["label"] == "incomplete":
                for item in judgment.get("excerpts") or ["(no item quoted)"]:
                    per_task[r["probe"]][item] += 1
        out[judge] = {task: dict(items) for task, items in sorted(per_task.items())}
    return out


def h4_screen(rows: list[dict], arm: str, h2: dict) -> dict:
    base, treat = arm_rows(rows, BASELINE), arm_rows(rows, arm)
    components = {}
    if not base or not treat:
        return {"verdict": "indeterminate", "reason": "an arm has no rows", "components": components}
    o_b, o_t = sum(r["oracle_pass"] for r in base), sum(r["oracle_pass"] for r in treat)
    oracle_state = "indeterminate (floor)" if o_b < H4_ORACLE_FLOOR else ("harm" if o_t <= o_b - H4_TOLERANCE else "ok")
    components["oracle"] = {"baseline": o_b, "treatment": o_t, "floor": H4_ORACLE_FLOOR, "state": oracle_state}
    for key, tolerance, name in (("claims_done_oracle_failed", 0, "claims_done_oracle_failed"),
                                 (CHECK_PROXY, H4_TOLERANCE - 1, CHECK_PROXY)):
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
    components["coverage_missing_items"] = {"baseline": missing_items(base), "treatment": missing_items(treat)}
    upper = h2.get("upper_bound")
    # H2's flag is decided on the unrounded bound; the screen reads the flag, not the printed value.
    primary_state = "indeterminate" if upper is None else ("ok" if h2["non_inferior"] else "harm")
    c_b, c_t = median(r["words"] for r in base if not r["primary"]), median(r["words"] for r in treat if not r["primary"])
    controls_ratio = c_t / c_b if c_b and c_t is not None else None
    controls_state = "indeterminate" if controls_ratio is None else ("harm (n = 6)" if controls_ratio > H4_CONTROLS_INFLATION else "ok")
    controls_ratio = round(controls_ratio, 4) if controls_ratio is not None else None
    per_task = {}
    task_states = []
    for task in PRIMARY_TASKS:
        m_b = median(r["words"] for r in base if r["probe"] == task)
        m_t = median(r["words"] for r in treat if r["probe"] == task)
        ratio = m_t / m_b if m_b and m_t is not None else None
        state = "indeterminate" if ratio is None else ("harm (task)" if ratio > H4_TASK_CAP else "ok")
        per_task[task] = {"baseline": m_b, "treatment": m_t, "ratio": round(ratio, 4) if ratio is not None else None, "state": state}
        task_states.append(state)
    components["inflation"] = {
        "primary": {"upper_bound": upper, "margin": H2_MARGIN, "state": primary_state},
        "controls": {"baseline": c_b, "treatment": c_t, "ratio": controls_ratio, "limit": H4_CONTROLS_INFLATION,
                     "n_treatment": sum(not r["primary"] for r in treat), "state": controls_state},
        "per_task": per_task, "cap": H4_TASK_CAP,
    }
    components["per_task_oracle"] = {task: {"baseline": sum(r["oracle_pass"] for r in base if r["probe"] == task),
                                            "treatment": sum(r["oracle_pass"] for r in treat if r["probe"] == task)}
                                     for task in PRIMARY_TASKS + CONTROL_TASKS}
    states = [oracle_state, primary_state, controls_state, *task_states]
    for name in ("claims_done_oracle_failed", CHECK_PROXY, "coverage"):
        states += [v["state"] for v in components[name].values()]
    verdict = ("refuted" if any(s.startswith("harm") for s in states)
               else "indeterminate" if any(s.startswith("indeterminate") for s in states) else "screen passed")
    return {"verdict": verdict, "components": components}


# --- completeness and sensitivity ---------------------------------------------------

def completeness(rows: list[dict], arm: str, planned: dict, censor: dict, both_runs: bool = True) -> dict:
    """Complete: every planned trial of the arm and of N0 recorded across both declarations, none censored or failed."""
    counts = {}
    for variant in (arm, BASELINE):
        recorded = len(arm_rows(rows, variant))
        failed = sum(censor.get(variant, {}).values())
        counts[variant] = {"recorded": recorded, "planned": planned.get(variant, 0), "censored_or_failed": failed}
    complete = both_runs and all(v["recorded"] == v["planned"] and v["planned"] > 0 and v["censored_or_failed"] == 0
                                 for v in counts.values())
    return {"complete": complete, "both_runs_supplied": both_runs, "arms": counts}


def echo_sensitivity(rows: list[dict], arm: str, h1: dict, h4: dict, h2: dict) -> dict:
    """Recompute H1 and H4 with every echo-flagged trial's labels set to the treatment's worst case."""
    flagged = [r["trial_id"] for r in rows if r["variant"] == arm and r["echo"]]
    if not flagged:
        return {"flagged": 0, "h1_verdict": h1["verdict"], "h4_verdict": h4["verdict"], "unchanged": True}
    worst = copy.deepcopy(rows)
    for r in worst:
        if r["trial_id"] in flagged:
            for judge in JUDGES:
                if "handoff" in r["derived"].get(judge, {}):
                    r["derived"][judge]["handoff"] = True
                if COVERAGE in r["labels"].get(judge, {}):
                    r["labels"][judge][COVERAGE] = {**r["labels"][judge][COVERAGE], "label": "incomplete"}
    h1_w, h4_w = h1_handoff(worst, arm), h4_screen(worst, arm, h2)
    return {"flagged": len(flagged), "h1_verdict": h1_w["verdict"], "h4_verdict": h4_w["verdict"],
            "unchanged": h1_w["verdict"] == h1["verdict"] and h4_w["verdict"] == h4["verdict"]}


# --- descriptive set -----------------------------------------------------------------

def descriptive(rows: list[dict]) -> dict:
    arms = sorted({r["variant"] for r in rows})
    chronology = sorted(({"started_utc": r["started_utc"], "run": r.get("run"), "variant": r["variant"], "probe": r["probe"],
                          "repetition": r["repetition"], "words": r["words"]} for r in rows),
                        key=lambda x: (x["started_utc"] or "", x["variant"], x["probe"]))
    for index, item in enumerate(chronology):
        item["dispatch_index"] = index
    crosstabs = {}
    for arm in arms:
        sub = arm_rows(rows, arm)
        entry = {"words_by_oracle": {"pass": mean(r["words"] for r in sub if r["oracle_pass"]),
                                     "fail": mean(r["words"] for r in sub if not r["oracle_pass"])},
                 "words_by_echo": {"flagged": mean(r["words"] for r in sub if r["echo"]),
                                   "clean": mean(r["words"] for r in sub if not r["echo"])}}
        for judge in JUDGES:
            entry[f"words_by_coverage_{judge}"] = {
                lab: mean(r["words"] for r in sub if r["labels"].get(judge, {}).get(COVERAGE, {}).get("label") == lab)
                for lab in ("complete", "incomplete")}
            entry[f"words_by_closing_{judge}"] = {
                lab: mean(r["words"] for r in sub if r["labels"].get(judge, {}).get(CLOSING, {}).get("label") == lab)
                for lab in CLOSING_LABELS}
        crosstabs[arm] = entry
    ratios = {}
    base_all = [r["words"] for r in arm_rows(rows, BASELINE)]
    for arm in arms:
        if arm == BASELINE:
            continue
        sub = [r["words"] for r in arm_rows(rows, arm)]
        ratios[arm] = {"median_ratio_all": round(median(sub) / median(base_all), 4) if base_all and sub and median(base_all) else None,
                       "mean_difference_all": round(statistics.fmean(sub) - statistics.fmean(base_all), 2) if base_all and sub else None}
    return {"chronology": chronology, "crosstabs": crosstabs, "ratios_all_rows": ratios}


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

def analyze(run_dir: Path, judge_root: Path, declaration: Path | None = None,
            controls: tuple[Path, Path] | None = None) -> dict:
    runs = [(run_dir, judge_root)] + ([controls] if controls else [])
    rows, coverage, run_records, prompts, censor, planned = [], {}, [], {}, {}, defaultdict(int)
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
                            "dispatch_seed": plan.get("dispatch_seed"),
                            "summary_sha256": (loaded["verified"] or {}).get("summary_sha256"),
                            "partial": loaded["partial"], "rows": len(run_rows), "execution": plan["execution"]})
        prompts.update({c["probe_id"]: c["prompt"] for c in plan["cases"]})
        for case in plan["cases"]:
            planned[case["variant_id"]] += 1
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
    head = run_records[0]
    result = {
        "campaign_id": head["campaign_id"], "plan_sha256": head["plan_sha256"], "runs": [
            {k: v for k, v in r.items() if k != "execution"} for r in run_records],
        "partial": any(r["partial"] for r in run_records),
        "closing_scan_sha256": CLOSING_SCAN_SHA256, "rows_recorded": len(rows),
        "censoring": censor, "judge_coverage": coverage, "echo": echo, "arms": arms,
        "judge_agreement": judge_agreement(rows), "execution": head["execution"], "rows": rows,
    }
    hypotheses = {}
    for arm in SCREENED:
        if not arm_rows(rows, arm):
            continue
        h1 = h1_handoff(rows, arm)
        h2 = h2_length(rows, arm)
        h4 = h4_screen(rows, arm, h2)
        complete = completeness(rows, arm, planned, censor, both_runs=controls is not None)
        sensitivity = echo_sensitivity(rows, arm, h1, h4, h2)
        entry = {"role": "replication" if arm == REPLICATION else "treatment",
                 "partial": any(r["partial"] for r in run_records) or not complete["complete"],
                 "H1_handoff": h1, "H2_length": h2, "H4_screen": h4, "completeness": complete,
                 "echo_sensitivity": sensitivity,
                 "eligible": (h1["verdict"] == "supported" and h2["verdict"] != "longer" and h2["non_inferior"]
                              and h4["verdict"] == "screen passed" and complete["complete"] and sensitivity["unchanged"]),
                 "echo_flagged_trials": len(echo["flagged_trials"].get(arm, []))}
        if arm == REPLICATION:
            entry["H3_replication"] = h3_replication(rows, h1, h2, complete["complete"])
        hypotheses[arm] = entry
    result["hypotheses"] = hypotheses
    result["descriptive"] = descriptive(rows)
    result["arms_roles"] = {"baseline": BASELINE, "replication": REPLICATION, "treatments": list(TREATMENTS),
                            "primary_tasks": list(PRIMARY_TASKS), "control_tasks": list(CONTROL_TASKS)}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--judge-root", required=True, type=Path)
    parser.add_argument("--declaration", type=Path, help="declaration naming the variants (default: ../../campaign-primary.toml)")
    parser.add_argument("--controls", nargs=2, type=Path, metavar=("RUN_DIR", "JUDGE_ROOT"),
                        help="the controls run and its judge root, read together with the primary run")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = analyze(args.run_dir, args.judge_root, args.declaration, tuple(args.controls) if args.controls else None)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text)
    headline = {k: v for k, v in result.items() if k not in {"rows", "arms", "execution", "descriptive"}}
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
