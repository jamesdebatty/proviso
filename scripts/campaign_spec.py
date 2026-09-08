#!/usr/bin/env python3
"""Declared campaign arms, pins, battery and reductions — one generic analyzer.

A campaign declaration (`campaign-declaration/1`, TOML) states which arms ran,
at which pins, over which battery, and which reductions, comparisons and gates
the protocol committed to. This module reads a result set, checks it against the
declaration, applies the declared reductions, and emits the summary.

Nothing here is campaign-specific: the campaign lives in the declaration, which
a reader can check against the preregistration without reading this file.

Two record sources are supported:

  bakeoff-out/1   an archived promptfoo-era result directory: `responses/<key>/`
                  with `meta.json` + `response.json`, and `judgments/*.json`.
  capture-spine/1 a T-002 manifest; one record per trial.

What it deliberately does not express is listed in
`sources/2026-08-25-t006-campaign-harness.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score_eval import metrics  # noqa: E402

SCHEMA = "campaign-declaration/1"
RECORD_KINDS = ("response", "judgment", "trial")
STATISTICS = ("mean", "median", "sum", "count", "tally", "share")
COMPARISON_KINDS = ("delta", "pct_change")
OPERATORS = {"<=": lambda a, b: a <= b, "<": lambda a, b: a < b,
             ">=": lambda a, b: a >= b, ">": lambda a, b: a > b}

# --- Response scans -----------------------------------------------------
#
# Text scans a declaration may name in `[records] scans`. Each takes the answer
# text and its prompt and returns one number or label per response. They are
# campaign-agnostic by construction; which of them a campaign uses, and what it
# does with the result, is declared, not coded.

NUMERAL_RE = re.compile(r"\d[\d,.]*")
QUOTED_RE = re.compile(r'"([^"\n]{3,60})"|“([^”\n]{3,60})”')
HYPHEN_COMPOUND_RE = re.compile(r"\b[a-z]{3,}(?:-[a-z]{3,}){1,3}\b")
TITLE_PHRASE_RE = re.compile(
    r"(?<![.!?]\s)(?<!^)\b(?:[A-Z][a-z]{2,}\s){1,3}[A-Z][a-z]{2,}\b", re.M)
TOOL_TRANSCRIPT_RE = re.compile(
    r"(?m)<invoke name=|<parameter name=|^\*\*Tool: |^total \d+\s*$|\bdrwx")
INSPECT_RE = re.compile(
    r"(?i)\b(let me|i(?:'|’)ll|i will|i am going to|i need to|going to)\b"
    r"[^.!?\n]{0,80}\b(inspect|look at|examine|explore|read|open|list|review)\b"
    r"[^.!?\n]{0,80}\b(project|file|files|codebase|repo|repository|director(?:y|ies))\b")
MIN_ANSWER_WORDS = 40


def scan_words(text: str, prompt: str) -> int:
    return metrics(text)["words"]


def scan_novel_numerals(text: str, prompt: str) -> int:
    """Numeric tokens in the answer that never appear in the prompt."""
    given = set(NUMERAL_RE.findall(prompt))
    return sum(1 for token in NUMERAL_RE.findall(text) if token not in given)


def scan_novel_coinages(text: str, prompt: str) -> int:
    """Distinct reused coined-looking terms absent from the prompt.

    A coined handle is reused by construction, so a candidate counts only if it
    appears at least twice. Deliberately over-inclusive; applied identically to
    every arm, so it measures relative coinage load.
    """
    given = prompt.lower()
    lowered = text.lower()
    candidates = set()
    for match in QUOTED_RE.finditer(text):
        term = (match.group(1) or match.group(2) or "").strip().lower()
        if len(term.split()) >= 2:
            candidates.add(term)
    for pattern in (HYPHEN_COMPOUND_RE, TITLE_PHRASE_RE):
        for match in pattern.finditer(text):
            candidates.add(match.group(0).strip().lower())
    return sum(1 for term in candidates
               if term and term not in given and lowered.count(term) >= 2)


def scan_preflight_v2(text: str, prompt: str) -> str:
    """Frozen v2 admission rule: `answered` or `stalled`."""
    if len(re.findall(r"[A-Za-z0-9']+", text)) < MIN_ANSWER_WORDS:
        return "stalled"
    if TOOL_TRANSCRIPT_RE.search(text):
        return "stalled"
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if paragraphs and INSPECT_RE.search(paragraphs[-1]):
        return "stalled"
    return "answered"


SCANS = {"words": scan_words, "novel_numerals": scan_novel_numerals,
         "novel_coinages": scan_novel_coinages, "preflight": scan_preflight_v2}

# --- Declaration --------------------------------------------------------


def parse(path: Path) -> dict:
    """Read a declaration without validating it."""
    spec = tomllib.loads(Path(path).read_text())
    spec["_path"] = str(Path(path).resolve())
    return spec


def load(path: Path) -> dict:
    """Read a declaration and raise on any structural problem."""
    spec = parse(path)
    problems = validate(spec)
    if problems:
        raise ValueError("; ".join(problems))
    return spec


def validate(spec: dict) -> list[str]:
    problems = []
    if spec.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA!r}")
    campaign = spec.get("campaign") or {}
    arms = spec.get("arms") or []
    arm_ids = [arm.get("id") for arm in arms]
    if not arms or len(set(arm_ids)) != len(arm_ids):
        problems.append("arms must be non-empty with unique ids")
    if campaign.get("baseline_arm") not in arm_ids:
        problems.append("campaign.baseline_arm must name a declared arm")
    if (spec.get("records") or {}).get("source") not in READERS:
        problems.append(f"records.source must be one of {sorted(READERS)}")
    for name in (spec.get("records") or {}).get("scans", []):
        if name not in SCANS:
            problems.append(f"unknown scan {name!r}")
    names = set()
    for item in spec.get("reductions", []):
        name = item.get("name")
        if not name or name in names:
            problems.append(f"reduction name missing or duplicated: {name!r}")
        names.add(name)
        if item.get("over") not in RECORD_KINDS:
            problems.append(f"{name}: over must be one of {RECORD_KINDS}")
        if item.get("statistic") not in STATISTICS:
            problems.append(f"{name}: statistic must be one of {STATISTICS}")
        if item.get("statistic") != "count" and not item.get("field"):
            problems.append(f"{name}: field is required")
        if "arm" not in (item.get("group_by") or []):
            problems.append(f"{name}: group_by must include 'arm'")
        if item.get("statistic") == "share" and not (item.get("value") and item.get("among")):
            problems.append(f"{name}: share needs value and among")
    for item in spec.get("comparisons", []):
        if item.get("reduction") not in names:
            problems.append(f"{item.get('name')!r}: unknown reduction")
        if item.get("kind") not in COMPARISON_KINDS:
            problems.append(f"{item.get('name')!r}: kind must be one of {COMPARISON_KINDS}")
    comparison_names = {item.get("name") for item in spec.get("comparisons", [])}
    for item in spec.get("gates", []):
        target = item.get("reduction") or item.get("comparison")
        if target not in names | comparison_names:
            problems.append(f"gate {item.get('name')!r}: unknown reduction or comparison")
        if item.get("op") not in OPERATORS:
            problems.append(f"gate {item.get('name')!r}: op must be one of {sorted(OPERATORS)}")
        if ("vs" in item) == ("value" in item):
            problems.append(f"gate {item.get('name')!r}: needs exactly one of vs, value")
    return problems


# --- Record readers -----------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_bakeoff_out(spec: dict, root: Path) -> list[dict]:
    """Records from an archived `out/<run>/` directory.

    The declaration is load-bearing here, not decorative: an undeclared arm, a
    binary version other than the declared pin, or a clause whose hash is not
    the one the arm declares, raises rather than being summarized.
    """
    base = Path(spec["_path"]).parent
    arms = {arm["id"]: arm for arm in spec["arms"]}
    pinned_version = (spec.get("pins") or {}).get("generator_binary_version")
    scans = (spec.get("records") or {}).get("scans", [])
    battery = spec.get("battery") or {}
    prompts = {}
    for line in (base / battery["tasks_file"]).read_text().splitlines():
        task = json.loads(line)
        prompts[task["id"]] = task["prompt"]
    records = []
    for directory in sorted((root / "responses").iterdir()):
        meta_path = directory / "meta.json"
        payload_path = directory / "response.json"
        if not (meta_path.is_file() and payload_path.is_file()):
            continue
        meta = json.loads(meta_path.read_text())
        arm = arms.get(meta["arm"])
        if arm is None:
            raise ValueError(f"undeclared arm in results: {meta['arm']!r}")
        if pinned_version and meta.get("claude_version") != pinned_version:
            raise ValueError(f"{directory.name}: binary is not the declared pin")
        if meta.get("clause_sha256") != (arm.get("sha256") or None):
            raise ValueError(f"{directory.name}: clause hash is not the arm's declared hash")
        if meta.get("response_sha256") != _sha256_file(payload_path):
            raise ValueError(f"{directory.name}: response artifact hash mismatch")
        text = json.loads(payload_path.read_text())["result"]
        prompt = prompts[meta["task_id"]]
        record = {"record": "response", "arm": meta["arm"], "task_id": meta["task_id"],
                  "repetition": meta["repetition"]}
        for name in scans:
            record[name] = SCANS[name](text, prompt)
        records.append(record)
    expected = len(arms) * len(prompts) * battery["repetitions"]
    if len(records) != expected:
        raise ValueError(f"expected {expected} responses, read {len(records)}")
    baseline = spec["campaign"]["baseline_arm"]
    for path in sorted((root / "judgments").glob("*.json")):
        item = json.loads(path.read_text())
        labels = item["labels"]
        inverse = {arm_id: label for label, arm_id in labels.items()}
        for label, arm_id in labels.items():
            score = item["judgment"]["answers"][label]
            record = {"record": "judgment", "judge": item["judge"], "arm": arm_id,
                      "task_id": item["task_id"], "repetition": item["repetition"],
                      "pairwise_vs_baseline": None}
            for key, value in score.items():
                record[key] = len(value) if isinstance(value, list) else value
            if arm_id != baseline:
                left, right = sorted((inverse[arm_id], inverse[baseline]))
                winner = item["judgment"]["pairwise"][f"{left}_vs_{right}"]
                record["pairwise_vs_baseline"] = (
                    "tie" if winner == "tie"
                    else "candidate" if winner == inverse[arm_id] else "baseline")
            records.append(record)
    return records


def read_capture_spine(spec: dict, root: Path) -> list[dict]:
    """One record per trial of a T-002 `capture-spine/1` manifest."""
    manifest = json.loads(Path(root).read_text())
    if manifest.get("schema") != "capture-spine/1":
        raise ValueError(f"not a capture-spine/1 manifest: {manifest.get('schema')!r}")
    arms = {arm["id"]: arm for arm in spec["arms"]}
    records = []
    for trial in manifest["trials"]:
        arm = arms.get(trial["arm"])
        if arm is None:
            raise ValueError(f"undeclared arm in manifest: {trial['arm']!r}")
        strata = arm.get("strata")
        if strata is not None and trial["stratum"] not in strata:
            raise ValueError(
                f"{trial['trial_id']}: arm {trial['arm']!r} is not declared over "
                f"stratum {trial['stratum']!r}")
        record = {"record": "trial", "arm": trial["arm"], "trial_id": trial["trial_id"],
                  "fixture_id": trial["fixture_id"], "stratum": trial["stratum"],
                  "surface_verdict": trial["surface_verdict"],
                  "distinct_surfaces": trial["distinct_surfaces"]}
        record.update(trial.get("usage_totals") or {})
        records.append(record)
    return records


READERS = {"bakeoff-out/1": read_bakeoff_out, "capture-spine/1": read_capture_spine}

# --- Reductions, comparisons, gates -------------------------------------


def _apply(item: dict, records: list[dict]) -> dict[tuple, object]:
    group_by = item["group_by"]
    where = item.get("where") or {}
    field = item.get("field")
    statistic = item["statistic"]
    # Every group present in the record set gets an entry, so a `where` that
    # selects nothing reports 0 rather than vanishing from the summary.
    groups: dict[tuple, list] = defaultdict(list)
    for record in records:
        if record["record"] != item["over"]:
            continue
        key = tuple(record.get(name) for name in group_by)
        groups.setdefault(key, [])
        if any(record.get(name) != value for name, value in where.items()):
            continue
        value = record.get(field) if field else True
        if value is not None:
            groups[key].append(value)
    digits = item.get("round")
    out = {}
    for key, values in groups.items():
        if statistic == "count":
            result = len(values)
        elif statistic == "sum":
            result = sum(values)
        elif statistic == "mean":
            result = statistics.mean(values) if values else None
        elif statistic == "median":
            result = statistics.median(values) if values else None
        elif statistic == "tally":
            result = {label: values.count(label) for label in sorted(set(values))}
        else:  # share
            denominator = sum(1 for value in values if value in item["among"])
            result = values.count(item["value"]) / denominator if denominator else None
        if digits is not None and isinstance(result, float):
            result = round(result, digits)
        out[key] = result
    return out


def _baseline_key(key: tuple, group_by: list, baseline: str) -> tuple:
    return tuple(baseline if name == "arm" else value
                 for name, value in zip(group_by, key, strict=True))


def analyze(spec: dict, results: Path) -> dict:
    """Read a result set and compute every declared reduction, comparison and gate."""
    records = READERS[spec["records"]["source"]](spec, Path(results))
    baseline = spec["campaign"]["baseline_arm"]
    reductions = {item["name"]: (item, _apply(item, records))
                  for item in spec.get("reductions", [])}
    comparisons = {}
    for item in spec.get("comparisons", []):
        source, values = reductions[item["reduction"]]
        group_by = source["group_by"]
        computed = {}
        for key, value in values.items():
            reference = values.get(_baseline_key(key, group_by, baseline))
            if key == _baseline_key(key, group_by, baseline) or reference is None:
                continue
            if item["kind"] == "pct_change" and reference == 0:
                continue
            delta = value - reference
            result = delta if item["kind"] == "delta" else 100 * delta / reference
            digits = item.get("round")
            computed[key] = round(result, digits) if digits is not None else result
        comparisons[item["name"]] = (source, computed)
    gates = {arm["id"]: {} for arm in spec["arms"] if arm["id"] != baseline}
    for item in spec.get("gates", []):
        target = item.get("reduction") or item.get("comparison")
        source, values = reductions.get(target) or comparisons[target]
        group_by = source["group_by"]
        for arm in gates:
            checks = []
            for key, value in values.items():
                if key[group_by.index("arm")] != arm:
                    continue
                if "value" in item:
                    threshold = item["value"]
                else:
                    threshold = values.get(_baseline_key(key, group_by, baseline))
                    if threshold is None:
                        checks.append(False)
                        continue
                    threshold *= item.get("factor", 1)
                checks.append(value is not None and OPERATORS[item["op"]](value, threshold))
            gates[arm][item["name"]] = bool(checks) and all(checks)
    return {
        "schema": SCHEMA,
        "campaign": spec["campaign"]["id"],
        "baseline_arm": baseline,
        "arms": [arm["id"] for arm in spec["arms"]],
        "records": {kind: sum(1 for record in records if record["record"] == kind)
                    for kind in RECORD_KINDS
                    if any(record["record"] == kind for record in records)},
        "reductions": {name: _serialize(values) for name, (_, values) in reductions.items()},
        "comparisons": {name: _serialize(values) for name, (_, values) in comparisons.items()},
        "gates": gates,
        # An arm with no declared gates has no verdict to report: `all({})` is
        # True, so it is omitted rather than reported as having passed.
        "eligible": {arm: all(checks.values())
                     for arm, checks in gates.items() if checks},
    }


def _serialize(values: dict[tuple, object]) -> dict:
    return {"/".join(str(part) for part in key): value for key, value in values.items()}


# --- CLI ----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("check", "analyze"))
    parser.add_argument("declaration", type=Path)
    parser.add_argument("--results", type=Path,
                        help="result directory or manifest; required by analyze")
    args = parser.parse_args(argv)
    spec = parse(args.declaration)
    problems = validate(spec)
    if problems:
        for problem in problems:
            print(f"problem: {problem}")
        return 1
    if args.command == "check":
        print(f"{spec['campaign']['id']}: {len(spec['arms'])} arms, "
              f"{len(spec.get('reductions', []))} reductions, "
              f"{len(spec.get('gates', []))} gates, 0 problems")
        return 0
    if args.results is None:
        parser.error("analyze requires --results")
    print(json.dumps(analyze(spec, args.results), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
