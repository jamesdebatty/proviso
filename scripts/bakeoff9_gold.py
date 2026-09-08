#!/usr/bin/env python3
"""Content-addressed solo-owner reference workflow for Bakeoff 9."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import bakeoff9_judge as judge
import bakeoff9_pilot
import bakeoff9_run
import judge_eval


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
CORRECTED_RUN = "results/pilot-corrected-2026-08-27"
MEMBERSHIP_SCHEMA = "bakeoff9-owner-reference-membership/1"
OWNER_PACKET_SCHEMA = "bakeoff9-owner-pass-packet/1"
OWNER_DRAFT_SCHEMA = "bakeoff9-owner-pass-draft/1"
OWNER_PASS_SCHEMA = "bakeoff9-owner-pass/1"
REPEAT_PACKET_SCHEMA = "bakeoff9-owner-repeat-packet/1"
REPEAT_DRAFT_SCHEMA = "bakeoff9-owner-repeat-draft/1"
REPEAT_PASS_SCHEMA = "bakeoff9-owner-repeat/1"
ADJUDICATION_DRAFT_SCHEMA = "bakeoff9-owner-self-adjudication-draft/1"
ADJUDICATION_SCHEMA = "bakeoff9-owner-self-adjudication/1"
REPORT_SCHEMA = "bakeoff9-owner-intra-rater-report/1"
ARTIFACT_SCHEMA = "bakeoff9-owner-reference/1"
OWNER_ATTESTATION = "human-owner-treatment-blind-no-vendor-output"
REPEAT_ATTESTATION = "human-owner-treatment-blind-no-vendor-output-no-first-labels"
ADJUDICATION_ATTESTATION = "human-owner-self-adjudication-no-vendor-output"
HUMAN_ID = re.compile(r"human_[0-9a-f]{16}")
REPEAT_SEED = 20260828
REPEAT_GAP = timedelta(hours=72)
REPEAT_PER_COHORT = 5
# The classes the owner labels. `winner` is absent: the pair cohort was dropped
# on 2026-08-28, so no membership case carries it.
REFERENCE_CLASSES = judge.ANSWER_CLASSES + judge.ESCALATION_CLASSES
# Only these decide vendor admission and must therefore vary in the reference.
GATED_CLASSES = bakeoff9_run.FROZEN_REQUIRED_CLASSES


class GoldIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class GoldMembership:
    raw: Mapping
    cases: tuple[judge.JudgeCase, ...]

    @property
    def membership_sha256(self) -> str:
        return self.raw["membership_sha256"]

    @property
    def judge_membership_sha256(self) -> str:
        return self.raw["judge_membership_sha256"]


@dataclass(frozen=True)
class OwnerPass:
    raw: Mapping
    labels_by_case: Mapping[str, dict]

    @property
    def sha256(self) -> str:
        return self.raw["pass_sha256"]

    @property
    def owner_id(self) -> str:
        return self.raw["actor"]["id"]


@dataclass(frozen=True)
class OwnerRepeat:
    raw: Mapping
    labels_by_case: Mapping[str, dict]

    @property
    def sha256(self) -> str:
        return self.raw["repeat_sha256"]


@dataclass(frozen=True)
class SelfAdjudication:
    raw: Mapping
    labels_by_case: Mapping[str, dict]

    @property
    def sha256(self) -> str:
        return self.raw["adjudication_sha256"]


@dataclass(frozen=True)
class BoundGold:
    artifact_sha256: str
    gold_set: judge.GoldSet
    intra_rater_report: Mapping


@dataclass(frozen=True)
class GoldReadiness:
    ready: bool
    blockers: tuple[str, ...]
    membership_sha256: str | None = None
    artifact_sha256: str | None = None


def _canonical_bytes(value: object) -> bytes:
    return judge.canonical_json(value).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _self_hash(value: Mapping, field: str) -> str:
    return _sha256({key: item for key, item in value.items() if key != field})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise GoldIntegrityError("owner-reference timestamps must be UTC")
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GoldIntegrityError("owner-reference timestamp must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GoldIntegrityError("owner-reference timestamp is invalid") from exc
    if _timestamp(parsed) != value:
        raise GoldIntegrityError("owner-reference timestamp is not canonical")
    return parsed


def human_id(pseudonym: str) -> str:
    if not isinstance(pseudonym, str) or not pseudonym.strip():
        raise GoldIntegrityError("owner pseudonym must be non-empty")
    digest = hashlib.sha256(("bakeoff9-owner\0" + pseudonym).encode()).hexdigest()
    return "human_" + digest[:16]


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise GoldIntegrityError(f"owner-reference source is outside the repository: {path}") from exc


def _document(role: str, path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise GoldIntegrityError(f"owner-reference source is missing or symlinked: {path}")
    return {"role": role, "path": _repo_path(path), "sha256": _file_sha256(path)}


def _immutable_write(path: Path, value: Mapping) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        if path.read_text() != payload:
            raise GoldIntegrityError(f"immutable owner-reference artifact already differs: {path}")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            if path.read_text() != payload:
                raise GoldIntegrityError(f"concurrent owner-reference write differs: {path}")
    finally:
        temporary_path.unlink(missing_ok=True)




def _source(trial_path: Path, artifact: Mapping) -> dict:
    return {
        "source_id": "source_" + hashlib.sha256(
            (artifact["response_sha256"] + "\0" + artifact["trial_id"]).encode()
        ).hexdigest()[:16],
        "capsule_path": _repo_path(trial_path),
        "capsule_file_sha256": _file_sha256(trial_path),
        "capsule_artifact_sha256": artifact["artifact_sha256"],
        "response_sha256": artifact["response_sha256"],
        "response_pointer": "/response",
    }


def _member(case: judge.JudgeCase, origin: str, construction: str,
            sources: Sequence[dict], source_case_ids: Sequence[str] = ()) -> dict:
    return {
        "case": case.to_dict(),
        "case_sha256": case.sha256,
        "case_schema_sha256": judge.sha256_json(judge.case_schema(case)),
        "provenance": {
            "origin": origin,
            "construction": construction,
            "source_case_ids": list(source_case_ids),
            "sources": list(sources),
        },
    }


def _answer_case(artifact: Mapping) -> judge.JudgeCase:
    response_sha = artifact["response_sha256"]
    contract = artifact["fixture"]["contract"]
    oracle = contract.get("oracle") or {}
    required = (oracle["criterion"],) if oracle.get("criterion") else ()
    return judge.JudgeCase(
        judge.opaque_id("case", "owner-answer\0" + response_sha),
        judge.CaseKind.ANSWER, contract["prompt"], required, artifact["response"],
        claims=judge.claim_references(artifact["response"], response_sha),
        criteria=judge.criterion_references(contract, response_sha),
    )


def _escalation_case(artifact: Mapping, cause: str) -> judge.JudgeCase:
    return judge.escalation_case(
        artifact["fixture"]["contract"], artifact["response"],
        artifact["response_sha256"], cause, namespace="owner",
    )


def _corrected_sources(campaign_dir: Path) -> tuple[Path, tuple[tuple[Path, dict], ...], dict]:
    run_dir = campaign_dir / CORRECTED_RUN
    grades_path = run_dir / "mechanical-grades.json"
    plan = bakeoff9_run.load_plan(run_dir / "plan.json")
    paths = {path.stem: path for path in (run_dir / "trials").glob("*.json")}
    planned = {case.trial_id for case in plan.trials}
    if set(paths) != planned:
        raise GoldIntegrityError("corrected-pilot trial coverage differs from its plan")
    artifacts = tuple(
        bakeoff9_run.load_trial_artifact(paths[case.trial_id], plan) for case in plan.trials
    )
    if len(artifacts) != 20 or any(not isinstance(item, bakeoff9_run.CompletedTrial) for item in artifacts):
        raise GoldIntegrityError("owner reference requires 20 complete corrected-pilot trials")
    trial_values = tuple(
        (run_dir / "trials" / f"{item.trial_id}.json", item.to_dict()) for item in artifacts
    )
    built_cases = bakeoff9_pilot.build_blind_cases(run_dir, grades_path)
    stored_cases = json.loads((run_dir / "pilot-blind-cases.json").read_text())
    if built_cases != stored_cases:
        raise GoldIntegrityError("stored pilot blind cases differ from corrected evidence")
    human = json.loads((run_dir / "pilot-human-adjudication.json").read_text())
    built_summary = bakeoff9_pilot.summarize_pilot(run_dir, grades_path, stored_cases, human)
    if built_summary != json.loads((run_dir / "pilot-summary-human-reviewed.json").read_text()):
        raise GoldIntegrityError("stored human-reviewed pilot summary differs from corrected evidence")
    return run_dir, trial_values, stored_cases


def _judge_rubric() -> str:
    return judge_eval.judge_system_prompt((ROOT / "grader" / "rubric.md").read_text())


def _cohort(case: judge.JudgeCase) -> str:
    if case.kind is judge.CaseKind.ANSWER:
        return "answer"
    return case.class_names[0]


def _repeat_plan(cases: Sequence[judge.JudgeCase], basis_sha256: str) -> dict:
    cohorts = {
        name: [case for case in cases if _cohort(case) == name]
        for name in ("answer", *judge.ESCALATION_CLASSES)
    }
    selected = []
    by_cohort = {}
    for name, eligible in cohorts.items():
        ranked = sorted(
            eligible,
            key=lambda case: hashlib.sha256(
                f"bakeoff9-owner-repeat-v2\0{REPEAT_SEED}\0{basis_sha256}\0{name}\0{case.sha256}".encode()
            ).hexdigest(),
        )
        if len(ranked) < REPEAT_PER_COHORT:
            raise GoldIntegrityError(f"repeat cohort has fewer than five cases: {name}")
        chosen = ranked[:REPEAT_PER_COHORT]
        by_cohort[name] = [case.case_id for case in chosen]
        selected.extend(chosen)
    unique = {case.case_id: case for case in selected}
    aliases = [
        {
            "canonical_case_id": case_id,
            "repeat_case_id": judge.opaque_id("case", f"repeat\0{basis_sha256}\0{case_id}"),
        }
        for case_id in sorted(unique)
    ]
    presentation = sorted(
        (item["repeat_case_id"] for item in aliases),
        key=lambda value: hashlib.sha256(f"repeat-order\0{basis_sha256}\0{value}".encode()).hexdigest(),
    )
    base = {
        "strategy": "class-balanced-digest-rank-v2",
        "seed": REPEAT_SEED,
        "minimum_cases_per_cohort": REPEAT_PER_COHORT,
        "minimum_gap_seconds": int(REPEAT_GAP.total_seconds()),
        "selection_basis_sha256": basis_sha256,
        "cases_by_cohort": by_cohort,
        "aliases": aliases,
        "presentation_order": presentation,
    }
    return {**base, "repeat_plan_sha256": _sha256(base)}


def build_membership(campaign_dir: Path = DEFAULT_CAMPAIGN) -> GoldMembership:
    campaign_dir = Path(campaign_dir).resolve()
    run_dir, trial_values, blind = _corrected_sources(campaign_dir)
    blind_by_key = {(item["response_sha256"], item["class"]): item for item in blind["cases"]}
    ordered = tuple(sorted(trial_values, key=lambda item: item[1]["response_sha256"]))
    members = []
    for path, artifact in ordered:
        source = _source(path, artifact)
        members.append(_member(_answer_case(artifact), "primary", "pilot-answer", (source,)))
        claim = blind_by_key.get((artifact["response_sha256"], "claim_support"))
        if claim is None:
            raise GoldIntegrityError("corrected pilot lacks one claim-support case")
        members.append(_member(
            _escalation_case(artifact, "claim_support"), "primary", "pilot-claim-support",
            (source,), (claim["case_id"],),
        ))
        completion = blind_by_key.get((artifact["response_sha256"], "completion_word"))
        members.append(_member(
            _escalation_case(artifact, "completion_word"),
            "primary" if completion else "supplemental", "same-response-completion",
            (source,), () if completion is None else (completion["case_id"],),
        ))
        members.append(_member(
            _escalation_case(artifact, "invented_check"), "supplemental",
            "same-response-invented-check", (source,),
        ))
    members.sort(key=lambda item: item["case"]["case_id"])
    cases = tuple(judge.JudgeCase.from_dict(item["case"]) for item in members)
    counts = Counter(name for case in cases for name in case.class_names)
    if any(counts[name] < 5 for name in REFERENCE_CLASSES):
        raise GoldIntegrityError(f"owner-reference class coverage is insufficient: {counts}")
    documents = [
        _document("corrected-plan", run_dir / "plan.json"),
        _document("mechanical-grades", run_dir / "mechanical-grades.json"),
        _document("pilot-blind-cases", run_dir / "pilot-blind-cases.json"),
        _document("human-pilot-adjudication", run_dir / "pilot-human-adjudication.json"),
        _document("human-pilot-summary", run_dir / "pilot-summary-human-reviewed.json"),
        _document("label-instructions", campaign_dir / "gold" / "label-instructions.md"),
        _document("self-adjudication-instructions", campaign_dir / "gold" / "self-adjudication-instructions.md"),
        _document("judge-rubric", ROOT / "grader" / "rubric.md"),
    ]
    documents.extend(_document("trial-capsule", path) for path, _ in ordered)
    basis = {
        "campaign_id": "clause-bakeoff-9-2026-08-22",
        "judge_rubric_sha256": hashlib.sha256(_judge_rubric().encode()).hexdigest(),
        "judge_membership_sha256": judge.gold_membership_sha256(cases),
        "documents": sorted(documents, key=lambda item: (item["role"], item["path"])),
        "members": members,
    }
    basis_sha = _sha256(basis)
    base = {"schema": MEMBERSHIP_SCHEMA, **basis, "repeat_plan": _repeat_plan(cases, basis_sha)}
    raw = {**base, "membership_sha256": _sha256(base)}
    return GoldMembership(raw, cases)


def _freeze(campaign_dir: Path) -> dict:
    declaration = tomllib.loads((campaign_dir / "campaign.toml").read_text())
    bakeoff9_run.validate_freeze_declaration(declaration)
    return declaration["freeze"]


def membership_path(campaign_dir: Path) -> Path:
    return campaign_dir / _freeze(campaign_dir)["gold"]["membership_manifest"]


def artifact_path(campaign_dir: Path) -> Path:
    return campaign_dir / _freeze(campaign_dir)["gold"]["artifact"]


def validate_membership(campaign_dir: Path, raw: Mapping) -> GoldMembership:
    if not isinstance(raw, dict) or raw.get("schema") != MEMBERSHIP_SCHEMA:
        raise GoldIntegrityError("owner-reference membership has an invalid schema")
    if raw.get("membership_sha256") != _self_hash(raw, "membership_sha256"):
        raise GoldIntegrityError("owner-reference membership hash mismatch")
    expected = build_membership(campaign_dir)
    if raw != expected.raw:
        raise GoldIntegrityError("owner-reference membership differs from deterministic pilot evidence")
    return expected


def load_membership(campaign_dir: Path = DEFAULT_CAMPAIGN) -> GoldMembership:
    campaign_dir = Path(campaign_dir).resolve()
    path = membership_path(campaign_dir)
    if not path.is_file():
        raise GoldIntegrityError(f"owner-reference membership is missing: {path}")
    return validate_membership(campaign_dir, json.loads(path.read_text()))


def make_owner_packet(membership: GoldMembership, campaign_dir: Path = DEFAULT_CAMPAIGN) -> dict:
    campaign_dir = Path(campaign_dir).resolve()
    instructions = (campaign_dir / "gold" / "label-instructions.md").read_text()
    rubric = _judge_rubric()
    base = {
        "schema": OWNER_PACKET_SCHEMA,
        "campaign_id": membership.raw["campaign_id"],
        "membership_sha256": membership.membership_sha256,
        "instructions": instructions,
        "instructions_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
        "rubric": rubric,
        "rubric_sha256": hashlib.sha256(rubric.encode()).hexdigest(),
        "cases": [
            {"case": case.to_dict(), "case_sha256": case.sha256,
             "schema": judge.case_schema(case),
             "schema_sha256": judge.sha256_json(judge.case_schema(case))}
            for case in membership.cases
        ],
    }
    return {**base, "packet_sha256": _sha256(base)}


def _walk_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_owner_packet(raw: Mapping, membership: GoldMembership,
                          campaign_dir: Path = DEFAULT_CAMPAIGN) -> dict:
    expected = make_owner_packet(membership, campaign_dir)
    if raw != expected:
        raise GoldIntegrityError("owner packet differs from frozen membership")
    forbidden = {"provenance", "trial_id", "fixture_id", "stratum", "arm", "capsule_path"}
    if forbidden & set(_walk_keys(raw)):
        raise GoldIntegrityError("owner packet leaks treatment provenance")
    return expected


def make_owner_draft(membership: GoldMembership, packet: Mapping, owner_id: str,
                     now: datetime | None = None) -> dict:
    if not HUMAN_ID.fullmatch(owner_id):
        raise GoldIntegrityError("owner draft needs an opaque human id")
    return {
        "schema": OWNER_DRAFT_SCHEMA,
        "membership_sha256": membership.membership_sha256,
        "packet_sha256": packet["packet_sha256"],
        "actor": {"kind": "human", "id": owner_id},
        "attestation": OWNER_ATTESTATION,
        "opened_at": _timestamp(now or _utc_now()),
        "labels": [{"case_id": case.case_id, "labels": None}
                   for case in membership.cases],
    }


def _labels_by_case(entries: object, cases: Mapping[str, judge.JudgeCase]) -> dict[str, dict]:
    if not isinstance(entries, list):
        raise GoldIntegrityError("owner labels must be a list")
    by_case = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"case_id", "labels"}:
            raise GoldIntegrityError("owner label entry is invalid")
        case_id = item["case_id"]
        if case_id in by_case or case_id not in cases:
            raise GoldIntegrityError("owner labels contain duplicate or unknown case")
        judge.validate_case_labels(cases[case_id], item["labels"])
        by_case[case_id] = item["labels"]
    if set(by_case) != set(cases):
        raise GoldIntegrityError("owner label coverage is incomplete")
    return by_case


def finalize_owner_draft(raw: Mapping, membership: GoldMembership, packet: Mapping,
                         now: datetime | None = None) -> dict:
    if not isinstance(raw, dict) or raw.get("schema") != OWNER_DRAFT_SCHEMA:
        raise GoldIntegrityError("owner-pass draft has an invalid schema")
    opened = _parse_timestamp(raw.get("opened_at"))
    locked = now or _utc_now()
    if locked < opened:
        raise GoldIntegrityError("owner pass locked before it opened")
    base = {**raw, "schema": OWNER_PASS_SCHEMA, "locked_at": _timestamp(locked)}
    final = {**base, "pass_sha256": _sha256(base)}
    validate_owner_pass(final, membership, packet)
    return final


def validate_owner_pass(raw: Mapping, membership: GoldMembership, packet: Mapping) -> OwnerPass:
    expected = {"schema", "membership_sha256", "packet_sha256", "actor", "attestation",
                "opened_at", "locked_at", "labels", "pass_sha256"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema"] != OWNER_PASS_SCHEMA:
        raise GoldIntegrityError("owner pass has invalid fields or schema")
    if raw["pass_sha256"] != _self_hash(raw, "pass_sha256"):
        raise GoldIntegrityError("owner-pass hash mismatch")
    if raw["membership_sha256"] != membership.membership_sha256 or raw["packet_sha256"] != packet["packet_sha256"]:
        raise GoldIntegrityError("owner pass belongs to another membership or packet")
    actor = raw["actor"]
    if not isinstance(actor, dict) or set(actor) != {"kind", "id"} or actor["kind"] != "human" or not HUMAN_ID.fullmatch(actor["id"]):
        raise GoldIntegrityError("owner pass requires one opaque human owner")
    if raw["attestation"] != OWNER_ATTESTATION:
        raise GoldIntegrityError("owner pass lacks the human-only attestation")
    if _parse_timestamp(raw["locked_at"]) < _parse_timestamp(raw["opened_at"]):
        raise GoldIntegrityError("owner-pass timestamps are non-monotonic")
    cases = {case.case_id: case for case in membership.cases}
    return OwnerPass(raw, _labels_by_case(raw["labels"], cases))


def _alias_case(case: judge.JudgeCase, alias: str) -> judge.JudgeCase:
    value = case.to_dict()
    value["case_id"] = alias
    return judge.JudgeCase.from_dict(value)


def make_repeat_packet(membership: GoldMembership, owner: OwnerPass,
                       now: datetime | None = None) -> dict:
    opened = now or _utc_now()
    not_before = _parse_timestamp(owner.raw["locked_at"]) + REPEAT_GAP
    if opened < not_before:
        raise GoldIntegrityError(f"owner repeat is not available before {_timestamp(not_before)}")
    case_by_id = {case.case_id: case for case in membership.cases}
    alias_by_canonical = {
        item["canonical_case_id"]: item["repeat_case_id"]
        for item in membership.raw["repeat_plan"]["aliases"]
    }
    by_alias = {
        alias: _alias_case(case_by_id[canonical], alias)
        for canonical, alias in alias_by_canonical.items()
    }
    base = {
        "schema": REPEAT_PACKET_SCHEMA,
        "membership_sha256": membership.membership_sha256,
        "owner_pass_sha256": owner.sha256,
        "repeat_plan_sha256": membership.raw["repeat_plan"]["repeat_plan_sha256"],
        "owner_id": owner.owner_id,
        "not_before": _timestamp(not_before),
        "opened_at": _timestamp(opened),
        "cases": [
            {"case": by_alias[alias].to_dict(), "case_sha256": by_alias[alias].sha256,
             "schema": judge.case_schema(by_alias[alias]),
             "schema_sha256": judge.sha256_json(judge.case_schema(by_alias[alias]))}
            for alias in membership.raw["repeat_plan"]["presentation_order"]
        ],
    }
    return {**base, "packet_sha256": _sha256(base)}


def make_repeat_draft(membership: GoldMembership, owner: OwnerPass, packet: Mapping) -> dict:
    cases = tuple(judge.JudgeCase.from_dict(item["case"]) for item in packet["cases"])
    return {
        "schema": REPEAT_DRAFT_SCHEMA,
        "membership_sha256": membership.membership_sha256,
        "owner_pass_sha256": owner.sha256,
        "packet_sha256": packet["packet_sha256"],
        "actor": {"kind": "human", "id": owner.owner_id},
        "attestation": REPEAT_ATTESTATION,
        "labels": [{"case_id": case.case_id, "labels": None} for case in cases],
    }


def finalize_repeat_draft(raw: Mapping, membership: GoldMembership, owner: OwnerPass,
                          packet: Mapping, now: datetime | None = None) -> dict:
    if not isinstance(raw, dict) or raw.get("schema") != REPEAT_DRAFT_SCHEMA:
        raise GoldIntegrityError("owner-repeat draft has an invalid schema")
    locked = now or _utc_now()
    if locked < _parse_timestamp(packet["opened_at"]):
        raise GoldIntegrityError("owner repeat locked before release")
    base = {**raw, "schema": REPEAT_PASS_SCHEMA, "locked_at": _timestamp(locked)}
    final = {**base, "repeat_sha256": _sha256(base)}
    validate_repeat_pass(final, membership, owner, packet)
    return final


def validate_repeat_pass(raw: Mapping, membership: GoldMembership, owner: OwnerPass,
                         packet: Mapping) -> OwnerRepeat:
    expected = {"schema", "membership_sha256", "owner_pass_sha256", "packet_sha256",
                "actor", "attestation", "labels", "locked_at", "repeat_sha256"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema"] != REPEAT_PASS_SCHEMA:
        raise GoldIntegrityError("owner repeat has invalid fields or schema")
    if raw["repeat_sha256"] != _self_hash(raw, "repeat_sha256"):
        raise GoldIntegrityError("owner-repeat hash mismatch")
    if raw["membership_sha256"] != membership.membership_sha256 or raw["owner_pass_sha256"] != owner.sha256 or raw["packet_sha256"] != packet["packet_sha256"]:
        raise GoldIntegrityError("owner repeat belongs to another source")
    if raw["actor"] != {"kind": "human", "id": owner.owner_id} or raw["attestation"] != REPEAT_ATTESTATION:
        raise GoldIntegrityError("owner repeat must use the same human owner and blind attestation")
    not_before = _parse_timestamp(owner.raw["locked_at"]) + REPEAT_GAP
    if _parse_timestamp(packet["not_before"]) != not_before or _parse_timestamp(packet["opened_at"]) < not_before:
        raise GoldIntegrityError("owner repeat was released before the 72-hour gate")
    if _parse_timestamp(raw["locked_at"]) < _parse_timestamp(packet["opened_at"]):
        raise GoldIntegrityError("owner-repeat timestamps are non-monotonic")
    cases = {item["case"]["case_id"]: judge.JudgeCase.from_dict(item["case"]) for item in packet["cases"]}
    return OwnerRepeat(raw, _labels_by_case(raw["labels"], cases))


def _repeat_canonical_labels(membership: GoldMembership, repeat: OwnerRepeat) -> dict[str, dict]:
    alias = {item["repeat_case_id"]: item["canonical_case_id"] for item in membership.raw["repeat_plan"]["aliases"]}
    return {alias[case_id]: labels for case_id, labels in repeat.labels_by_case.items()}


def _disagreements(case: judge.JudgeCase, left: Mapping, right: Mapping) -> list[str]:
    return sorted(name for name in case.class_names
                  if judge.normalized_label(name, left[name]) != judge.normalized_label(name, right[name]))


def make_adjudication_draft(membership: GoldMembership, owner: OwnerPass,
                            repeat: OwnerRepeat) -> dict:
    repeat_labels = _repeat_canonical_labels(membership, repeat)
    cases = {case.case_id: case for case in membership.cases}
    return {
        "schema": ADJUDICATION_DRAFT_SCHEMA,
        "membership_sha256": membership.membership_sha256,
        "owner_pass_sha256": owner.sha256,
        "owner_repeat_sha256": repeat.sha256,
        "actor": {"kind": "human", "id": owner.owner_id},
        "attestation": ADJUDICATION_ATTESTATION,
        "resolutions": [
            {"case_id": case_id, "labels": owner.labels_by_case[case_id],
             "disagreements": _disagreements(cases[case_id], owner.labels_by_case[case_id], repeat_labels[case_id]),
             "rationale": ""}
            for case_id in sorted(repeat_labels)
        ],
    }


def finalize_adjudication_draft(raw: Mapping, membership: GoldMembership,
                                owner: OwnerPass, repeat: OwnerRepeat,
                                now: datetime | None = None) -> dict:
    if not isinstance(raw, dict) or raw.get("schema") != ADJUDICATION_DRAFT_SCHEMA:
        raise GoldIntegrityError("self-adjudication draft has an invalid schema")
    base = {**raw, "schema": ADJUDICATION_SCHEMA, "completed_at": _timestamp(now or _utc_now())}
    final = {**base, "adjudication_sha256": _sha256(base)}
    validate_adjudication(final, membership, owner, repeat)
    return final


def validate_adjudication(raw: Mapping, membership: GoldMembership,
                          owner: OwnerPass, repeat: OwnerRepeat) -> SelfAdjudication:
    expected = {"schema", "membership_sha256", "owner_pass_sha256", "owner_repeat_sha256",
                "actor", "attestation", "resolutions", "completed_at", "adjudication_sha256"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema"] != ADJUDICATION_SCHEMA:
        raise GoldIntegrityError("self-adjudication has invalid fields or schema")
    if raw["adjudication_sha256"] != _self_hash(raw, "adjudication_sha256"):
        raise GoldIntegrityError("self-adjudication hash mismatch")
    if raw["membership_sha256"] != membership.membership_sha256 or raw["owner_pass_sha256"] != owner.sha256 or raw["owner_repeat_sha256"] != repeat.sha256:
        raise GoldIntegrityError("self-adjudication belongs to another owner observation")
    if raw["actor"] != {"kind": "human", "id": owner.owner_id} or raw["attestation"] != ADJUDICATION_ATTESTATION:
        raise GoldIntegrityError("self-adjudication must use the same human owner")
    if _parse_timestamp(raw["completed_at"]) < _parse_timestamp(repeat.raw["locked_at"]):
        raise GoldIntegrityError("self-adjudication predates the repeat")
    repeat_labels = _repeat_canonical_labels(membership, repeat)
    cases = {case.case_id: case for case in membership.cases}
    by_case = {}
    for item in raw["resolutions"]:
        if not isinstance(item, dict) or set(item) != {"case_id", "labels", "disagreements", "rationale"}:
            raise GoldIntegrityError("self-adjudication resolution is invalid")
        case_id = item["case_id"]
        if case_id in by_case or case_id not in repeat_labels:
            raise GoldIntegrityError("self-adjudication has duplicate or unknown case")
        case = cases[case_id]
        judge.validate_case_labels(case, item["labels"])
        disagreements = _disagreements(case, owner.labels_by_case[case_id], repeat_labels[case_id])
        if item["disagreements"] != disagreements:
            raise GoldIntegrityError("self-adjudication disagreement record is inaccurate")
        if disagreements and (not isinstance(item["rationale"], str) or not item["rationale"].strip()):
            raise GoldIntegrityError("self-adjudication disagreements require rationale")
        by_case[case_id] = item["labels"] if disagreements else owner.labels_by_case[case_id]
    if set(by_case) != set(repeat_labels):
        raise GoldIntegrityError("self-adjudication coverage is incomplete")
    return SelfAdjudication(raw, by_case)


def intra_rater_report(membership: GoldMembership, owner: OwnerPass,
                       repeat: OwnerRepeat) -> dict:
    repeat_labels = _repeat_canonical_labels(membership, repeat)
    metrics = []
    for class_name in REFERENCE_CLASSES:
        cases = [case for case in membership.cases if case.case_id in repeat_labels and class_name in case.class_names]
        left = [judge.normalized_label(class_name, owner.labels_by_case[case.case_id][class_name]) for case in cases]
        right = [judge.normalized_label(class_name, repeat_labels[case.case_id][class_name]) for case in cases]
        agreement, kappa, reason = judge.cohen_kappa(left, right)
        confusion = Counter(zip(left, right))
        metrics.append({
            "class_name": class_name, "cases": len(cases),
            "agreements": sum(a == b for a, b in zip(left, right)),
            "exact_agreement": agreement, "cohen_kappa": kappa,
            "undefined_reason": reason,
            "confusion": [[a, b, count] for (a, b), count in sorted(confusion.items())],
        })
    if any(item["cases"] < 5 for item in metrics):
        raise GoldIntegrityError("intra-rater report has insufficient class coverage")
    base = {
        "schema": REPORT_SCHEMA,
        "owner_pass_sha256": owner.sha256,
        "owner_repeat_sha256": repeat.sha256,
        "repeat_plan_sha256": membership.raw["repeat_plan"]["repeat_plan_sha256"],
        "metrics": metrics,
        "limitations": [
            "One owner is not independent human consensus.",
            "Five repeats per class produce noisy and sometimes undefined kappa.",
            "Local UTC timestamps are not an external trusted time source.",
        ],
    }
    return {**base, "report_sha256": _sha256(base)}


def assemble(membership: GoldMembership, owner_packet: Mapping, owner: OwnerPass,
             repeat_packet: Mapping, repeat: OwnerRepeat,
             adjudication: SelfAdjudication, campaign_dir: Path = DEFAULT_CAMPAIGN) -> dict:
    instructions = (Path(campaign_dir) / "gold" / "self-adjudication-instructions.md").read_text()
    report = intra_rater_report(membership, owner, repeat)
    base = {
        "schema": ARTIFACT_SCHEMA,
        "membership": dict(membership.raw), "owner_packet": dict(owner_packet),
        "owner_pass": dict(owner.raw), "repeat_packet": dict(repeat_packet),
        "owner_repeat": dict(repeat.raw),
        "self_adjudication_instructions": instructions,
        "self_adjudication_instructions_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
        "self_adjudication": dict(adjudication.raw), "intra_rater_report": report,
    }
    return {**base, "artifact_sha256": _sha256(base)}


def validate_artifact(campaign_dir: Path, raw: Mapping,
                      now: datetime | None = None) -> BoundGold:
    expected = {"schema", "membership", "owner_packet", "owner_pass", "repeat_packet",
                "owner_repeat", "self_adjudication_instructions",
                "self_adjudication_instructions_sha256", "self_adjudication",
                "intra_rater_report", "artifact_sha256"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema"] != ARTIFACT_SCHEMA:
        raise GoldIntegrityError("owner-reference artifact has invalid fields or schema")
    if raw["artifact_sha256"] != _self_hash(raw, "artifact_sha256"):
        raise GoldIntegrityError("owner-reference artifact hash mismatch")
    membership = validate_membership(campaign_dir, raw["membership"])
    packet = validate_owner_packet(raw["owner_packet"], membership, campaign_dir)
    owner = validate_owner_pass(raw["owner_pass"], membership, packet)
    expected_repeat = make_repeat_packet(membership, owner, _parse_timestamp(raw["repeat_packet"]["opened_at"]))
    if raw["repeat_packet"] != expected_repeat:
        raise GoldIntegrityError("owner repeat packet differs from frozen selection or timing")
    repeat = validate_repeat_pass(raw["owner_repeat"], membership, owner, expected_repeat)
    observed_now = now or _utc_now()
    if any(_parse_timestamp(value) > observed_now for value in (
        owner.raw["locked_at"], raw["repeat_packet"]["opened_at"],
        repeat.raw["locked_at"], raw["self_adjudication"]["completed_at"],
    )):
        raise GoldIntegrityError("owner-reference artifact contains a future observation")
    instructions = (Path(campaign_dir) / "gold" / "self-adjudication-instructions.md").read_text()
    if raw["self_adjudication_instructions"] != instructions or raw["self_adjudication_instructions_sha256"] != hashlib.sha256(instructions.encode()).hexdigest():
        raise GoldIntegrityError("self-adjudication instructions changed")
    adjudication = validate_adjudication(raw["self_adjudication"], membership, owner, repeat)
    report = intra_rater_report(membership, owner, repeat)
    if raw["intra_rater_report"] != report:
        raise GoldIntegrityError("intra-rater report does not recompute from originals")
    final_labels = dict(owner.labels_by_case)
    final_labels.update(adjudication.labels_by_case)
    for class_name in GATED_CLASSES:
        values = {judge.normalized_label(class_name, final_labels[case.case_id][class_name])
                  for case in membership.cases if class_name in case.class_names}
        if len(values) < 2:
            raise GoldIntegrityError(f"owner-reference gated class is degenerate: {class_name}")
    gold_set = judge.make_gold_set(membership.cases, final_labels, raw["artifact_sha256"])
    return BoundGold(raw["artifact_sha256"], gold_set, report)


class GoldRepository:
    def __init__(self, campaign_dir: Path):
        self.campaign_dir = Path(campaign_dir).resolve()

    @classmethod
    def open(cls, campaign_dir: Path = DEFAULT_CAMPAIGN) -> "GoldRepository":
        return cls(campaign_dir)

    def readiness(self) -> GoldReadiness:
        membership_sha = None
        try:
            membership_sha = load_membership(self.campaign_dir).membership_sha256
            bound = self.load()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return GoldReadiness(False, (str(exc),), membership_sha, None)
        return GoldReadiness(True, (), membership_sha, bound.artifact_sha256)

    def load(self) -> BoundGold:
        path = artifact_path(self.campaign_dir)
        if not path.is_file():
            raise GoldIntegrityError(f"owner reference is missing: {path}")
        return validate_artifact(self.campaign_dir, json.loads(path.read_text()))


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise GoldIntegrityError(f"JSON artifact must be an object: {path}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("membership", "packet"):
        item = commands.add_parser(name)
        item.add_argument("--out", type=Path)
    commands.add_parser("status")
    commands.add_parser("check")
    identity = commands.add_parser("human-id")
    identity.add_argument("pseudonym")
    owner_draft = commands.add_parser("owner-draft")
    owner_draft.add_argument("--actor", required=True)
    owner_draft.add_argument("--out", type=Path, required=True)
    owner_finalize = commands.add_parser("finalize-owner")
    owner_finalize.add_argument("path", type=Path)
    owner_finalize.add_argument("--out", type=Path, required=True)
    repeat_packet = commands.add_parser("repeat-packet")
    repeat_packet.add_argument("--owner", type=Path, required=True)
    repeat_packet.add_argument("--out", type=Path, required=True)
    repeat_draft = commands.add_parser("repeat-draft")
    repeat_draft.add_argument("--owner", type=Path, required=True)
    repeat_draft.add_argument("--repeat-packet", type=Path, required=True)
    repeat_draft.add_argument("--out", type=Path, required=True)
    repeat_finalize = commands.add_parser("finalize-repeat")
    repeat_finalize.add_argument("path", type=Path)
    repeat_finalize.add_argument("--owner", type=Path, required=True)
    repeat_finalize.add_argument("--repeat-packet", type=Path, required=True)
    repeat_finalize.add_argument("--out", type=Path, required=True)
    adjudication_draft = commands.add_parser("adjudication-draft")
    adjudication_draft.add_argument("--owner", type=Path, required=True)
    adjudication_draft.add_argument("--repeat-packet", type=Path, required=True)
    adjudication_draft.add_argument("--repeat", type=Path, required=True)
    adjudication_draft.add_argument("--out", type=Path, required=True)
    adjudication_finalize = commands.add_parser("finalize-adjudication")
    adjudication_finalize.add_argument("path", type=Path)
    adjudication_finalize.add_argument("--owner", type=Path, required=True)
    adjudication_finalize.add_argument("--repeat-packet", type=Path, required=True)
    adjudication_finalize.add_argument("--repeat", type=Path, required=True)
    adjudication_finalize.add_argument("--out", type=Path, required=True)
    assembly = commands.add_parser("assemble")
    for name in ("owner", "repeat-packet", "repeat", "adjudication"):
        assembly.add_argument("--" + name, type=Path, required=True)
    assembly.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    campaign = args.campaign.resolve()
    if args.command == "human-id":
        print(human_id(args.pseudonym))
        return 0
    if args.command == "membership":
        membership = build_membership(campaign)
        out = args.out or membership_path(campaign)
        _immutable_write(out, membership.raw)
        print(json.dumps({"path": str(out), "membership_sha256": membership.membership_sha256,
                          "cases": len(membership.cases)}, indent=2))
        return 0
    membership = load_membership(campaign)
    packet = make_owner_packet(membership, campaign)
    if args.command == "packet":
        out = args.out or campaign / "gold" / "owner-pass-packet.json"
        _immutable_write(out, packet)
        print(json.dumps({"path": str(out), "packet_sha256": packet["packet_sha256"]}, indent=2))
        return 0
    if args.command in {"status", "check"}:
        status = GoldRepository.open(campaign).readiness()
        print(json.dumps(status.__dict__, indent=2))
        return 0 if args.command == "status" or status.ready else 2
    if args.command == "owner-draft":
        _immutable_write(args.out, make_owner_draft(membership, packet, args.actor))
        print(args.out)
        return 0
    if args.command == "finalize-owner":
        final = finalize_owner_draft(_read_json(args.path), membership, packet)
        _immutable_write(args.out, final)
        print(final["pass_sha256"])
        return 0
    owner = validate_owner_pass(_read_json(args.owner), membership, packet)
    if args.command == "repeat-packet":
        repeat_packet = make_repeat_packet(membership, owner)
        _immutable_write(args.out, repeat_packet)
        print(repeat_packet["packet_sha256"])
        return 0
    repeat_packet = _read_json(args.repeat_packet)
    if args.command == "repeat-draft":
        expected = make_repeat_packet(membership, owner, _parse_timestamp(repeat_packet["opened_at"]))
        if repeat_packet != expected:
            raise GoldIntegrityError("repeat packet is invalid")
        _immutable_write(args.out, make_repeat_draft(membership, owner, repeat_packet))
        print(args.out)
        return 0
    if args.command == "finalize-repeat":
        final = finalize_repeat_draft(_read_json(args.path), membership, owner, repeat_packet)
        _immutable_write(args.out, final)
        print(final["repeat_sha256"])
        return 0
    repeat = validate_repeat_pass(_read_json(args.repeat), membership, owner, repeat_packet)
    if args.command == "adjudication-draft":
        _immutable_write(args.out, make_adjudication_draft(membership, owner, repeat))
        print(args.out)
        return 0
    if args.command == "finalize-adjudication":
        final = finalize_adjudication_draft(_read_json(args.path), membership, owner, repeat)
        _immutable_write(args.out, final)
        print(final["adjudication_sha256"])
        return 0
    adjudication = validate_adjudication(_read_json(args.adjudication), membership, owner, repeat)
    artifact = assemble(membership, packet, owner, repeat_packet, repeat, adjudication, campaign)
    out = args.out or artifact_path(campaign)
    _immutable_write(out, artifact)
    validate_artifact(campaign, artifact)
    print(json.dumps({"path": str(out), "artifact_sha256": artifact["artifact_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
