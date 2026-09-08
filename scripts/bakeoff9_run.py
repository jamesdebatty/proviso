#!/usr/bin/env python3
"""Immutable bakeoff 9 run plans, per-trial ledgers, and score bridge."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, runtime_checkable
from collections.abc import Sequence

try:
    from . import capture_spine
    from .bakeoff9_trajectory import (
        CommandEvent,
        EditEvent,
        TrajectoryEvidenceError,
        TrajectoryRecorder,
        snapshot_tree,
        validate_public_trajectory,
    )
except ImportError:
    import capture_spine
    from bakeoff9_trajectory import (
        CommandEvent,
        EditEvent,
        TrajectoryEvidenceError,
        TrajectoryRecorder,
        snapshot_tree,
        validate_public_trajectory,
    )


ROOT = Path(__file__).resolve().parent.parent
PLAN_SCHEMA = "bakeoff9-run-plan/1"
TRIAL_SCHEMA = "bakeoff9-trial/1"
ATTEMPT_SCHEMA = "bakeoff9-attempt/1"
PILOT_SCHEMA = "bakeoff9-pilot/1"
PILOT_STRATA = ("b1-easy", "b1-hard")
PILOT_ARM = "a1-intact"
FULL_ARMS_BY_STRATUM = {
    "b1-easy": ("a1-intact", "a2-intact"),
    "b1-hard": ("a1-intact", "a2-intact", "a1-ablated", "a2-ablated"),
    "b3": ("a1-intact", "a2-intact"),
}
FROZEN_REQUIRED_CLASSES = (
    "overall", "escalation:completion_word", "escalation:claim_support",
    "escalation:invented_check",
)
FROZEN_REPORTED_CLASSES = (
    "task_completion", "focus", "plain_language", "jargon_discipline",
    "nuance_and_safety", "unnecessary_passages", "unexplained_jargon",
    "missing_requirements", "material_errors",
)
FROZEN_TOKEN_TERMS = (
    "output_tokens", "thinking_tokens", "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
USAGE_FIELDS = {
    "input_tokens", "output_tokens", "thinking_tokens",
    "cache_creation_input_tokens", "cache_read_input_tokens",
    "turns", "api_error_turns",
}
CAPTURE_FIELDS = {
    "schema", "surface_verdict", "mode", "declared_configuration",
    "fragment_count", "synthetic_status", "preflight", "request_surfaces",
    "primary_request_count", "auxiliary_request_count",
    "auxiliary_request_surfaces", "auxiliary_cost_caveat", "result_usage",
    "baseline", "raw_bodies_retained", "raw_dir_purged", "sdk_init", "turns",
    "usage_totals", "cli_versions", "model_provenance", "raw_preserved",
    "raw_path_sha256", "trajectory_complete", "trajectory_error_sha256",
    "live_surface_bootstrap", "arm_reminder",
    "executed_tool_count", "denied_tool_count",
}
SDK_WIRE_KEYS = {
    "messages", "tool_input", "tool_response", "tool_use_id", "session_id",
    "request_body", "response_body", "raw_request", "raw_response",
}


class RunIntegrityError(ValueError):
    """An immutable input or committed artifact does not match its digest."""


class AuthorizationMismatchError(PermissionError):
    """Paid authorization is absent or bound to another exact plan."""


class AmbiguousDispatchError(RuntimeError):
    """A prior paid dispatch has no committed result and cannot be retried."""


class RunKind(str, Enum):
    CANARY = "canary"
    PILOT = "pilot"
    CAMPAIGN = "campaign"
    CLI_TRANSFER = "cli-transfer"


class AdapterKind(str, Enum):
    SDK_QUERY = "sdk-query"
    INTERACTIVE_CLI = "interactive-cli"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authorized_trial_ids_sha256(trial_ids: Sequence[str]) -> str:
    """Bind authorization to one exact ordered set of planned trial ids."""
    ids = list(trial_ids)
    if not ids or len(ids) != len(set(ids)) or not all(isinstance(item, str) for item in ids):
        raise AuthorizationMismatchError("authorized trial ids must be non-empty and unique")
    return _sha256(_canonical_bytes(ids))


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _frozen_mapping(value: Mapping | None) -> Mapping:
    return MappingProxyType(dict(value or {}))


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise RunIntegrityError(f"campaign input is outside the repository: {path}") from exc


def _contained_source_path(root: Path, value: str, *, kind: str) -> Path:
    """Resolve a declared source below root without allowing a symlink component."""
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise RunIntegrityError(f"{kind} path must be non-empty and relative: {value!r}")
    relative = Path(value)
    if ".." in relative.parts:
        raise RunIntegrityError(f"{kind} path may not contain '..': {value!r}")
    root = root.resolve()
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise RunIntegrityError(f"{kind} path contains a symbolic link: {value!r}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RunIntegrityError(f"{kind} path escapes its source root: {value!r}") from exc
    if not resolved.exists():
        raise RunIntegrityError(f"{kind} source does not exist: {value!r}")
    return resolved


def _repo_source_path(value: str, *, kind: str) -> Path:
    return _contained_source_path(ROOT, value, kind=kind)


def _campaign_source_path(campaign_dir: Path, value: str, *, kind: str) -> Path:
    return _contained_source_path(campaign_dir, value, kind=kind)


def _absolute_repo_source_path(path: Path, *, kind: str) -> Path:
    candidate = path if path.is_absolute() else Path.cwd() / path
    try:
        relative = candidate.relative_to(ROOT)
    except ValueError as exc:
        raise RunIntegrityError(f"{kind} source is outside the repository: {path}") from exc
    return _repo_source_path(relative.as_posix(), kind=kind)


def _validated_reference(value: object, *, kind: str) -> Mapping:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise RunIntegrityError(f"{kind} reference has an invalid shape")
    if not isinstance(value["sha256"], str) or not HEX_SHA256.fullmatch(value["sha256"]):
        raise RunIntegrityError(f"{kind} reference has an invalid sha256")
    return value


def fixture_tree_sha256(path: Path) -> str:
    """Digest one fixture directory using the trajectory tree algorithm."""
    return snapshot_tree(path).sha256


@dataclass(frozen=True)
class TrialCase:
    trial_id: str
    ordinal: int
    run_kind: RunKind
    adapter: AdapterKind
    fixture_id: str
    stratum: str
    fixture_path: str
    fixture_sha256: str
    prompt: str
    arm: str
    arm_path: str
    arm_sha256: str
    harness_prompt: str
    repetition: int
    excluded_from_primary_analysis: bool
    case_sha256: str
    _campaign_dir: Path | None = field(default=None, repr=False, compare=False)

    def to_dict(self, *, include_hash: bool = True) -> dict:
        value = {
            "trial_id": self.trial_id,
            "ordinal": self.ordinal,
            "run_kind": self.run_kind.value,
            "adapter": self.adapter.value,
            "fixture_id": self.fixture_id,
            "stratum": self.stratum,
            "fixture_path": self.fixture_path,
            "fixture_sha256": self.fixture_sha256,
            "prompt": self.prompt,
            "arm": self.arm,
            "arm_path": self.arm_path,
            "arm_sha256": self.arm_sha256,
            "harness_prompt": self.harness_prompt,
            "repetition": self.repetition,
            "excluded_from_primary_analysis": self.excluded_from_primary_analysis,
        }
        if include_hash:
            value["case_sha256"] = self.case_sha256
        return value

    @classmethod
    def from_dict(cls, value: Mapping, *, campaign_dir: Path) -> "TrialCase":
        raw = dict(value)
        expected = raw.pop("case_sha256", None)
        actual = _sha256(_canonical_bytes(raw))
        if expected != actual:
            raise RunIntegrityError(f"case hash mismatch for {raw.get('trial_id')!r}")
        return cls(
            trial_id=raw["trial_id"],
            ordinal=raw["ordinal"],
            run_kind=RunKind(raw["run_kind"]),
            adapter=AdapterKind(raw["adapter"]),
            fixture_id=raw["fixture_id"],
            stratum=raw["stratum"],
            fixture_path=raw["fixture_path"],
            fixture_sha256=raw["fixture_sha256"],
            prompt=raw["prompt"],
            arm=raw["arm"],
            arm_path=raw["arm_path"],
            arm_sha256=raw["arm_sha256"],
            harness_prompt=raw["harness_prompt"],
            repetition=raw["repetition"],
            excluded_from_primary_analysis=raw["excluded_from_primary_analysis"],
            case_sha256=expected,
            _campaign_dir=campaign_dir,
        )

    @classmethod
    def create(cls, *, campaign_dir: Path, **fields) -> "TrialCase":
        raw = {
            key: value.value if isinstance(value, Enum) else value
            for key, value in fields.items()
        }
        digest = _sha256(_canonical_bytes(raw))
        return cls(**fields, case_sha256=digest, _campaign_dir=campaign_dir)


@dataclass(frozen=True)
class RunPlan:
    campaign_id: str
    run_kind: RunKind
    adapter: AdapterKind
    protocol: Mapping
    declaration: Mapping
    pilot_declaration: Mapping | None
    fixture_set_sha256: str
    trials: tuple[TrialCase, ...]
    plan_sha256: str
    _campaign_dir: Path = field(repr=False, compare=False, default=Path("."))

    def __post_init__(self):
        object.__setattr__(self, "protocol", _frozen_mapping(self.protocol))
        object.__setattr__(self, "declaration", _frozen_mapping(self.declaration))
        if self.pilot_declaration is not None:
            object.__setattr__(self, "pilot_declaration", _frozen_mapping(self.pilot_declaration))

    def to_dict(self, *, include_hash: bool = True) -> dict:
        value = {
            "schema": PLAN_SCHEMA,
            "campaign_id": self.campaign_id,
            "run_kind": self.run_kind.value,
            "adapter": self.adapter.value,
            "protocol": dict(self.protocol),
            "declaration": dict(self.declaration),
            "pilot_declaration": (
                dict(self.pilot_declaration) if self.pilot_declaration is not None else None
            ),
            "fixture_set_sha256": self.fixture_set_sha256,
            "trials": [trial.to_dict() for trial in self.trials],
        }
        if include_hash:
            value["plan_sha256"] = self.plan_sha256
        return value

    def trial(self, trial_id: str) -> TrialCase:
        matches = [trial for trial in self.trials if trial.trial_id == trial_id]
        if len(matches) != 1:
            raise KeyError(f"plan has no unique trial {trial_id!r}")
        return matches[0]

    @classmethod
    def create(cls, *, campaign_dir: Path, **fields) -> "RunPlan":
        temporary = cls(**fields, plan_sha256="", _campaign_dir=campaign_dir)
        digest = _sha256(_canonical_bytes(temporary.to_dict(include_hash=False)))
        return cls(**fields, plan_sha256=digest, _campaign_dir=campaign_dir)

    @classmethod
    def from_dict(
        cls, value: Mapping, *, snapshot_dir: Path | None = None
    ) -> "RunPlan":
        raw = dict(value)
        if raw.get("schema") != PLAN_SCHEMA:
            raise RunIntegrityError(f"unknown run plan schema: {raw.get('schema')!r}")
        expected = raw.pop("plan_sha256", None)
        actual = _sha256(_canonical_bytes(raw))
        if expected != actual:
            raise RunIntegrityError("run plan hash mismatch")
        protocol = _validated_reference(raw.get("protocol"), kind="protocol")
        _validated_reference(raw.get("declaration"), kind="declaration")
        if raw.get("pilot_declaration") is not None:
            _validated_reference(raw["pilot_declaration"], kind="pilot declaration")
        protocol_path = _repo_source_path(protocol["path"], kind="protocol")
        campaign_dir = protocol_path.parent
        trials = tuple(
            TrialCase.from_dict(item, campaign_dir=campaign_dir) for item in raw["trials"]
        )
        plan = cls(
            campaign_id=raw["campaign_id"],
            run_kind=RunKind(raw["run_kind"]),
            adapter=AdapterKind(raw["adapter"]),
            protocol=raw["protocol"],
            declaration=raw["declaration"],
            pilot_declaration=raw.get("pilot_declaration"),
            fixture_set_sha256=raw["fixture_set_sha256"],
            trials=trials,
            plan_sha256=expected,
            _campaign_dir=campaign_dir,
        )
        plan.verify_integrity(snapshot_dir=snapshot_dir)
        return plan

    def verify_sources(self, *, snapshot_dir: Path | None = None) -> None:
        for kind, candidate in (("protocol", self.protocol), ("declaration", self.declaration)):
            reference = _validated_reference(candidate, kind=kind)
            path = _repo_source_path(reference["path"], kind=kind)
            if (
                not path.is_file() or _file_sha256(path) != reference["sha256"]
            ) and not _snapshot_matches(reference, snapshot_dir, kind=kind):
                raise RunIntegrityError(f"plan source changed: {reference['path']}")
        if self.pilot_declaration is not None:
            _validated_reference(self.pilot_declaration, kind="pilot declaration")
            path = _repo_source_path(
                self.pilot_declaration["path"], kind="pilot declaration"
            )
            if (
                not path.is_file() or _file_sha256(path) != self.pilot_declaration["sha256"]
            ) and not _snapshot_matches(
                self.pilot_declaration, snapshot_dir, kind="pilot declaration"
            ):
                raise RunIntegrityError(f"pilot declaration changed: {self.pilot_declaration['path']}")
        for case in self.trials:
            fixture = _campaign_source_path(
                self._campaign_dir, case.fixture_path, kind="fixture"
            )
            arm = _campaign_source_path(self._campaign_dir, case.arm_path, kind="arm")
            if fixture_tree_sha256(fixture) != case.fixture_sha256:
                raise RunIntegrityError(f"fixture changed after planning: {case.fixture_id}")
            if _file_sha256(arm) != case.arm_sha256:
                raise RunIntegrityError(f"arm changed after planning: {case.arm}")

    def verify_integrity(self, *, snapshot_dir: Path | None = None) -> None:
        if self.plan_sha256 != _sha256(_canonical_bytes(self.to_dict(include_hash=False))):
            raise RunIntegrityError("run plan object does not match its hash")
        ids = [case.trial_id for case in self.trials]
        ordinals = [case.ordinal for case in self.trials]
        if len(set(ids)) != len(ids) or ordinals != list(range(1, len(self.trials) + 1)):
            raise RunIntegrityError("run plan trial ids or ordinals are not unique and canonical")
        for case in self.trials:
            if case.case_sha256 != _sha256(_canonical_bytes(case.to_dict(include_hash=False))):
                raise RunIntegrityError(f"trial case object does not match its hash: {case.trial_id}")
        if self.fixture_set_sha256 != pilot_fixture_set_sha256(self.trials):
            raise RunIntegrityError("run plan fixture set does not match its hash")
        self.verify_sources(snapshot_dir=snapshot_dir)


def _snapshot_matches(
    reference: Mapping, snapshot_dir: Path | None, *, kind: str
) -> bool:
    if snapshot_dir is None:
        return False
    root = Path(snapshot_dir)
    if not root.is_dir() or root.is_symlink():
        return False
    try:
        candidate = _contained_source_path(
            root, Path(reference["path"]).name, kind=f"{kind} snapshot"
        )
    except RunIntegrityError:
        return False
    return candidate.is_file() and _file_sha256(candidate) == reference["sha256"]


@dataclass(frozen=True)
class PaidAuthorizationEvidence:
    present: bool
    byte_count: int
    sha256: str
    plan_sha256: str
    authorized_trial_count: int
    authorized_trial_ids_sha256: str

    def to_dict(self) -> dict:
        return {
            "present": self.present,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "plan_sha256": self.plan_sha256,
            "authorized_trial_count": self.authorized_trial_count,
            "authorized_trial_ids_sha256": self.authorized_trial_ids_sha256,
        }

    @classmethod
    def from_wording(
        cls, wording: str, *, plan: RunPlan,
        authorized_trial_ids: Sequence[str] | None = None,
        authorized_trial_count: int | None = None,
        authorized_trial_ids_sha256: str | None = None,
    ) -> "PaidAuthorizationEvidence":
        encoded = wording.encode("utf-8")
        return cls.from_digest(
            _sha256(encoded), len(encoded), plan=plan,
            authorized_trial_ids=authorized_trial_ids,
            authorized_trial_count=authorized_trial_count,
            authorized_trial_ids_sha256=authorized_trial_ids_sha256,
        )

    @classmethod
    def from_digest(
        cls,
        sha256: str,
        byte_count: int,
        *,
        plan: RunPlan,
        authorized_trial_ids: Sequence[str] | None = None,
        authorized_trial_count: int | None = None,
        authorized_trial_ids_sha256: str | None = None,
        present: bool = True,
    ) -> "PaidAuthorizationEvidence":
        if not HEX_SHA256.fullmatch(sha256):
            raise AuthorizationMismatchError("authorization digest must be lowercase sha256")
        if not isinstance(byte_count, int) or byte_count <= 0:
            raise AuthorizationMismatchError("authorization byte count must be positive")
        if authorized_trial_ids is not None:
            ids = list(authorized_trial_ids)
            count = len(ids)
            subset_sha256 = globals()["authorized_trial_ids_sha256"](ids)
            if authorized_trial_count is not None and authorized_trial_count != count:
                raise AuthorizationMismatchError("authorization count differs from selected ids")
            if authorized_trial_ids_sha256 is not None and authorized_trial_ids_sha256 != subset_sha256:
                raise AuthorizationMismatchError("authorization hash differs from selected ids")
        else:
            count = authorized_trial_count
            if count == len(plan.trials) and authorized_trial_ids_sha256 is None:
                subset_sha256 = globals()["authorized_trial_ids_sha256"](
                    [trial.trial_id for trial in plan.trials]
                )
            else:
                subset_sha256 = authorized_trial_ids_sha256
        if not isinstance(count, int) or count <= 0 or count > len(plan.trials):
            raise AuthorizationMismatchError("authorized trial count must be positive")
        if not isinstance(subset_sha256, str) or not HEX_SHA256.fullmatch(subset_sha256):
            raise AuthorizationMismatchError("authorized trial ids digest must be lowercase sha256")
        return cls(present, byte_count, sha256, plan.plan_sha256, count, subset_sha256)


@dataclass(frozen=True)
class GenerationResult:
    response: str
    usage: Mapping
    capture: Mapping

    def __post_init__(self):
        object.__setattr__(self, "usage", _frozen_mapping(self.usage))
        object.__setattr__(self, "capture", _frozen_mapping(self.capture))


@dataclass(frozen=True)
class GenerationFailure:
    code: str
    detail: str
    capture: Mapping = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "capture", _frozen_mapping(self.capture))


@runtime_checkable
class GenerationAdapter(Protocol):
    kind: AdapterKind

    def generate(
        self, case: TrialCase, workspace: Path, trajectory: TrajectoryRecorder
    ) -> GenerationResult | GenerationFailure:
        ...


@dataclass(frozen=True)
class CompletedTrial:
    artifact: Mapping

    @property
    def status(self) -> str:
        return "completed"

    @property
    def trial_id(self) -> str:
        return self.artifact["trial_id"]

    @property
    def response(self) -> str:
        return self.artifact["response"]

    @property
    def usage(self) -> Mapping:
        return self.artifact["usage"]

    @property
    def trajectory(self) -> tuple[Mapping, ...]:
        return tuple(self.artifact["trajectory"])

    def to_dict(self) -> dict:
        return dict(self.artifact)


@dataclass(frozen=True)
class FailedTrial:
    artifact: Mapping

    @property
    def status(self) -> str:
        return "failed"

    @property
    def trial_id(self) -> str:
        return self.artifact["trial_id"]

    @property
    def failure(self) -> Mapping:
        return self.artifact["failure"]

    def to_dict(self) -> dict:
        return dict(self.artifact)


TrialResult = CompletedTrial | FailedTrial


def _artifact_digest(value: Mapping) -> str:
    return _sha256(_canonical_bytes({k: v for k, v in value.items() if k != "artifact_sha256"}))


def _sdk_wire_problems(value: object, path: str = "") -> list[str]:
    problems: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{path}/{key}"
            if key in SDK_WIRE_KEYS:
                problems.append(f"{location}: raw SDK wire field escaped")
            problems.extend(_sdk_wire_problems(item, location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            problems.extend(_sdk_wire_problems(item, f"{path}[{index}]"))
    return problems


def _validate_capture(value: object) -> dict:
    if not isinstance(value, dict):
        raise RunIntegrityError("trial capture must be an object")
    unexpected = sorted(set(value) - CAPTURE_FIELDS)
    if unexpected:
        raise RunIntegrityError("trial capture has unexpected fields: " + ", ".join(unexpected))
    verdict = value.get("surface_verdict")
    if verdict not in {"match", "fake", "unrecorded", "ungraded"}:
        raise RunIntegrityError("trial capture has no surface verdict")
    if "mode" in value and value["mode"] not in {"live", "fake", "preflight"}:
        raise RunIntegrityError("trial capture has an invalid mode")
    if "declared_configuration" in value and not isinstance(
        value["declared_configuration"], dict
    ):
        raise RunIntegrityError("trial capture declared configuration must be an object")
    if "fragment_count" in value and (
        isinstance(value["fragment_count"], bool)
        or not isinstance(value["fragment_count"], int)
        or value["fragment_count"] < 0
    ):
        raise RunIntegrityError("trial capture fragment count must be non-negative")
    if "preflight" in value and not isinstance(value["preflight"], dict):
        raise RunIntegrityError("trial capture preflight must be an object")
    if "request_surfaces" in value and not isinstance(value["request_surfaces"], list):
        raise RunIntegrityError("trial capture request surfaces must be a list")
    for field in (
        "primary_request_count", "auxiliary_request_count",
        "executed_tool_count", "denied_tool_count",
    ):
        if field in value and (
            isinstance(value[field], bool)
            or not isinstance(value[field], int)
            or value[field] < 0
        ):
            raise RunIntegrityError(f"trial capture {field} must be non-negative")
    if "auxiliary_request_surfaces" in value and not isinstance(
        value["auxiliary_request_surfaces"], list
    ):
        raise RunIntegrityError("trial capture auxiliary surfaces must be a list")
    for field in ("raw_bodies_retained", "raw_dir_purged", "raw_preserved"):
        if field in value and not isinstance(value[field], bool):
            raise RunIntegrityError(f"trial capture {field} must be boolean")
    if "trajectory_complete" in value and not isinstance(value["trajectory_complete"], bool):
        raise RunIntegrityError("trial capture trajectory completeness must be boolean")
    if "trajectory_error_sha256" in value and (
        not isinstance(value["trajectory_error_sha256"], str)
        or not HEX_SHA256.fullmatch(value["trajectory_error_sha256"])
    ):
        raise RunIntegrityError("trial capture trajectory error hash is invalid")
    if value.get("trajectory_complete") is False and "trajectory_error_sha256" not in value:
        raise RunIntegrityError("incomplete trajectory capture lacks an error hash")
    if "raw_path_sha256" in value and (
        not isinstance(value["raw_path_sha256"], str)
        or not HEX_SHA256.fullmatch(value["raw_path_sha256"])
    ):
        raise RunIntegrityError("trial capture raw path hash is invalid")
    for field in (
        "result_usage", "baseline", "sdk_init", "usage_totals",
        "cli_versions", "model_provenance", "live_surface_bootstrap", "arm_reminder",
    ):
        if field in value and not isinstance(value[field], dict):
            raise RunIntegrityError(f"trial capture {field} must be an object")
    if "turns" in value and not isinstance(value["turns"], list):
        raise RunIntegrityError("trial capture turns must be a list")
    if verdict == "match":
        required_live = {
            "schema", "preflight", "request_surfaces", "primary_request_count",
            "auxiliary_request_count", "auxiliary_request_surfaces", "result_usage",
            "baseline", "raw_bodies_retained", "raw_dir_purged", "sdk_init", "turns",
            "usage_totals", "cli_versions", "model_provenance",
            "executed_tool_count", "denied_tool_count",
        }
        missing = sorted(required_live - set(value))
        if missing:
            raise RunIntegrityError(
                "matched live capture is missing fields: " + ", ".join(missing)
            )
        if value["schema"] != capture_spine.MANIFEST_SCHEMA_VERSION:
            raise RunIntegrityError("matched live capture has the wrong schema")
        if value["primary_request_count"] < 1 or not value["request_surfaces"]:
            raise RunIntegrityError("matched live capture has no primary request evidence")
        if value["raw_bodies_retained"] is not False or value["raw_dir_purged"] is not True:
            raise RunIntegrityError("matched live capture did not purge its raw tier")
        if not value["turns"]:
            raise RunIntegrityError("matched live capture has no sanitized turns")
        if value.get("mode") == "live":
            bootstrap = value.get("live_surface_bootstrap") or {}
            reminder = value.get("arm_reminder") or {}
            if bootstrap.get("schema") != "bakeoff9-live-surface-bootstrap/1":
                raise RunIntegrityError("matched live capture lacks a surface bootstrap")
            if reminder.get("verified") is not True:
                raise RunIntegrityError("matched live capture lacks verified arm reminder evidence")
            if reminder.get("verified_requests") != reminder.get("primary_request_count"):
                raise RunIntegrityError("matched live capture arm reminder counts differ")
            if not isinstance(reminder.get("arm_sha256"), str) or not HEX_SHA256.fullmatch(
                reminder["arm_sha256"]
            ):
                raise RunIntegrityError("matched live capture arm hash is invalid")
    if value.get("raw_preserved") is True and "raw_path_sha256" not in value:
        raise RunIntegrityError("preserved raw capture lacks a path hash")
    problems = capture_spine.retention_problems(value) + _sdk_wire_problems(value)
    if problems:
        raise RunIntegrityError("capture record violates retention: " + "; ".join(problems))
    return value


def _validate_usage(value: object) -> dict:
    if not isinstance(value, dict):
        raise RunIntegrityError("completed trial usage must be an object")
    unexpected = sorted(set(value) - USAGE_FIELDS)
    missing = sorted({"input_tokens", "output_tokens"} - set(value))
    if unexpected or missing:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unexpected:
            detail.append("unexpected " + ", ".join(unexpected))
        raise RunIntegrityError("completed trial usage shape is invalid: " + "; ".join(detail))
    if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in value.values()):
        raise RunIntegrityError("completed trial usage counts must be non-negative integers")
    problems = capture_spine.retention_problems(value) + _sdk_wire_problems(value)
    if problems:
        raise RunIntegrityError("usage record violates retention: " + "; ".join(problems))
    return value


def _validate_response(
    response: object, response_sha256: object, response_redacted: object
) -> str:
    if not isinstance(response, str):
        raise RunIntegrityError("completed trial response must be text")
    if response_sha256 != _sha256(response.encode("utf-8")):
        raise RunIntegrityError("response hash mismatch")
    if capture_spine.REMINDER_TAG.search(response):
        raise RunIntegrityError("response contains a retained system-reminder payload")
    if capture_spine.redact(response) != response:
        raise RunIntegrityError("response contains credential-shaped text")
    if not isinstance(response_redacted, bool):
        raise RunIntegrityError("completed trial response redaction flag is invalid")
    return response


def _validate_failure(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"stage", "code", "detail"}:
        raise RunIntegrityError("failed trial has an invalid failure record")
    if value.get("stage") != "generation" or not isinstance(value.get("code"), str):
        raise RunIntegrityError("failed trial has an invalid failure discriminator")
    detail = value.get("detail")
    if not isinstance(detail, str) or len(detail) > capture_spine.MAX_RECORD_STRING:
        raise RunIntegrityError("failed trial detail is invalid")
    problems = capture_spine.retention_problems(value) + _sdk_wire_problems(value)
    if problems:
        raise RunIntegrityError("failure record violates retention: " + "; ".join(problems))
    return value


def _validate_artifact(value: Mapping, *, plan: RunPlan) -> TrialResult:
    artifact = dict(value)
    if artifact.get("schema") != TRIAL_SCHEMA:
        raise RunIntegrityError(f"unknown trial schema: {artifact.get('schema')!r}")
    if artifact.get("artifact_sha256") != _artifact_digest(artifact):
        raise RunIntegrityError(f"trial artifact hash mismatch: {artifact.get('trial_id')}")
    common_fields = {
        "schema", "status", "trial_id", "case_sha256", "plan_sha256", "run_kind",
        "adapter", "fixture_id", "stratum", "arm", "repetition",
        "excluded_from_primary_analysis", "fixture", "authorization", "workspace",
        "trajectory", "capture", "artifact_sha256",
    }
    status = artifact.get("status")
    expected_fields = (
        common_fields | {"response", "response_sha256", "response_redacted", "usage"}
        if status == "completed"
        else common_fields | {"failure"}
        if status == "failed"
        else set()
    )
    if not expected_fields or set(artifact) != expected_fields:
        raise RunIntegrityError("trial fields do not match a completed or failed discriminator")
    case = plan.trial(artifact["trial_id"])
    if artifact.get("plan_sha256") != plan.plan_sha256:
        raise RunIntegrityError(f"trial belongs to another plan: {case.trial_id}")
    if artifact.get("case_sha256") != case.case_sha256:
        raise RunIntegrityError(f"trial case hash mismatch: {case.trial_id}")
    expected_metadata = {
        "run_kind": case.run_kind.value,
        "adapter": case.adapter.value,
        "fixture_id": case.fixture_id,
        "stratum": case.stratum,
        "arm": case.arm,
        "repetition": case.repetition,
        "excluded_from_primary_analysis": case.excluded_from_primary_analysis,
    }
    if any(artifact.get(name) != expected for name, expected in expected_metadata.items()):
        raise RunIntegrityError(f"trial metadata differs from its case: {case.trial_id}")
    fixture = artifact.get("fixture") or {}
    fixture_dir = _campaign_source_path(plan._campaign_dir, case.fixture_path, kind="fixture")
    expected_contract = json.loads(
        _contained_source_path(
            fixture_dir, "fixture.json", kind="fixture contract"
        ).read_text()
    )
    if (
        fixture.get("path") != case.fixture_path
        or fixture.get("sha256") != case.fixture_sha256
        or fixture.get("contract") != expected_contract
    ):
        raise RunIntegrityError(f"trial fixture differs from its case: {case.trial_id}")
    authorization = artifact.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
        "present", "byte_count", "sha256", "plan_sha256", "authorized_trial_count",
        "authorized_trial_ids_sha256",
    }:
        raise RunIntegrityError("trial authorization evidence has an invalid shape")
    evidence = PaidAuthorizationEvidence(**authorization)
    _validate_authorization(plan, evidence)
    if evidence.authorized_trial_count == 1:
        expected_subset = authorized_trial_ids_sha256([case.trial_id])
        if evidence.authorized_trial_ids_sha256 != expected_subset:
            raise AuthorizationMismatchError("single-trial authorization does not bind this trial")
    elif evidence.authorized_trial_count == len(plan.trials):
        expected_subset = authorized_trial_ids_sha256(
            [planned.trial_id for planned in plan.trials]
        )
        if evidence.authorized_trial_ids_sha256 != expected_subset:
            raise AuthorizationMismatchError("full-plan authorization hash is invalid")
    workspace = artifact.get("workspace")
    if (
        not isinstance(workspace, dict)
        or set(workspace) != {"initial_sha256", "final_sha256"}
        or any(
            not isinstance(value, str) or not HEX_SHA256.fullmatch(value)
            for value in workspace.values()
        )
    ):
        raise RunIntegrityError("trial workspace evidence has an invalid shape")
    trajectory = validate_public_trajectory(artifact.get("trajectory") or [])
    trajectory_problems = capture_spine.retention_problems(trajectory) + _sdk_wire_problems(trajectory)
    if trajectory_problems:
        raise RunIntegrityError(
            "trajectory violates retention: " + "; ".join(trajectory_problems)
        )
    capture = _validate_capture(artifact.get("capture"))
    if (capture.get("arm_reminder") or {}).get("arm_sha256") not in {None, case.arm_sha256}:
        raise RunIntegrityError("trial capture arm reminder belongs to another arm")
    if status == "completed":
        _validate_response(
            artifact.get("response"), artifact.get("response_sha256"),
            artifact.get("response_redacted"),
        )
        _validate_usage(artifact.get("usage"))
        return CompletedTrial(MappingProxyType(artifact))
    if status == "failed":
        _validate_failure(artifact.get("failure"))
        return FailedTrial(MappingProxyType(artifact))
    raise RunIntegrityError(f"unknown trial status: {artifact.get('status')!r}")


def pilot_fixture_set_sha256(cases: tuple[TrialCase, ...]) -> str:
    value = [
        {
            "stratum": case.stratum,
            "fixture_id": case.fixture_id,
            "fixture_sha256": case.fixture_sha256,
        }
        for case in cases
    ]
    return _sha256(_canonical_bytes(value))


def _pilot_declaration(path: Path, *, cases: tuple[TrialCase, ...], campaign_id: str,
                       declaration_sha256: str, arm_sha256: str) -> Mapping | None:
    if not path.is_file():
        return None
    path = _absolute_repo_source_path(path, kind="pilot declaration")
    data = tomllib.loads(path.read_text())
    expected_ids = [case.fixture_id for case in cases]
    expected_set = pilot_fixture_set_sha256(cases)
    checks = {
        "schema": PILOT_SCHEMA,
        "campaign_id": campaign_id,
        "campaign_declaration_sha256": declaration_sha256,
        "fixture_set_sha256": expected_set,
        "arm": PILOT_ARM,
        "arm_sha256": arm_sha256,
        "repetitions": 1,
        "excluded_from_primary_analysis": True,
        "ordering": "stratum-then-fixture-id",
        "seed": 0,
        "fixture_ids": expected_ids,
    }
    mismatches = [name for name, expected in checks.items() if data.get(name) != expected]
    if mismatches:
        raise RunIntegrityError(
            "pilot declaration does not match the canonical pilot: " + ", ".join(mismatches)
        )
    return {"path": _repo_relative(path), "sha256": _file_sha256(path)}


def build_pilot_plan(
    campaign_dir: Path, pilot_declaration: Path | None = None
) -> RunPlan:
    """Build the exact A1/intact, one-repetition, twenty-B1 pilot plan."""
    campaign_dir = campaign_dir.resolve()
    protocol_path = _campaign_source_path(
        campaign_dir, "preregistration.md", kind="protocol"
    )
    declaration_path = _campaign_source_path(
        campaign_dir, "campaign.toml", kind="declaration"
    )
    declaration = tomllib.loads(declaration_path.read_text())
    campaign_id = declaration["campaign"]["id"]
    arm = next(item for item in declaration["arms"] if item["id"] == PILOT_ARM)
    arm_path = _campaign_source_path(campaign_dir, arm["claude_md"], kind="arm")
    actual_arm_sha = _file_sha256(arm_path)
    if actual_arm_sha != arm["sha256"]:
        raise RunIntegrityError("a1-intact arm does not match campaign.toml")
    cases: list[TrialCase] = []
    ordinal = 0
    for stratum in PILOT_STRATA:
        for fixture_dir in sorted(
            (campaign_dir / declaration["battery"]["fixtures_dir"] / stratum).iterdir(),
            key=lambda path: path.name,
        ):
            if not fixture_dir.is_dir():
                continue
            fixture_dir = _campaign_source_path(
                campaign_dir,
                fixture_dir.relative_to(campaign_dir).as_posix(),
                kind="fixture",
            )
            contract = json.loads(
                _contained_source_path(fixture_dir, "fixture.json", kind="fixture contract").read_text()
            )
            if contract["stratum"] != stratum or contract["id"] != fixture_dir.name:
                raise RunIntegrityError(f"fixture path and contract disagree: {fixture_dir}")
            ordinal += 1
            fields = {
                "trial_id": f"pilot-{ordinal:02d}-{stratum}-{contract['id']}-a1-intact",
                "ordinal": ordinal,
                "run_kind": RunKind.PILOT,
                "adapter": AdapterKind.SDK_QUERY,
                "fixture_id": contract["id"],
                "stratum": stratum,
                "fixture_path": fixture_dir.relative_to(campaign_dir).as_posix(),
                "fixture_sha256": fixture_tree_sha256(fixture_dir),
                "prompt": contract["prompt"],
                "arm": PILOT_ARM,
                "arm_path": arm["claude_md"],
                "arm_sha256": actual_arm_sha,
                "harness_prompt": arm["harness_prompt"],
                "repetition": 1,
                "excluded_from_primary_analysis": True,
            }
            cases.append(TrialCase.create(campaign_dir=campaign_dir, **fields))
    frozen_cases = tuple(cases)
    stratum_counts = Counter(case.stratum for case in frozen_cases)
    if len(frozen_cases) != 20 or stratum_counts != Counter({name: 10 for name in PILOT_STRATA}):
        raise RunIntegrityError("pilot must contain exactly every B1 fixture once")
    if len({case.fixture_id for case in frozen_cases}) != len(frozen_cases):
        raise RunIntegrityError("pilot fixture ids must be unique across both B1 strata")
    pilot_path = pilot_declaration or campaign_dir / "pilot.toml"
    declaration_sha256 = _file_sha256(declaration_path)
    heading = "\n".join(protocol_path.read_text().splitlines()[:8]).lower()
    if "status: **frozen" in heading and "not frozen" not in heading:
        historical_declaration = _campaign_source_path(
            campaign_dir,
            "results/pilot-corrected-2026-08-27/snapshots/campaign.toml",
            kind="corrected-pilot campaign snapshot",
        )
        declaration_sha256 = _file_sha256(historical_declaration)
    pilot_ref = _pilot_declaration(
        pilot_path,
        cases=frozen_cases,
        campaign_id=campaign_id,
        declaration_sha256=declaration_sha256,
        arm_sha256=actual_arm_sha,
    )
    return RunPlan.create(
        campaign_dir=campaign_dir,
        campaign_id=campaign_id,
        run_kind=RunKind.PILOT,
        adapter=AdapterKind.SDK_QUERY,
        protocol={"path": _repo_relative(protocol_path), "sha256": _file_sha256(protocol_path)},
        declaration={
            "path": _repo_relative(declaration_path), "sha256": _file_sha256(declaration_path)
        },
        pilot_declaration=pilot_ref,
        fixture_set_sha256=pilot_fixture_set_sha256(frozen_cases),
        trials=frozen_cases,
    )


def build_full_plan(campaign_dir: Path, *, allow_draft: bool = False) -> RunPlan:
    """Build the exact declared 240-response factorial campaign."""
    campaign_dir = campaign_dir.resolve()
    protocol_path = _campaign_source_path(campaign_dir, "preregistration.md", kind="protocol")
    heading = "\n".join(protocol_path.read_text().splitlines()[:8]).lower()
    frozen = "status: **frozen" in heading and "not frozen" not in heading
    if not frozen and not allow_draft:
        raise RunIntegrityError("full campaign planning requires a frozen protocol")
    declaration_path = _campaign_source_path(campaign_dir, "campaign.toml", kind="declaration")
    declaration = tomllib.loads(declaration_path.read_text())
    validate_freeze_declaration(declaration)
    battery = declaration.get("battery") or {}
    if (
        battery.get("strata") != list(FULL_ARMS_BY_STRATUM)
        or battery.get("fixtures_per_stratum") != 10
        or battery.get("repetitions") != 3
        or battery.get("scored_responses") != 240
    ):
        raise RunIntegrityError("campaign battery does not declare the frozen 240-response design")
    arms = {arm.get("id"): arm for arm in declaration.get("arms") or []}
    if set(arms) != {arm for values in FULL_ARMS_BY_STRATUM.values() for arm in values}:
        raise RunIntegrityError("campaign arms do not match the frozen factorial design")
    expected_strata = {
        "a1-intact": ["b1-easy", "b1-hard", "b3"],
        "a2-intact": ["b1-easy", "b1-hard", "b3"],
        "a1-ablated": ["b1-hard"],
        "a2-ablated": ["b1-hard"],
    }
    arm_paths = {}
    for arm_id, arm in arms.items():
        if arm.get("strata") != expected_strata[arm_id]:
            raise RunIntegrityError(f"{arm_id} strata do not match the frozen design")
        path = _campaign_source_path(campaign_dir, arm.get("claude_md"), kind="arm")
        digest = _file_sha256(path)
        if digest != arm.get("sha256"):
            raise RunIntegrityError(f"{arm_id} arm does not match campaign.toml")
        arm_paths[arm_id] = (path, digest)
    fixtures_root = _campaign_source_path(
        campaign_dir, battery.get("fixtures_dir"), kind="fixtures directory"
    )
    cases = []
    ordinal = 0
    fixture_ids = set()
    for stratum, stratum_arms in FULL_ARMS_BY_STRATUM.items():
        directory = _contained_source_path(fixtures_root, stratum, kind="fixture stratum")
        fixtures = tuple(path for path in sorted(directory.iterdir()) if path.is_dir())
        if len(fixtures) != 10:
            raise RunIntegrityError(f"{stratum} must contain exactly ten fixtures")
        for fixture_dir in fixtures:
            fixture_dir = _campaign_source_path(
                campaign_dir, fixture_dir.relative_to(campaign_dir).as_posix(), kind="fixture"
            )
            contract = json.loads(
                _contained_source_path(fixture_dir, "fixture.json", kind="fixture contract").read_text()
            )
            if contract.get("stratum") != stratum or contract.get("id") != fixture_dir.name:
                raise RunIntegrityError(f"fixture path and contract disagree: {fixture_dir}")
            if contract["id"] in fixture_ids:
                raise RunIntegrityError(f"fixture ids must be globally unique: {contract['id']}")
            fixture_ids.add(contract["id"])
            fixture_sha = fixture_tree_sha256(fixture_dir)
            for arm_id in stratum_arms:
                arm = arms[arm_id]
                for repetition in range(1, 4):
                    ordinal += 1
                    fields = {
                        "trial_id": (
                            f"campaign-{ordinal:03d}-{stratum}-{contract['id']}-{arm_id}-r{repetition}"
                        ),
                        "ordinal": ordinal,
                        "run_kind": RunKind.CAMPAIGN,
                        "adapter": AdapterKind.SDK_QUERY,
                        "fixture_id": contract["id"],
                        "stratum": stratum,
                        "fixture_path": fixture_dir.relative_to(campaign_dir).as_posix(),
                        "fixture_sha256": fixture_sha,
                        "prompt": contract["prompt"],
                        "arm": arm_id,
                        "arm_path": arm["claude_md"],
                        "arm_sha256": arm_paths[arm_id][1],
                        "harness_prompt": arm["harness_prompt"],
                        "repetition": repetition,
                        "excluded_from_primary_analysis": False,
                    }
                    cases.append(TrialCase.create(campaign_dir=campaign_dir, **fields))
    frozen_cases = tuple(cases)
    observed = Counter((case.stratum, case.arm) for case in frozen_cases)
    expected = Counter({
        (stratum, arm): 30
        for stratum, stratum_arms in FULL_ARMS_BY_STRATUM.items()
        for arm in stratum_arms
    })
    if len(frozen_cases) != 240 or observed != expected or ordinal != 240:
        raise RunIntegrityError("full campaign plan does not contain the exact 240 declared cells")
    return RunPlan.create(
        campaign_dir=campaign_dir,
        campaign_id=declaration["campaign"]["id"],
        run_kind=RunKind.CAMPAIGN,
        adapter=AdapterKind.SDK_QUERY,
        protocol={"path": _repo_relative(protocol_path), "sha256": _file_sha256(protocol_path)},
        declaration={"path": _repo_relative(declaration_path), "sha256": _file_sha256(declaration_path)},
        pilot_declaration=None,
        fixture_set_sha256=pilot_fixture_set_sha256(frozen_cases),
        trials=frozen_cases,
    )


def validate_freeze_declaration(declaration: Mapping) -> None:
    """Fail closed unless every issue #10 interpretation choice is bound."""
    freeze = declaration.get("freeze")
    if not isinstance(freeze, Mapping):
        raise RunIntegrityError("campaign declaration has no decision-relevant freeze")
    if (
        freeze.get("date") != "2026-08-28"
        or freeze.get("protocol_edition") != "solo-owner-reference/1"
        or freeze.get("pilot_p0") != 0.5
    ):
        raise RunIntegrityError("freeze date or corrected-pilot p0 is not bound")
    if (
        freeze.get("primary_plan") != "primary-plan-2026-08-28b-gated-classes.json"
        or freeze.get("supersedes_primary_plan_sha256")
        != "8234a9303f96167ff8e425d2f366c571540c75b1c692e31f22b9c701b9453e3a"
    ):
        raise RunIntegrityError("primary plan path is not frozen")

    design = freeze.get("design") or {}
    if (
        design.get("accept_capable") is not False
        or design.get("posture") != "refute-or-indeterminate-only"
        or not design.get("accept_limitation")
    ):
        raise RunIntegrityError("detectable-design posture is not frozen")

    analysis = freeze.get("analysis") or {}
    expected_analysis = {
        "seed": 20260827,
        "iterations": 9999,
        "alpha": 0.05,
        "interval_method": "fixture_cluster_percentile_bootstrap",
        "p_value_method": "paired_task_sign_flip",
        "h_relative_denominator": "absolute_intact_clause_effect",
    }
    if any(analysis.get(key) != value for key, value in expected_analysis.items()):
        raise RunIntegrityError("campaign analysis policy is not frozen")

    tokens = freeze.get("tokens") or {}
    if (
        tuple(tokens.get("terms") or ()) != FROZEN_TOKEN_TERMS
        or tuple(tokens.get("weights") or ()) != (1.0, 1.0, 1.0, 1.0)
        or tokens.get("missing") != "unavailable-not-zero"
    ):
        raise RunIntegrityError("B3 total-token formula is not frozen")

    judges = freeze.get("judges") or {}
    expected_judges = {
        "openai": (
            "OpenAI", "gpt-5.4-2026-03-05",
            "https://developers.openai.com/api/docs/models/gpt-5.4", "2026-08-27",
        ),
        "zai": (
            "Z.ai", "glm-5.3-flash",
            "https://docs.z.ai/guides/llm/glm-5.3-flash", "2026-08-28",
        ),
    }
    if set(judges) != set(expected_judges):
        raise RunIntegrityError("judge vendors are not the two frozen non-Anthropic vendors")
    for provider, (vendor, model, documentation, accessed) in expected_judges.items():
        item = judges.get(provider) or {}
        if (
            item.get("vendor") != vendor
            or item.get("model") != model
            or item.get("documentation") != documentation
            or item.get("accessed") != accessed
            or item.get("resolved_model_must_equal_requested") is not True
        ):
            raise RunIntegrityError(f"{provider} judge binding is not frozen")

    gold = freeze.get("gold") or {}
    if (
        gold.get("membership_manifest") != "gold-membership-solo-owner-2026-08-28.json"
        or gold.get("artifact") != "gold/owner-reference.json"
        or gold.get("reference_kind") != "owner-adjudicated"
        or tuple(gold.get("required_classes") or ()) != FROZEN_REQUIRED_CLASSES
        or tuple(gold.get("reported_classes") or ()) != FROZEN_REPORTED_CLASSES
        or gold.get("minimum_cases_per_class") != 5
        or gold.get("complete_owner_passes") != 1
        or gold.get("repeat_strategy") != "class-balanced-digest-rank-v2"
        or gold.get("repeat_selection_seed") != 20260828
        or gold.get("minimum_repeat_cases_per_class") != 5
        or gold.get("minimum_repeat_gap_hours") != 72
        or gold.get("owner_kind") != "human-no-model-substitute"
        or any(gold.get(key) is not True for key in (
            "owner_self_adjudication", "preserve_original_observations",
            "treatment_blind", "membership_frozen_before_vendor_calls",
        ))
    ):
        raise RunIntegrityError("owner-reference procedure is not frozen")

    calibration = freeze.get("calibration") or {}
    if (
        calibration.get("minimum_exact_agreement") != 0.8
        or calibration.get("minimum_cohen_kappa") != 0.6
        or calibration.get("allow_perfect_degenerate") is not False
        or calibration.get("failure") != "block-without-retuning"
    ):
        raise RunIntegrityError("judge calibration policy is not frozen")

    audit = freeze.get("audit") or {}
    if (
        audit.get("seed") != 20260827
        or audit.get("sample_size") != 20
        or audit.get("include_agreement_and_disagreement_when_available") is not True
        or audit.get("include_unanimous_pass_when_available") is not True
    ):
        raise RunIntegrityError("judge audit policy is not frozen")

    transfer = freeze.get("cli_transfer") or {}
    if (
        transfer.get("stratum") != "b1-hard"
        or tuple(transfer.get("arms") or ()) != ("a1-intact", "a2-intact")
        or transfer.get("fixtures") != "all-10"
        or tuple(transfer.get("repetitions") or ()) != (1,)
        or transfer.get("adapter") != "interactive-cli"
        or transfer.get("pair_to") != "sdk-same-fixture-arm-repetition-1"
        or transfer.get("responses") != 20
        or transfer.get("primary_analysis_eligible") is not False
        or transfer.get("decision_rule") != "signed-a2-minus-a1-direction"
    ):
        raise RunIntegrityError("paired CLI transfer policy is not frozen")


def primary_plan_path(campaign_dir: Path) -> Path:
    declaration = tomllib.loads((Path(campaign_dir) / "campaign.toml").read_text())
    validate_freeze_declaration(declaration)
    return _campaign_source_path(
        Path(campaign_dir).resolve(), declaration["freeze"]["primary_plan"],
        kind="primary plan",
    )


def materialize_primary_plan(campaign_dir: Path) -> RunPlan:
    """Create or confirm the immutable content-addressed 240-response plan."""
    campaign_dir = Path(campaign_dir).resolve()
    declaration = tomllib.loads((campaign_dir / "campaign.toml").read_text())
    validate_freeze_declaration(declaration)
    relative = declaration["freeze"]["primary_plan"]
    path = campaign_dir / relative
    if path.is_symlink() or path.parent.resolve() != campaign_dir:
        raise RunIntegrityError("primary plan path must be a direct campaign child")
    plan = build_full_plan(campaign_dir)
    TrialStore._atomic_create(path, plan.to_dict())
    loaded = load_plan(path)
    if loaded.to_dict() != plan.to_dict():
        raise RunIntegrityError("materialized primary plan differs from the frozen design")
    return loaded


def validate_primary_plan(campaign_dir: Path) -> RunPlan:
    """Validate the stored plan against fresh protocol, declaration, and fixtures."""
    campaign_dir = Path(campaign_dir).resolve()
    declaration = tomllib.loads((campaign_dir / "campaign.toml").read_text())
    validate_freeze_declaration(declaration)
    relative = declaration["freeze"]["primary_plan"]
    path = _campaign_source_path(campaign_dir, relative, kind="primary plan")
    stored = load_plan(path)
    expected = build_full_plan(campaign_dir)
    if stored.to_dict() != expected.to_dict():
        raise RunIntegrityError("stored primary plan does not match the exact frozen 240-response design")
    return stored


def _outside_sensitive_roots(path: Path) -> Path:
    resolved = path.resolve()
    home = Path.home().resolve()
    repo = ROOT.resolve()
    if resolved == home or home in resolved.parents:
        raise RunIntegrityError(f"trial workspace must be outside HOME: {resolved}")
    if resolved == repo or repo in resolved.parents:
        raise RunIntegrityError(f"trial workspace must be outside the repository: {resolved}")
    return resolved


def materialize_fixture(
    case: TrialCase, workspace_root: Path, *, workspace_name: str | None = None
) -> Path:
    """Copy a seed and assigned CLAUDE.md into one fresh isolated workspace."""
    root = _outside_sensitive_roots(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise RunIntegrityError("workspace root may not be a symbolic link")
    campaign_dir = case._campaign_dir
    if campaign_dir is None:
        raise RunIntegrityError("trial case is detached from its campaign source")
    fixture_dir = _campaign_source_path(campaign_dir, case.fixture_path, kind="fixture")
    if fixture_tree_sha256(fixture_dir) != case.fixture_sha256:
        raise RunIntegrityError(f"fixture changed before materialization: {case.fixture_id}")
    arm_path = _campaign_source_path(campaign_dir, case.arm_path, kind="arm")
    if _file_sha256(arm_path) != case.arm_sha256:
        raise RunIntegrityError(f"arm changed before materialization: {case.arm}")
    name = workspace_name or case.trial_id
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise RunIntegrityError(f"unsafe workspace name: {name!r}")
    workspace = root / name
    if workspace.exists():
        raise RunIntegrityError(f"trial workspace is never reused: {workspace}")
    shutil.copytree(fixture_dir / "seed", workspace, symlinks=False)
    (workspace / "CLAUDE.md").write_bytes(arm_path.read_bytes())
    return workspace


class TrialStore:
    """One immutable plan plus separately committed trial and attempt files."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.plan_path = self.root / "plan.json"
        self.trials_dir = self.root / "trials"
        self.attempts_dir = self.root / "attempts"
        self.locks_dir = self.root / ".locks"

    @staticmethod
    def _atomic_create(path: Path, value: Mapping) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        if path.exists():
            if path.read_text() != payload:
                raise RunIntegrityError(f"immutable artifact already differs: {path}")
            return
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, path)
            except FileExistsError:
                if path.read_text() != payload:
                    raise RunIntegrityError(f"concurrent immutable write differs: {path}")
        finally:
            temp_path.unlink(missing_ok=True)

    def write_plan(self, plan: RunPlan) -> Path:
        plan.verify_integrity()
        self._atomic_create(self.plan_path, plan.to_dict())
        return self.plan_path

    def load_plan(self) -> RunPlan:
        return load_plan(self.plan_path)

    def trial_path(self, trial_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", trial_id):
            raise RunIntegrityError(f"unsafe trial id: {trial_id!r}")
        return self.trials_dir / f"{trial_id}.json"

    def attempt_path(
        self, trial_id: str, authorization_sha256: str, state: str, attempt_ordinal: int = 1
    ) -> Path:
        if state not in {"prepared", "dispatched", "returned"}:
            raise RunIntegrityError(f"unknown attempt state: {state}")
        if not isinstance(attempt_ordinal, int) or attempt_ordinal < 1:
            raise RunIntegrityError("attempt ordinal must be positive")
        return (
            self.attempts_dir / trial_id /
            f"{authorization_sha256}.{attempt_ordinal:03d}.{state}.json"
        )

    def dispatched_attempts(self, trial_id: str, authorization_sha256: str) -> tuple[Path, ...]:
        directory = self.attempts_dir / trial_id
        return tuple(sorted(directory.glob(f"{authorization_sha256}.*.dispatched.json")))

    def write_attempt(
        self, *, plan: RunPlan, case: TrialCase, authorization: PaidAuthorizationEvidence,
        state: str, workspace: Path, attempt_ordinal: int = 1,
    ) -> Path:
        value = {
            "schema": ATTEMPT_SCHEMA,
            "state": state,
            "trial_id": case.trial_id,
            "case_sha256": case.case_sha256,
            "plan_sha256": plan.plan_sha256,
            "authorization": authorization.to_dict(),
            "attempt_ordinal": attempt_ordinal,
            "workspace_sha256": _sha256(str(workspace).encode("utf-8")),
        }
        value["attempt_sha256"] = _sha256(_canonical_bytes(value))
        path = self.attempt_path(
            case.trial_id, authorization.sha256, state, attempt_ordinal
        )
        self._atomic_create(path, value)
        return path

    def commit_trial(self, trial: TrialResult) -> Path:
        path = self.trial_path(trial.trial_id)
        self._atomic_create(path, trial.to_dict())
        return path

    @contextmanager
    def trial_ownership(self, trial_id: str):
        """Serialize only writers for one trial; independent trials never contend."""
        self.trial_path(trial_id)
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.locks_dir / f"{trial_id}.lock"
        with lock_path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load_trial(self, trial_id: str, *, plan: RunPlan) -> TrialResult:
        plan.verify_integrity()
        return _validate_artifact(json.loads(self.trial_path(trial_id).read_text()), plan=plan)


def validate_authorization(
    plan: RunPlan,
    authorization: PaidAuthorizationEvidence,
    *,
    authorized_trial_ids: Sequence[str] | None = None,
    trial_id: str | None = None,
) -> None:
    if authorization.present is not True:
        raise AuthorizationMismatchError("paid authorization is absent")
    if authorization.plan_sha256 != plan.plan_sha256:
        raise AuthorizationMismatchError("paid authorization belongs to another plan")
    if not 1 <= authorization.authorized_trial_count <= len(plan.trials):
        raise AuthorizationMismatchError("paid authorization count is outside the plan")
    if (
        not isinstance(authorization.sha256, str)
        or not HEX_SHA256.fullmatch(authorization.sha256)
        or isinstance(authorization.byte_count, bool)
        or not isinstance(authorization.byte_count, int)
        or authorization.byte_count <= 0
        or isinstance(authorization.authorized_trial_count, bool)
        or not isinstance(authorization.authorized_trial_count, int)
        or not isinstance(authorization.authorized_trial_ids_sha256, str)
        or not HEX_SHA256.fullmatch(authorization.authorized_trial_ids_sha256)
    ):
        raise AuthorizationMismatchError("paid authorization evidence is malformed")
    if authorized_trial_ids is not None:
        ids = list(authorized_trial_ids)
        planned = {case.trial_id for case in plan.trials}
        if len(ids) != len(set(ids)) or any(item not in planned for item in ids):
            raise AuthorizationMismatchError("paid authorization selects unknown or duplicate trials")
        if authorization.authorized_trial_count != len(ids):
            raise AuthorizationMismatchError("paid authorization count differs from selected trials")
        if authorization.authorized_trial_ids_sha256 != globals()["authorized_trial_ids_sha256"](ids):
            raise AuthorizationMismatchError("paid authorization hash differs from selected trials")
        if trial_id is not None and trial_id not in ids:
            raise AuthorizationMismatchError("trial is outside the authorized selection")


_validate_authorization = validate_authorization


def _base_artifact(
    *, plan: RunPlan, case: TrialCase, authorization: PaidAuthorizationEvidence,
    initial_sha256: str, final_sha256: str, trajectory: list[dict], capture: Mapping,
) -> dict:
    fixture_dir = _campaign_source_path(
        plan._campaign_dir, case.fixture_path, kind="fixture"
    )
    contract_path = _contained_source_path(
        fixture_dir, "fixture.json", kind="fixture contract"
    )
    contract = json.loads(contract_path.read_text())
    return {
        "schema": TRIAL_SCHEMA,
        "trial_id": case.trial_id,
        "case_sha256": case.case_sha256,
        "plan_sha256": plan.plan_sha256,
        "run_kind": case.run_kind.value,
        "adapter": case.adapter.value,
        "fixture_id": case.fixture_id,
        "stratum": case.stratum,
        "arm": case.arm,
        "repetition": case.repetition,
        "excluded_from_primary_analysis": case.excluded_from_primary_analysis,
        "fixture": {
            "path": case.fixture_path,
            "sha256": case.fixture_sha256,
            "contract": contract,
        },
        "authorization": authorization.to_dict(),
        "workspace": {"initial_sha256": initial_sha256, "final_sha256": final_sha256},
        "trajectory": trajectory,
        "capture": dict(capture),
    }


def _completed_artifact(
    base: dict, generated: GenerationResult, *, plan: RunPlan
) -> CompletedTrial:
    safe_response = capture_spine.REMINDER_SPAN.sub(
        "<withheld:system-reminder>", generated.response
    )
    safe_response = capture_spine.redact(safe_response)
    capture_problems = capture_spine.retention_problems(dict(generated.capture))
    if capture_problems:
        raise RunIntegrityError("capture record violates retention: " + "; ".join(capture_problems))
    value = {
        **base,
        "status": "completed",
        "response": safe_response,
        "response_sha256": _sha256(safe_response.encode("utf-8")),
        "response_redacted": safe_response != generated.response,
        "usage": dict(generated.usage),
    }
    value["artifact_sha256"] = _artifact_digest(value)
    result = _validate_artifact(value, plan=plan)
    assert isinstance(result, CompletedTrial)
    return result


def _failed_artifact(base: dict, failure: GenerationFailure, *, plan: RunPlan) -> FailedTrial:
    if not failure.code or not isinstance(failure.detail, str):
        raise RunIntegrityError("generation failure needs a code and detail")
    if len(failure.detail) > capture_spine.MAX_RECORD_STRING:
        raise RunIntegrityError("failure detail exceeds the durable-record limit")
    if capture_spine.redact(failure.detail) != failure.detail:
        raise RunIntegrityError("failure detail contains credential-shaped text")
    capture_problems = capture_spine.retention_problems(dict(failure.capture))
    if capture_problems:
        raise RunIntegrityError("capture record violates retention: " + "; ".join(capture_problems))
    value = {
        **base,
        "status": "failed",
        "failure": {"stage": "generation", "code": failure.code, "detail": failure.detail},
    }
    value["artifact_sha256"] = _artifact_digest(value)
    result = _validate_artifact(value, plan=plan)
    assert isinstance(result, FailedTrial)
    return result


def execute_trial(
    *,
    plan: RunPlan,
    trial_id: str,
    store: TrialStore,
    adapter: GenerationAdapter,
    authorization: PaidAuthorizationEvidence,
    authorized_trial_ids: Sequence[str] | None = None,
    workspace_root: Path,
    prepare_adapter: Callable[[GenerationAdapter, TrialCase, Path], GenerationAdapter] | None = None,
) -> TrialResult:
    """Execute or resume one trial without any shared manifest mutation."""
    plan.verify_integrity()
    selected = list(authorized_trial_ids) if authorized_trial_ids is not None else [
        case.trial_id for case in plan.trials
    ]
    validate_authorization(
        plan, authorization, authorized_trial_ids=selected, trial_id=trial_id
    )
    committed = store.trial_path(trial_id)
    if committed.is_file():
        return store.load_trial(trial_id, plan=plan)
    case = plan.trial(trial_id)
    adapter_kind = adapter.kind if isinstance(adapter.kind, AdapterKind) else AdapterKind(adapter.kind)
    if adapter_kind != case.adapter:
        raise RunIntegrityError(
            f"adapter {adapter_kind.value} cannot execute {case.adapter.value} trial"
        )
    with store.trial_ownership(trial_id):
        committed = store.trial_path(trial_id)
        if committed.is_file():
            return store.load_trial(trial_id, plan=plan)
        if store.dispatched_attempts(case.trial_id, authorization.sha256):
            raise AmbiguousDispatchError(
                f"trial {case.trial_id} was dispatched under this authorization without a commit; "
                "a new explicit authorization is required"
            )
        attempt_ordinal = 1
        while True:
            workspace_name = (
                f"{case.trial_id}-{authorization.sha256[:12]}-{attempt_ordinal:03d}"
            )
            workspace_path = _outside_sensitive_roots(workspace_root) / workspace_name
            prepared_path = store.attempt_path(
                case.trial_id, authorization.sha256, "prepared", attempt_ordinal
            )
            if not workspace_path.exists() and not prepared_path.exists():
                break
            attempt_ordinal += 1
        workspace = materialize_fixture(case, workspace_root, workspace_name=workspace_name)
        recorder = TrajectoryRecorder(workspace)
        initial = snapshot_tree(workspace).sha256
        store.write_attempt(
            plan=plan, case=case, authorization=authorization, state="prepared",
            workspace=workspace, attempt_ordinal=attempt_ordinal,
        )
        if prepare_adapter is not None:
            adapter = prepare_adapter(adapter, case, workspace)
            prepared_kind = (
                adapter.kind if isinstance(adapter.kind, AdapterKind) else AdapterKind(adapter.kind)
            )
            if prepared_kind != case.adapter:
                raise RunIntegrityError(
                    f"prepared adapter {prepared_kind.value} cannot execute {case.adapter.value} trial"
                )
        store.write_attempt(
            plan=plan, case=case, authorization=authorization, state="dispatched",
            workspace=workspace, attempt_ordinal=attempt_ordinal,
        )
        generated = adapter.generate(case, workspace, recorder)
        if isinstance(generated, GenerationFailure):
            try:
                trajectory = recorder.public_trajectory()
            except TrajectoryEvidenceError as exc:
                trajectory = recorder.diagnostic_trajectory()
                generated = GenerationFailure(
                    generated.code,
                    generated.detail,
                    {
                        **dict(generated.capture),
                        "trajectory_complete": False,
                        "trajectory_error_sha256": _sha256(str(exc).encode("utf-8")),
                    },
                )
        else:
            trajectory = recorder.public_trajectory()
        final = snapshot_tree(workspace).sha256
        capture = generated.capture
        base = _base_artifact(
            plan=plan,
            case=case,
            authorization=authorization,
            initial_sha256=initial,
            final_sha256=final,
            trajectory=trajectory,
            capture=capture,
        )
        if isinstance(generated, GenerationResult):
            result: TrialResult = _completed_artifact(base, generated, plan=plan)
        elif isinstance(generated, GenerationFailure):
            result = _failed_artifact(base, generated, plan=plan)
        else:
            raise RunIntegrityError("generation adapter returned an unknown result type")
        store.write_attempt(
            plan=plan, case=case, authorization=authorization, state="returned",
            workspace=workspace, attempt_ordinal=attempt_ordinal,
        )
        store.commit_trial(result)
        return result


def load_committed_trials(store: TrialStore, plan: RunPlan) -> tuple[TrialResult, ...]:
    """Derive run state from immutable trial files in canonical plan order."""
    results: list[TrialResult] = []
    for case in plan.trials:
        if store.trial_path(case.trial_id).is_file():
            results.append(store.load_trial(case.trial_id, plan=plan))
    return tuple(results)


def _validate_authorization_groups(
    results: Sequence[TrialResult], *, require_complete: bool
) -> None:
    groups: dict[tuple[object, ...], list[str]] = {}
    for result in results:
        authorization = result.artifact["authorization"]
        key = (
            authorization["sha256"],
            authorization["byte_count"],
            authorization["plan_sha256"],
            authorization["authorized_trial_count"],
            authorization["authorized_trial_ids_sha256"],
        )
        groups.setdefault(key, []).append(result.trial_id)
    for key, trial_ids in groups.items():
        expected_count = key[3]
        expected_hash = key[4]
        if len(trial_ids) > expected_count:
            raise AuthorizationMismatchError("authorization group exceeds its selected trial count")
        if len(trial_ids) != expected_count:
            if require_complete:
                raise AuthorizationMismatchError(
                    "authorization group is incomplete for subset verification"
                )
            continue
        if authorized_trial_ids_sha256(trial_ids) != expected_hash:
            raise AuthorizationMismatchError(
                "authorization group trial ids do not match the selected subset hash"
            )


def load_plan(path: Path) -> RunPlan:
    """Canonical strict loader for every consumer of an immutable plan."""
    path = Path(path)
    snapshots = path.parent / "snapshots"
    return RunPlan.from_dict(
        json.loads(path.read_text()),
        snapshot_dir=snapshots if snapshots.is_dir() else None,
    )


def load_trial_artifact(path: Path, plan: RunPlan) -> TrialResult:
    """Canonical strict loader for one committed trial capsule."""
    path = Path(path)
    trial_id = path.stem
    if path.name != f"{trial_id}.json":
        raise RunIntegrityError(f"trial artifact has an invalid filename: {path.name}")
    plan.trial(trial_id)
    return _validate_artifact(json.loads(path.read_text()), plan=plan)


def load_trial_artifacts(
    run_dir: Path, plan: RunPlan, *, require_all: bool = False
) -> tuple[TrialResult, ...]:
    """Load committed capsules in plan order, rejecting files outside the plan."""
    trials_dir = Path(run_dir) / "trials"
    paths = tuple(sorted(trials_dir.glob("*.json"))) if trials_dir.is_dir() else ()
    planned = {case.trial_id for case in plan.trials}
    unexpected = sorted(path.name for path in paths if path.stem not in planned)
    if unexpected:
        raise RunIntegrityError("unexpected trial artifacts: " + ", ".join(unexpected))
    by_id = {path.stem: load_trial_artifact(path, plan) for path in paths}
    if require_all:
        missing = [case.trial_id for case in plan.trials if case.trial_id not in by_id]
        if missing:
            raise RunIntegrityError("missing trial artifacts: " + ", ".join(missing))
    results = tuple(by_id[case.trial_id] for case in plan.trials if case.trial_id in by_id)
    _validate_authorization_groups(results, require_complete=True)
    return results


def trial_to_score_input(trial: CompletedTrial) -> dict:
    """Narrow completed capsules to the existing score_eval input contract."""
    artifact = trial.to_dict()
    if artifact.get("status") != "completed":
        raise RunIntegrityError("only completed trials can reach score_eval")
    return {
        "trial_id": artifact["trial_id"],
        "prompt_id": artifact["fixture_id"],
        "repetition": artifact["repetition"],
        "arm": artifact["arm"],
        "response": artifact["response"],
        "usage": artifact["usage"],
        "fixture": artifact["fixture"]["contract"],
        "trajectory": artifact["trajectory"],
    }
