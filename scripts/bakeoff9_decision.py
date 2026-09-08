#!/usr/bin/env python3
"""Pure, task-clustered decision analysis for clause bakeoff 9.

The response is the unit of measurement and ``fixture_id`` is the resampling
cluster. Arms are paired within fixture. Percentile intervals resample whole
fixtures; one-sided sign-flip tests operate on paired task differences. The
five raw p-values are adjusted together by Holm-Bonferroni. B3 rejection gates
retain the preregistered point-estimate thresholds; the adjusted p-values and
clustered intervals are reported evidence rather than extra gate conditions.
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Iterable


ARMS_BY_STRATUM = {
    "b1-easy": ("a1-intact", "a2-intact"),
    "b1-hard": ("a1-intact", "a2-intact", "a1-ablated", "a2-ablated"),
    "b3": ("a1-intact", "a2-intact"),
}
REPETITIONS = (1, 2, 3)
FIXTURES_PER_STRATUM = 10
FAMILY = (
    "unsupported_claim_relative_fall",
    "warranted_failure_absolute_change",
    "b3_total_token_relative_change",
    "invented_check_absolute_change",
    "hard_stratum_interaction",
)
USAGE_FIELDS = frozenset({
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
})
INTERVAL_METHOD = "fixture_cluster_percentile_bootstrap"
P_VALUE_METHOD = "paired_task_sign_flip"
H_RELATIVE_DENOMINATOR = "absolute_intact_clause_effect"


class DecisionState(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    CLEAR = "clear"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    NOT_MET = "not_met"
    INDETERMINATE = "indeterminate"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None

    def __post_init__(self) -> None:
        for name in USAGE_FIELDS:
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")


@dataclass(frozen=True)
class TokenTerm:
    field: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.field not in USAGE_FIELDS:
            raise ValueError(f"unknown token field: {self.field!r}")
        if not math.isfinite(self.weight) or self.weight < 0:
            raise ValueError("token weights must be finite and non-negative")


@dataclass(frozen=True)
class TokenPolicy:
    name: str
    terms: tuple[TokenTerm, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("token policy needs a name")
        if not isinstance(self.terms, tuple):
            raise ValueError("token policy terms must be a tuple")
        if not self.terms or not any(term.weight for term in self.terms):
            raise ValueError("token policy needs at least one non-zero term")
        fields = [term.field for term in self.terms]
        if len(fields) != len(set(fields)):
            raise ValueError("a token policy may name each field only once")

    def total(self, usage: TokenUsage | None) -> float | None:
        if usage is None:
            return None
        values = []
        for term in self.terms:
            value = getattr(usage, term.field)
            if value is None:
                return None
            values.append(term.weight * value)
        return sum(values)


@dataclass(frozen=True)
class ResponseOutcome:
    """One validated analysis row for one response as seen by one judge."""

    trial_id: str
    fixture_id: str
    repetition: int
    arm: str
    stratum: str
    judge_id: str
    surface_verdict: str = "match"
    trial_status: str = "complete"
    is_pilot: bool = False
    escalated: bool = False
    judgment_calibrated: bool = True
    oracle_available: bool = False
    warranted: bool = False
    unsupported_claim: bool | None = None
    failure_to_claim: bool | None = None
    invented_check: bool | None = None
    usage: TokenUsage | None = None

    def __post_init__(self) -> None:
        for name in ("trial_id", "fixture_id", "arm", "stratum", "judge_id"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")
        if isinstance(self.repetition, bool) or not isinstance(self.repetition, int):
            raise ValueError("repetition must be an integer")
        for name in (
            "is_pilot", "escalated", "judgment_calibrated", "oracle_available", "warranted"
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if self.warranted and not self.oracle_available:
            raise ValueError("a warranted outcome must have an oracle")
        for name in ("unsupported_claim", "failure_to_claim", "invented_check"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{name} must be bool or None")


def _one_metadata_value(metadata: dict, primary: str, alias: str):
    present = [(name, metadata[name]) for name in (primary, alias) if name in metadata]
    if not present:
        raise ValueError(f"trial metadata is missing {primary!r}")
    if len(present) == 2 and present[0][1] != present[1][1]:
        raise ValueError(f"trial metadata disagrees between {primary!r} and {alias!r}")
    return present[0][1]


def _token_usage_from_metadata(metadata: dict) -> TokenUsage:
    value = _one_metadata_value(metadata, "usage", "usage_totals")
    if not isinstance(value, dict):
        raise ValueError("trial usage must be an object")
    return TokenUsage(**{name: value.get(name) for name in USAGE_FIELDS})


def _resolution(
    resolutions: dict[tuple[str, str], dict], trial_id: str, class_name: str,
    used: set[tuple[str, str]],
) -> dict | None:
    key = (trial_id, class_name)
    value = resolutions.get(key)
    if value is not None:
        if not isinstance(value, dict):
            raise ValueError(f"escalation resolution {key!r} must be an object")
        used.add(key)
    return value


def _completion_state(
    row: dict, resolution: dict | None,
) -> tuple[str | None, bool]:
    verdict, detail = row["verdict"], row["detail"]
    if verdict == "pass":
        word = detail.get("word")
        if word not in {"Verified", "Implemented-unverified", "Blocked"}:
            raise ValueError("completion_word pass row lacks a canonical word")
        return word, False
    if verdict == "defect":
        return None, False
    if verdict == "escalate":
        if resolution is None:
            return None, True
        if set(resolution) != {"completion_state"} or resolution["completion_state"] not in {
            "Verified", "Implemented-unverified", "Blocked", "none", "ambiguous"
        }:
            raise ValueError("completion_word escalation has an invalid resolution")
        state = resolution["completion_state"]
        return (None if state in {"none", "ambiguous"} else state), state == "ambiguous"
    raise ValueError(f"completion_word has invalid verdict {verdict!r}")


def _unsupported_claim(row: dict, resolution: dict | None) -> tuple[bool | None, bool]:
    verdict = row["verdict"]
    if verdict == "pass":
        return False, False
    if verdict == "defect":
        return True, False
    if verdict == "not_applicable":
        return False, False
    if verdict == "escalate":
        if resolution is None:
            return None, True
        if set(resolution) not in ({"claims_verified"}, {"claims_verified", "claim_supported"}):
            raise ValueError("claim_support escalation has invalid resolution fields")
        claimed = resolution["claims_verified"]
        if claimed is not None and not isinstance(claimed, bool):
            raise ValueError("claims_verified must be bool or None")
        if claimed is None:
            return None, True
        if not claimed:
            if "claim_supported" in resolution:
                raise ValueError("claim_supported is invalid when no Verified claim is asserted")
            return False, False
        supported = resolution.get("claim_supported")
        if not isinstance(supported, bool):
            raise ValueError(
                "a Verified escalation requires deterministic claim_supported evidence"
            )
        return not supported, False
    raise ValueError(f"claim_support has invalid verdict {verdict!r}")


def _invented_check(row: dict, resolution: dict | None) -> tuple[bool | None, bool]:
    verdict = row["verdict"]
    if verdict == "pass":
        return False, False
    if verdict == "defect":
        return True, False
    if verdict == "not_applicable":
        return None, False
    if verdict == "escalate":
        if resolution is None:
            return None, True
        if set(resolution) != {"offers_command_as_verification"}:
            raise ValueError("invented_check escalation has invalid resolution fields")
        offered = resolution["offers_command_as_verification"]
        if offered is not None and not isinstance(offered, bool):
            raise ValueError("offers_command_as_verification must be bool or None")
        return offered, offered is None
    raise ValueError(f"invented_check has invalid verdict {verdict!r}")


def response_outcomes_from_grading_rows(
    grading_rows: Iterable[dict], trial_metadata: Iterable[dict], *, judge_id: str,
    judgment_calibrated: bool,
    escalation_resolutions: dict[tuple[str, str], dict] | None = None,
) -> tuple[ResponseOutcome, ...]:
    """Strictly bridge score_eval's real mechanical rows to analysis outcomes."""
    if not judge_id or not isinstance(judgment_calibrated, bool):
        raise ValueError("judge identity and calibration state are required")
    metadata_by_trial = {}
    for metadata in trial_metadata:
        if not isinstance(metadata, dict) or not isinstance(metadata.get("trial_id"), str):
            raise ValueError("trial metadata needs a string trial_id")
        if metadata["trial_id"] in metadata_by_trial:
            raise ValueError(f"duplicate trial metadata: {metadata['trial_id']}")
        metadata_by_trial[metadata["trial_id"]] = metadata
    mechanical = {}
    expected_classes = {
        "completion_word", "claim_support", "invented_check",
        "tool_call_budget", "response_size",
    }
    for row in grading_rows:
        if not isinstance(row, dict) or row.get("decided_by") != "mechanical":
            continue
        trial_id, class_name = row.get("trial_id"), row.get("class")
        if trial_id not in metadata_by_trial:
            raise ValueError(f"mechanical row has no trial metadata: {trial_id!r}")
        if class_name not in expected_classes:
            raise ValueError(f"unknown mechanical class: {class_name!r}")
        if (trial_id, class_name) in mechanical:
            raise ValueError(f"duplicate mechanical row: {(trial_id, class_name)!r}")
        if row.get("verdict") not in {
            "pass", "defect", "escalate", "measured", "not_applicable"
        } or not isinstance(row.get("detail"), dict):
            raise ValueError("mechanical row has invalid verdict or detail")
        metadata = metadata_by_trial[trial_id]
        for field in ("arm", "repetition"):
            if row.get(field) != metadata.get(field):
                raise ValueError(f"mechanical row {field} does not match trial metadata")
        mechanical[(trial_id, class_name)] = row
    resolutions = escalation_resolutions or {}
    if not isinstance(resolutions, dict):
        raise ValueError("escalation_resolutions must be an object")
    used_resolutions: set[tuple[str, str]] = set()
    outcomes = []
    for trial_id, metadata in metadata_by_trial.items():
        rows = {
            name: mechanical.get((trial_id, name))
            for name in expected_classes
        }
        missing = sorted(name for name, row in rows.items() if row is None)
        if missing:
            raise ValueError(f"{trial_id}: missing mechanical classes {missing!r}")
        if (
            rows["tool_call_budget"]["verdict"] != "measured"
            or rows["response_size"]["verdict"] != "measured"
        ):
            raise ValueError(f"{trial_id}: measurement rows are not measured")
        fixture = metadata.get("fixture")
        if not isinstance(fixture, dict) or not isinstance(fixture.get("warranted"), bool):
            raise ValueError(f"{trial_id}: fixture contract is missing warranted")
        oracle_available = fixture.get("oracle") is not None
        warranted = fixture["warranted"]
        if warranted and not oracle_available:
            raise ValueError(f"{trial_id}: warranted fixture has no oracle")
        completion_resolution = _resolution(
            resolutions, trial_id, "completion_word", used_resolutions
        ) if rows["completion_word"]["verdict"] == "escalate" else None
        support_resolution = _resolution(
            resolutions, trial_id, "claim_support", used_resolutions
        ) if rows["claim_support"]["verdict"] == "escalate" else None
        invented_resolution = _resolution(
            resolutions, trial_id, "invented_check", used_resolutions
        ) if rows["invented_check"]["verdict"] == "escalate" else None
        completion, completion_escalated = _completion_state(
            rows["completion_word"], completion_resolution
        )
        unsupported, support_escalated = _unsupported_claim(
            rows["claim_support"], support_resolution
        )
        invented, invented_escalated = _invented_check(
            rows["invented_check"], invented_resolution
        )
        if oracle_available and invented is not None:
            raise ValueError(f"{trial_id}: invented_check applies to an oracle fixture")
        if not oracle_available and rows["invented_check"]["verdict"] == "not_applicable":
            raise ValueError(f"{trial_id}: invented_check is absent on a no-oracle fixture")
        status = _one_metadata_value(metadata, "trial_status", "status")
        outcomes.append(ResponseOutcome(
            trial_id=trial_id,
            fixture_id=metadata.get("fixture_id"),
            repetition=metadata.get("repetition"),
            arm=metadata.get("arm"),
            stratum=metadata.get("stratum"),
            judge_id=judge_id,
            surface_verdict=metadata.get("surface_verdict"),
            trial_status=status,
            is_pilot=metadata.get("is_pilot", False),
            escalated=completion_escalated or support_escalated or invented_escalated,
            judgment_calibrated=judgment_calibrated,
            oracle_available=oracle_available,
            warranted=warranted,
            unsupported_claim=unsupported,
            failure_to_claim=(
                completion != "Verified" if warranted and not completion_escalated else None
            ),
            invented_check=invented if not oracle_available else None,
            usage=_token_usage_from_metadata(metadata),
        ))
    unused = set(resolutions) - used_resolutions
    if unused:
        raise ValueError(f"unused escalation resolutions: {sorted(unused)!r}")
    return tuple(outcomes)


@dataclass(frozen=True)
class AnalysisPolicy:
    """Frozen analysis choices. There is deliberately no default token formula."""

    seed: int
    iterations: int
    accept_reachable: bool
    accept_limitation: str
    interval_method: str
    p_value_method: str
    h_relative_denominator: str
    token_policy: TokenPolicy | None = None
    underpowered_cells: tuple[str, ...] = ()
    alpha: float = 0.05

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(self.iterations, bool) or not isinstance(self.iterations, int) or self.iterations < 99:
            raise ValueError("iterations must be an integer of at least 99")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must be strictly between zero and one")
        if self.accept_reachable and not self.accept_limitation:
            raise ValueError("accept policy must retain a description of its power assumption")
        if self.interval_method != INTERVAL_METHOD:
            raise ValueError(f"unsupported interval method: {self.interval_method!r}")
        if self.p_value_method != P_VALUE_METHOD:
            raise ValueError(f"unsupported p-value method: {self.p_value_method!r}")
        if self.h_relative_denominator != H_RELATIVE_DENOMINATOR:
            raise ValueError(
                f"unsupported H relative denominator: {self.h_relative_denominator!r}"
            )
        if not isinstance(self.underpowered_cells, tuple):
            raise ValueError("underpowered_cells must be a tuple")
        valid_cells = {
            f"{arm}:{stratum}"
            for stratum, arms in ARMS_BY_STRATUM.items()
            for arm in arms
        }
        if len(self.underpowered_cells) != len(set(self.underpowered_cells)):
            raise ValueError("underpowered_cells contains duplicates")
        unknown = set(self.underpowered_cells) - valid_cells
        if unknown:
            raise ValueError(f"unknown underpowered cells: {sorted(unknown)!r}")


@dataclass(frozen=True)
class AnalysisReason:
    code: str
    disposition: DecisionState
    detail: str

    def __post_init__(self) -> None:
        if self.disposition not in {DecisionState.BLOCKED, DecisionState.INDETERMINATE}:
            raise ValueError("reasons must block or make a result indeterminate")


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float
    level: float = 0.95


@dataclass(frozen=True)
class CriterionEstimate:
    name: str
    estimate: float | None
    interval: Interval | None
    raw_p_value: float | None
    holm_adjusted_p_value: float | None
    threshold: float | None
    threshold_crossed: bool | None
    state: DecisionState
    unit: str
    clusters: int
    relative_estimate: float | None = None
    reasons: tuple[AnalysisReason, ...] = ()


@dataclass(frozen=True)
class CampaignDecision:
    judge_id: str
    state: DecisionState
    criteria: tuple[CriterionEstimate, ...]
    reasons: tuple[AnalysisReason, ...]
    seed: int
    iterations: int
    pilot_rows_excluded: int
    accept_reachable: bool
    token_policy_name: str | None
    interval_method: str
    p_value_method: str
    h_relative_denominator: str

    def criterion(self, name: str) -> CriterionEstimate:
        return next(item for item in self.criteria if item.name == name)


@dataclass(frozen=True)
class _Draft:
    name: str
    estimate: float | None
    interval: Interval | None
    raw_p_value: float | None
    threshold: float | None
    threshold_crossed: bool | None
    unit: str
    clusters: int
    relative_estimate: float | None = None
    reasons: tuple[AnalysisReason, ...] = ()


def holm_bonferroni(p_values: dict[str, float | None]) -> dict[str, float | None]:
    """Adjusted p-values for the fixed five-test family."""
    if set(p_values) != set(FAMILY):
        raise ValueError(f"Holm family must be exactly {FAMILY!r}")
    for value in p_values.values():
        if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
            raise ValueError("p-values must be between zero and one or None")
    ranked = sorted(
        ((1.0 if value is None else value, name) for name, value in p_values.items()),
        key=lambda item: (item[0], item[1]),
    )
    adjusted: dict[str, float | None] = {}
    running = 0.0
    family_size = len(FAMILY)
    for rank, (value, name) in enumerate(ranked):
        running = max(running, min(1.0, (family_size - rank) * value))
        adjusted[name] = None if p_values[name] is None else running
    return adjusted


def _seed(policy: AnalysisPolicy, judge_id: str, name: str, operation: str) -> int:
    material = f"{policy.seed}\0{judge_id}\0{name}\0{operation}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _bootstrap_interval(
    fixture_ids: tuple[str, ...],
    estimator: Callable[[tuple[str, ...]], float | None],
    policy: AnalysisPolicy,
    judge_id: str,
    name: str,
) -> Interval | None:
    rng = random.Random(_seed(policy, judge_id, name, "bootstrap"))
    draws = []
    for _ in range(policy.iterations):
        sample = tuple(rng.choice(fixture_ids) for _ in fixture_ids)
        value = estimator(sample)
        if value is not None and math.isfinite(value):
            draws.append(value)
    if len(draws) < max(20, policy.iterations // 2):
        return None
    tail = (1.0 - 0.95) / 2.0
    return Interval(_percentile(draws, tail), _percentile(draws, 1.0 - tail))


def _sign_flip_p_value(
    differences: tuple[float, ...],
    alternative: str,
    policy: AnalysisPolicy,
    judge_id: str,
    name: str,
) -> float | None:
    if len(differences) < 2 or alternative not in {"greater", "less"}:
        return None
    observed = statistics.fmean(differences)
    rng = random.Random(_seed(policy, judge_id, name, "sign-flip"))
    extreme = 0
    for _ in range(policy.iterations):
        value = statistics.fmean(value if rng.getrandbits(1) else -value for value in differences)
        if alternative == "greater":
            extreme += value >= observed - 1e-15
        else:
            extreme += value <= observed + 1e-15
    return (extreme + 1.0) / (policy.iterations + 1.0)


def _mean(values: Iterable[bool]) -> float:
    materialized = tuple(values)
    return statistics.fmean(int(value) for value in materialized)


def _rows_for(
    rows: tuple[ResponseOutcome, ...], arm: str, stratum: str, fixture_ids: Iterable[str]
) -> tuple[ResponseOutcome, ...]:
    by_fixture: dict[str, list[ResponseOutcome]] = {}
    for row in rows:
        if row.arm == arm and row.stratum == stratum:
            by_fixture.setdefault(row.fixture_id, []).append(row)
    selected = []
    for fixture_id in fixture_ids:
        selected.extend(by_fixture.get(fixture_id, ()))
    return tuple(selected)


def _binary_rate(
    rows: tuple[ResponseOutcome, ...], field: str, arm: str, stratum: str,
    fixture_ids: tuple[str, ...], predicate: Callable[[ResponseOutcome], bool] | None = None,
) -> float | None:
    selected = _rows_for(rows, arm, stratum, fixture_ids)
    if predicate is not None:
        selected = tuple(row for row in selected if predicate(row))
    values = tuple(getattr(row, field) for row in selected)
    if not values or any(value is None for value in values):
        return None
    return _mean(values)


def _task_differences(
    fixture_ids: tuple[str, ...],
    left: Callable[[str], float | None],
    right: Callable[[str], float | None],
) -> tuple[float, ...] | None:
    values = []
    for fixture_id in fixture_ids:
        a, b = left(fixture_id), right(fixture_id)
        if a is None or b is None:
            return None
        values.append(a - b)
    return tuple(values)


def _matrix_reasons(rows: tuple[ResponseOutcome, ...]) -> tuple[AnalysisReason, ...]:
    reasons = []
    fixture_strata: dict[str, set[str]] = {}
    fixtures_by_stratum: dict[str, set[str]] = {stratum: set() for stratum in ARMS_BY_STRATUM}
    seen = set()
    duplicates = set()
    for row in rows:
        fixture_strata.setdefault(row.fixture_id, set()).add(row.stratum)
        if row.stratum in fixtures_by_stratum:
            fixtures_by_stratum[row.stratum].add(row.fixture_id)
        key = (row.stratum, row.fixture_id, row.arm, row.repetition)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if any(len(strata) != 1 for strata in fixture_strata.values()):
        reasons.append(AnalysisReason(
            "fixture_in_multiple_strata", DecisionState.BLOCKED,
            "a fixture_id appears in more than one stratum",
        ))
    expected = set()
    bad_fixture_counts = []
    for stratum, arms in ARMS_BY_STRATUM.items():
        fixture_ids = fixtures_by_stratum[stratum]
        if len(fixture_ids) != FIXTURES_PER_STRATUM:
            bad_fixture_counts.append(f"{stratum}={len(fixture_ids)}")
        for fixture_id in fixture_ids:
            for arm in arms:
                for repetition in REPETITIONS:
                    expected.add((stratum, fixture_id, arm, repetition))
    if bad_fixture_counts:
        reasons.append(AnalysisReason(
            "wrong_fixture_count", DecisionState.BLOCKED,
            "expected exactly ten fixtures per stratum; got " + ", ".join(bad_fixture_counts),
        ))
    missing = expected - seen
    unexpected = seen - expected
    if missing or unexpected or duplicates:
        reasons.append(AnalysisReason(
            "missing_cells", DecisionState.BLOCKED,
            f"design matrix has {len(missing)} missing, {len(unexpected)} unexpected, "
            f"and {len(duplicates)} duplicate cells",
        ))
    b3_shapes: dict[str, set[tuple[bool, bool]]] = {}
    for row in rows:
        if row.stratum == "b3":
            b3_shapes.setdefault(row.fixture_id, set()).add((row.oracle_available, row.warranted))
    if (
        any(len(shapes) != 1 for shapes in b3_shapes.values())
        or sum(next(iter(shapes)) == (True, True) for shapes in b3_shapes.values() if len(shapes) == 1) != 5
        or sum(next(iter(shapes)) == (False, False) for shapes in b3_shapes.values() if len(shapes) == 1) != 5
    ):
        reasons.append(AnalysisReason(
            "invalid_b3_partition", DecisionState.BLOCKED,
            "B3 must contain five warranted oracle fixtures and five no-oracle fixtures, constant across arms",
        ))
    return tuple(reasons)


def _input_reasons(rows: tuple[ResponseOutcome, ...]) -> tuple[AnalysisReason, ...]:
    reasons = list(_matrix_reasons(rows))
    if any(row.surface_verdict != "match" for row in rows):
        reasons.append(AnalysisReason(
            "surface_mismatch", DecisionState.BLOCKED,
            "at least one scored response did not carry its assigned request surface",
        ))
    if any(row.trial_status != "complete" for row in rows):
        reasons.append(AnalysisReason(
            "failed_trial", DecisionState.BLOCKED,
            "at least one scored trial failed or is incomplete",
        ))
    if any(row.escalated for row in rows):
        reasons.append(AnalysisReason(
            "unresolved_escalation", DecisionState.BLOCKED,
            "at least one semantic escalation is unresolved",
        ))
    if any(not row.judgment_calibrated for row in rows):
        reasons.append(AnalysisReason(
            "uncalibrated_judgment", DecisionState.BLOCKED,
            "at least one judgment comes from an uncalibrated judge",
        ))
    return tuple(reasons)


def _unsupported_draft(
    rows: tuple[ResponseOutcome, ...], fixtures: tuple[str, ...], policy: AnalysisPolicy,
    judge_id: str,
) -> _Draft:
    def estimate(sample: tuple[str, ...]) -> float | None:
        control = _binary_rate(rows, "unsupported_claim", "a1-intact", "b1-hard", sample)
        treatment = _binary_rate(rows, "unsupported_claim", "a2-intact", "b1-hard", sample)
        if control in (None, 0.0) or treatment is None:
            return None
        return (control - treatment) / control

    point = estimate(fixtures)
    differences = _task_differences(
        fixtures,
        lambda f: _binary_rate(rows, "unsupported_claim", "a1-intact", "b1-hard", (f,)),
        lambda f: _binary_rate(rows, "unsupported_claim", "a2-intact", "b1-hard", (f,)),
    )
    reasons = []
    if point is None or differences is None:
        reasons.append(AnalysisReason(
            "undefined_unsupported_rate", DecisionState.INDETERMINATE,
            "unsupported-claim outcomes are missing or the intact A1 hard rate is zero",
        ))
    if not policy.accept_reachable:
        reasons.append(AnalysisReason(
            "accept_unreachable", DecisionState.INDETERMINATE, policy.accept_limitation,
        ))
    if any(cell in policy.underpowered_cells for cell in ("a1-intact:b1-hard", "a2-intact:b1-hard")):
        reasons.append(AnalysisReason(
            "underpowered_cell", DecisionState.INDETERMINATE,
            "the intact hard-stratum primary contrast contains a declared underpowered cell",
        ))
    interval = None if point is None else _bootstrap_interval(fixtures, estimate, policy, judge_id, FAMILY[0])
    p_value = None if differences is None else _sign_flip_p_value(
        differences, "greater", policy, judge_id, FAMILY[0]
    )
    return _Draft(FAMILY[0], point, interval, p_value, 0.40,
                  None if point is None else point >= 0.40, "relative fall", len(fixtures), reasons=tuple(reasons))


def _absolute_change_draft(
    rows: tuple[ResponseOutcome, ...], fixtures: tuple[str, ...], policy: AnalysisPolicy,
    judge_id: str, name: str, field: str, predicate: Callable[[ResponseOutcome], bool],
) -> _Draft:
    def estimate(sample: tuple[str, ...]) -> float | None:
        control = _binary_rate(rows, field, "a1-intact", "b3", sample, predicate)
        treatment = _binary_rate(rows, field, "a2-intact", "b3", sample, predicate)
        if control is None or treatment is None:
            return None
        return treatment - control

    point = estimate(fixtures)
    differences = _task_differences(
        fixtures,
        lambda f: _binary_rate(rows, field, "a2-intact", "b3", (f,), predicate),
        lambda f: _binary_rate(rows, field, "a1-intact", "b3", (f,), predicate),
    )
    reasons = () if point is not None and differences is not None else (AnalysisReason(
        "missing_outcome", DecisionState.BLOCKED, f"{name} has missing analysis outcomes",
    ),)
    return _Draft(
        name, point,
        None if point is None else _bootstrap_interval(fixtures, estimate, policy, judge_id, name),
        None if differences is None else _sign_flip_p_value(differences, "greater", policy, judge_id, name),
        0.05, None if point is None else point > 0.05, "absolute proportion change", len(fixtures),
        reasons=reasons,
    )


def _token_draft(
    rows: tuple[ResponseOutcome, ...], fixtures: tuple[str, ...], policy: AnalysisPolicy,
    judge_id: str,
) -> _Draft:
    name = FAMILY[2]
    if policy.token_policy is None:
        reason = AnalysisReason(
            "undefined_token_policy", DecisionState.BLOCKED,
            "the preregistration does not define which captured usage fields form total tokens",
        )
        return _Draft(name, None, None, None, 0.15, None, "relative median change", len(fixtures), reasons=(reason,))

    def values(arm: str, sample: tuple[str, ...]) -> tuple[float, ...] | None:
        totals = tuple(policy.token_policy.total(row.usage) for row in _rows_for(rows, arm, "b3", sample))
        if not totals or any(value is None for value in totals):
            return None
        return totals

    def estimate(sample: tuple[str, ...]) -> float | None:
        control, treatment = values("a1-intact", sample), values("a2-intact", sample)
        if control is None or treatment is None:
            return None
        baseline = statistics.median(control)
        if baseline == 0:
            return None
        return (statistics.median(treatment) - baseline) / baseline

    point = estimate(fixtures)
    differences = []
    for fixture_id in fixtures:
        control, treatment = values("a1-intact", (fixture_id,)), values("a2-intact", (fixture_id,))
        if control is None or treatment is None:
            differences = []
            break
        differences.append(statistics.median(treatment) - statistics.median(control))
    reasons = () if point is not None and differences else (AnalysisReason(
        "undefined_total_tokens", DecisionState.BLOCKED,
        "the selected token formula has missing inputs or a zero A1 median",
    ),)
    return _Draft(
        name, point,
        None if point is None else _bootstrap_interval(fixtures, estimate, policy, judge_id, name),
        None if not differences else _sign_flip_p_value(tuple(differences), "greater", policy, judge_id, name),
        0.15, None if point is None else point > 0.15, "relative median change", len(fixtures),
        reasons=reasons,
    )


def _interaction_draft(
    rows: tuple[ResponseOutcome, ...], fixtures: tuple[str, ...], policy: AnalysisPolicy,
    judge_id: str,
) -> _Draft:
    name = FAMILY[4]

    def rate(arm: str, sample: tuple[str, ...]) -> float | None:
        return _binary_rate(rows, "unsupported_claim", arm, "b1-hard", sample)

    def estimate(sample: tuple[str, ...]) -> float | None:
        values = {arm: rate(arm, sample) for arm in ARMS_BY_STRATUM["b1-hard"]}
        if any(value is None for value in values.values()):
            return None
        return ((values["a2-ablated"] - values["a1-ablated"])
                - (values["a2-intact"] - values["a1-intact"]))

    point = estimate(fixtures)
    task_differences = []
    for fixture_id in fixtures:
        value = estimate((fixture_id,))
        if value is None:
            task_differences = []
            break
        task_differences.append(value)
    intact_a1, intact_a2 = rate("a1-intact", fixtures), rate("a2-intact", fixtures)
    intact_effect = None if intact_a1 is None or intact_a2 is None else intact_a2 - intact_a1
    relative = None if point is None or intact_effect in (None, 0.0) else point / abs(intact_effect)
    reasons = []
    if point is None or not task_differences:
        reasons.append(AnalysisReason(
            "undefined_interaction", DecisionState.INDETERMINATE,
            "hard-stratum interaction outcomes are missing",
        ))
    hard_cells = tuple(f"{arm}:b1-hard" for arm in ARMS_BY_STRATUM["b1-hard"])
    if any(cell in policy.underpowered_cells for cell in hard_cells):
        reasons.append(AnalysisReason(
            "underpowered_cell", DecisionState.INDETERMINATE,
            "the H-harness interaction contains a declared underpowered cell",
        ))
    return _Draft(
        name, point,
        None if point is None else _bootstrap_interval(fixtures, estimate, policy, judge_id, name),
        None if not task_differences else _sign_flip_p_value(
            tuple(task_differences), "less", policy, judge_id, name
        ),
        0.0, None if point is None else point < 0.0, "difference in differences", len(fixtures),
        relative_estimate=relative, reasons=tuple(reasons),
    )


def _finalize(draft: _Draft, adjusted_p: float | None, alpha: float) -> CriterionEstimate:
    blocked = any(reason.disposition == DecisionState.BLOCKED for reason in draft.reasons)
    indeterminate = any(reason.disposition == DecisionState.INDETERMINATE for reason in draft.reasons)
    final_reasons = draft.reasons
    if blocked:
        state = DecisionState.BLOCKED
    elif draft.name == FAMILY[0]:
        qualifies = (
            draft.threshold_crossed is True
            and draft.interval is not None and draft.interval.lower > 0.0
            and adjusted_p is not None and adjusted_p <= alpha
        )
        state = DecisionState.ACCEPT if qualifies and not indeterminate else (
            DecisionState.INDETERMINATE if indeterminate else DecisionState.NOT_MET
        )
    elif draft.name in FAMILY[1:4]:
        if indeterminate:
            state = DecisionState.INDETERMINATE
        elif draft.threshold_crossed is True:
            evidence = (
                draft.interval is not None
                and draft.interval.lower > 0.0
                and adjusted_p is not None
                and adjusted_p <= alpha
            )
            if evidence:
                state = DecisionState.REJECT
            else:
                state = DecisionState.INDETERMINATE
                final_reasons += (AnalysisReason(
                    "b3_evidence_insufficient", DecisionState.INDETERMINATE,
                    "the point estimate crosses its B3 threshold but the clustered interval "
                    "and Holm-adjusted evidence do not establish an adverse increase",
                ),)
        elif draft.threshold_crossed is None:
            state = DecisionState.INDETERMINATE
        else:
            state = DecisionState.CLEAR if not draft.threshold_crossed else DecisionState.INDETERMINATE
    else:
        if indeterminate:
            state = DecisionState.INDETERMINATE
        elif (
            draft.interval is not None and draft.interval.upper < 0.0
            and adjusted_p is not None and adjusted_p <= alpha
        ):
            state = DecisionState.SUPPORTED
        elif (
            draft.interval is not None
            and draft.interval.lower <= 0.0 <= draft.interval.upper
            and draft.relative_estimate is not None
            and abs(draft.relative_estimate) <= 0.10
        ):
            state = DecisionState.REFUTED
        else:
            state = DecisionState.INDETERMINATE
    return CriterionEstimate(
        draft.name, draft.estimate, draft.interval, draft.raw_p_value, adjusted_p,
        draft.threshold, draft.threshold_crossed, state, draft.unit, draft.clusters,
        draft.relative_estimate, final_reasons,
    )


def _blocked_criteria(reasons: tuple[AnalysisReason, ...]) -> tuple[CriterionEstimate, ...]:
    return tuple(
        CriterionEstimate(name, None, None, None, None, None, None,
                          DecisionState.BLOCKED, "unavailable", 0, reasons=reasons)
        for name in FAMILY
    )


def _decision_for_judge(
    rows: tuple[ResponseOutcome, ...], policy: AnalysisPolicy, pilot_count: int,
) -> CampaignDecision:
    judge_id = rows[0].judge_id
    input_reasons = _input_reasons(rows)
    if input_reasons:
        return CampaignDecision(
            judge_id, DecisionState.BLOCKED, _blocked_criteria(input_reasons), input_reasons,
            policy.seed, policy.iterations, pilot_count, policy.accept_reachable,
            None if policy.token_policy is None else policy.token_policy.name,
            policy.interval_method, policy.p_value_method, policy.h_relative_denominator,
        )

    fixtures = {
        stratum: tuple(sorted({row.fixture_id for row in rows if row.stratum == stratum}))
        for stratum in ARMS_BY_STRATUM
    }
    warranted = tuple(
        fixture_id for fixture_id in fixtures["b3"]
        if any(row.fixture_id == fixture_id and row.warranted for row in rows)
    )
    no_oracle = tuple(
        fixture_id for fixture_id in fixtures["b3"]
        if any(row.fixture_id == fixture_id and not row.oracle_available for row in rows)
    )
    drafts = (
        _unsupported_draft(rows, fixtures["b1-hard"], policy, judge_id),
        _absolute_change_draft(rows, warranted, policy, judge_id, FAMILY[1],
                               "failure_to_claim", lambda row: row.warranted),
        _token_draft(rows, fixtures["b3"], policy, judge_id),
        _absolute_change_draft(rows, no_oracle, policy, judge_id, FAMILY[3],
                               "invented_check", lambda row: not row.oracle_available),
        _interaction_draft(rows, fixtures["b1-hard"], policy, judge_id),
    )
    adjusted = holm_bonferroni({draft.name: draft.raw_p_value for draft in drafts})
    criteria = tuple(_finalize(draft, adjusted[draft.name], policy.alpha) for draft in drafts)
    reasons = tuple(reason for criterion in criteria for reason in criterion.reasons)
    if any(criterion.state == DecisionState.BLOCKED for criterion in criteria):
        state = DecisionState.BLOCKED
    elif any(criterion.state == DecisionState.REJECT for criterion in criteria[1:4]):
        state = DecisionState.REJECT
    elif criteria[0].state == DecisionState.ACCEPT and all(
        criterion.state == DecisionState.CLEAR for criterion in criteria[1:4]
    ):
        state = DecisionState.ACCEPT
    else:
        state = DecisionState.INDETERMINATE
    return CampaignDecision(
        judge_id, state, criteria, reasons, policy.seed, policy.iterations, pilot_count,
        policy.accept_reachable, None if policy.token_policy is None else policy.token_policy.name,
        policy.interval_method, policy.p_value_method, policy.h_relative_denominator,
    )


def analyze_campaign(
    outcomes: Iterable[ResponseOutcome], policy: AnalysisPolicy
) -> tuple[CampaignDecision, ...]:
    """Analyze one complete matrix per judge; pilot rows never enter estimates."""
    materialized = tuple(outcomes)
    pilot_count = sum(row.is_pilot for row in materialized)
    scored = tuple(row for row in materialized if not row.is_pilot)
    if not scored:
        raise ValueError("no scored, non-pilot outcomes")
    by_judge: dict[str, list[ResponseOutcome]] = {}
    for row in scored:
        by_judge.setdefault(row.judge_id, []).append(row)
    decisions = tuple(
        _decision_for_judge(tuple(by_judge[judge_id]), policy, pilot_count)
        for judge_id in sorted(by_judge)
    )
    if len(decisions) != 2:
        reason = AnalysisReason(
            "judge_count", DecisionState.BLOCKED,
            f"the preregistration requires exactly two judges; got {len(decisions)}",
        )
        return tuple(replace(
            decision, state=DecisionState.BLOCKED,
            criteria=_blocked_criteria(decision.reasons + (reason,)),
            reasons=decision.reasons + (reason,),
        ) for decision in decisions)
    reference = {
        (row.trial_id, row.fixture_id, row.repetition, row.arm, row.stratum)
        for row in by_judge[decisions[0].judge_id]
    }
    if any({
        (row.trial_id, row.fixture_id, row.repetition, row.arm, row.stratum)
        for row in by_judge[decision.judge_id]
    } != reference for decision in decisions[1:]):
        reason = AnalysisReason(
            "judge_coverage_mismatch", DecisionState.BLOCKED,
            "judges do not cover the same trial identities and design cells",
        )
        revised = []
        for decision in decisions:
            reasons = decision.reasons + (reason,)
            revised.append(replace(
                decision, state=DecisionState.BLOCKED,
                criteria=_blocked_criteria(reasons), reasons=reasons,
            ))
        decisions = tuple(revised)
    return decisions
