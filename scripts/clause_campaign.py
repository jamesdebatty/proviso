#!/usr/bin/env python3
"""Declare and exercise a clause campaign without a campaign-specific runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from capture_spine import REMINDER_SPAN, REMINDER_TAG, is_auth_shaped_key, redact
from harness_common import isolated_environment, parse_stream_json, text_output
from prose_density import measure as measure_density

SCHEMA = "clause-campaign/1"
PLAN_SCHEMA = "clause-plan/1"
TRIAL_SCHEMA = "clause-trial/1"
GRADES_SCHEMA = "clause-grades/1"
JUDGMENTS_SCHEMA = "clause-judgments/1"
SUMMARY_SCHEMA = "clause-summary/1"
SYNTHETIC_ADAPTER = "synthetic/1"
# One isolated, tool-less, single-turn Claude Code print-mode session per trial
# on a pinned binary copy. Dispatch needs a per-run authorization file naming
# the plan hash; nothing in this module can write that file. Frozen since
# bakeoff 10 (2026-09-02): its command line, generation record, and summary
# label (including the `synthetic-integration-only` mislabel, T-024) must
# stay byte-identical so that sealed run keeps re-verifying.
LIVE_ADAPTER = "claude-code/1"
# Tool-enabled successor (bakeoff 11): the same spine with a declared tool
# surface passed through --tools, edits auto-accepted inside the workspace,
# Bash allowed only through the declared rules, the permitted interpreter
# wrapped in a sandbox-exec shim, an allow-listed child environment, reminder
# spans withheld from the retained stream and counted, and a hidden oracle run
# in the workspace after the session ends.
AGENTIC_ADAPTER = "claude-code/2"
LIVE_ADAPTERS = (LIVE_ADAPTER, AGENTIC_ADAPTER)
AGENTIC_TOOLS = ("Bash", "Edit", "Glob", "Grep", "Read", "Write")
AGENTIC_PERMISSION_MODES = ("acceptEdits", "dontAsk")
ALLOWED_TOOL_RULE = re.compile(r"^[A-Za-z]+(?:\(.+\))?$")
REMINDER_PLACEHOLDER = "<withheld:system-reminder>"
TAIL_CHARS = 1500
SCAN_MODULE = Path(__file__).with_name("final_message_scan.py")
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
REPO_ROOT = Path(__file__).resolve().parents[1]
# The child environment is built from this allow-list, never by removing
# names from the shell: a dispatching shell carries session tokens and
# sockets whose names nobody enumerated in advance (bakeoff 9's list).
CHILD_ENV_ALLOWLIST = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
                       "TZ", "TMPDIR")
CHILD_ENV_FIXED = {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_AUTOUPDATER": "1",
}
ABSOLUTE_PATH_TOKEN = re.compile(r"(?<![\w/.:-])(?:~(?=/|$)|/(?!/))[^\s'\"`;|&()<>]*")
AUTHORIZATION_SCHEMA = "clause-run-authorization/1"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
AUTH_FAILURE_MARKERS = (
    "authentication failed", "failed to authenticate", "not authenticated", "not logged in",
    "please run /login", "unauthorized", "invalid api key", "invalid oauth", "invalid bearer",
    '"api_error_status":401',
)
# Credential and routing variables never reach the pinned binary: the run bills
# the subscription login the binary holds, and a key or base URL in the
# dispatching shell must not silently change who pays or where calls go.
STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "CLAUDE_CODE_OAUTH_TOKEN")
# Harness-class failures (authentication, model, version, environment, error)
# stop the run past this fraction of planned trials; a trial that ran out of
# time or budget is a censoring record ("timeout", "budget") counted apart,
# with its own ceiling. Both kinds are retried by a rerun.
FAILURE_STOP_FRACTION = 0.10
RUNAWAY_KINDS = ("timeout", "budget")
RUNAWAY_STOP_FRACTION = 0.25
# Threshold graders over scripts/prose_density.py fields: grader -> field.
DENSITY_GRADERS = {
    "max_mean_sentence_words": "mean_sentence_words",
    "max_mean_paragraph_words": "mean_paragraph_words",
}
ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
TRIAL_ID = re.compile(r"^[a-z][a-z0-9-]*--[a-z][a-z0-9-]*--r[0-9]{3}--[0-9a-f]{12}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    return _digest_bytes(_canonical(value))


def _file_digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


#: Unmistakable credential shapes. Model prose from a tool-less trial whose
#: inputs carry no credential cannot leak one, but it routinely says things
#: like "authorization decisions" or "the password reset flow", which the
#: full sanitizer rewrites. Response text is therefore scanned with these
#: shapes only; every other field keeps the full sanitizer.
STRICT_CREDENTIAL_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._\-/+=]{16,}", re.I),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
RESPONSE_TEXT_PATHS = ("/output/text", "/response")


def _strict_credential_hit(text: str) -> bool:
    return any(pattern.search(text) for pattern in STRICT_CREDENTIAL_PATTERNS)


def _safety_problems(value: object, path: str = "") -> list[str]:
    problems: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            where = f"{path}/{key}"
            if is_auth_shaped_key(key) and isinstance(item, str):
                problems.append(f"{where}: authorization-shaped key carries a value")
            problems.extend(_safety_problems(item, where))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            problems.extend(_safety_problems(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        if "<system-reminder>" in value.lower():
            problems.append(f"{path}: carries a <system-reminder> payload")
        if path.endswith(RESPONSE_TEXT_PATHS):
            if _strict_credential_hit(value):
                problems.append(f"{path}: carries a credential")
        elif redact(value) != value:
            problems.append(f"{path}: carries credential-shaped text")
    return problems


def _ensure_safe(value: object, label: str) -> None:
    problems = _safety_problems(value)
    if problems:
        raise ValueError(f"{label} violates the durable-data policy: {'; '.join(problems)}")


def _seal(value: dict, field: str) -> dict:
    sealed = dict(value)
    sealed[field] = _digest(value)
    return sealed


def _verify_seal(value: dict, field: str, label: str) -> None:
    recorded = value.get(field)
    if not isinstance(recorded, str) or not SHA256.fullmatch(recorded):
        raise ValueError(f"{label}: missing or invalid {field}")
    body = dict(value)
    del body[field]
    if _digest(body) != recorded:
        raise ValueError(f"{label}: {field} does not match its content")


def _tree_digest(path: Path) -> str:
    entries = []
    for item in sorted(path.rglob("*"), key=lambda candidate: candidate.as_posix()):
        relative = item.relative_to(path).as_posix()
        if item.is_symlink():
            raise ValueError(f"symlink is not allowed in pinned tree: {relative}")
        if item.is_file():
            entries.append({"path": relative, "sha256": _file_digest(item)})
        elif not item.is_dir():
            raise ValueError(f"non-file entry is not allowed in pinned tree: {relative}")
    return _digest(entries)


def _require_mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a table")
    return value


def _require_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_id(value: object, label: str) -> str:
    identifier = _require_string(value, label)
    if not ID.fullmatch(identifier):
        raise ValueError(f"{label} must be a lowercase hyphenated identifier")
    return identifier


def _require_sha(value: object, label: str) -> str:
    digest = _require_string(value, label)
    if not SHA256.fullmatch(digest):
        raise ValueError(f"{label} must be a lowercase sha256")
    return digest


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _require_repetitions(value: object) -> int:
    repetitions = _require_positive_int(value, "campaign.repetitions")
    if repetitions > 999:
        raise ValueError("campaign.repetitions must not exceed 999")
    return repetitions


def _require_dispatch_seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 2**31 - 1:
        raise ValueError("campaign.dispatch_seed must be an integer from 0 to 2**31 - 1")
    return value


def _require_count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _require_positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError(f"{label} must be a positive number")
    return float(value)


def _exact_keys(value: dict, expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        raise ValueError(f"{label} is missing: {', '.join(missing)}")
    if extra:
        raise ValueError(f"{label} has unexpected keys: {', '.join(extra)}")


def _resolve_source(root: Path, relative: object, label: str, directory: bool) -> Path:
    text = _require_string(relative, label)
    supplied = Path(text)
    if supplied.is_absolute():
        raise ValueError(f"{label} must be relative to the campaign")
    current = root
    for part in supplied.parts:
        if part in ("", ".", ".."):
            raise ValueError(f"{label} contains an unsafe path component")
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")
    try:
        current.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the campaign directory") from exc
    if directory and not current.is_dir():
        raise ValueError(f"{label} is not a directory")
    if not directory and not current.is_file():
        raise ValueError(f"{label} is not a file")
    return current


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected a JSON object")
    return value


def _read_canonical(path: Path, label: str) -> dict:
    value = _read_json(path, label)
    if path.read_bytes() != _pretty(value):
        raise ValueError(f"{label}: bytes are not canonical")
    return value


def _write_immutable(path: Path, value: dict) -> None:
    _write_immutable_bytes(path, _pretty(value))


@dataclass(frozen=True)
class SourceRef:
    path: str
    sha256: str


@dataclass(frozen=True)
class Variant:
    """An arm's workspace `CLAUDE.md`; `claude_md` and `source` are None for an
    absent-file arm (`absent = true`), whose workspace must hold no CLAUDE.md
    at the start or the end of a trial (bakeoff 12's no-file baseline)."""
    id: str
    claude_md: SourceRef | None
    source: Path | None


@dataclass(frozen=True)
class Probe:
    id: str
    path: str
    tree_sha256: str
    prompt: str
    source: Path
    oracle: dict | None = None


@dataclass(frozen=True)
class ClauseCampaign:
    declaration: Path
    declaration_sha256: str
    campaign_id: str
    protocol: SourceRef
    repetitions: int
    execution: dict
    variants: tuple[Variant, ...]
    probes: tuple[Probe, ...]
    measures: tuple[dict, ...]
    dispatch_seed: int | None = None

    @classmethod
    def load(cls, declaration: Path) -> "ClauseCampaign":
        declaration = Path(declaration)
        if declaration.is_symlink() or not declaration.is_file():
            raise ValueError("campaign declaration must be a regular file")
        try:
            raw = tomllib.loads(declaration.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"cannot read campaign declaration: {exc}") from exc

        _exact_keys(raw, {"schema", "campaign", "execution", "variants", "probes", "measures"}, "declaration")
        if raw["schema"] != SCHEMA:
            raise ValueError(f"schema must be {SCHEMA}")
        root = declaration.parent

        campaign = _require_mapping(raw["campaign"], "campaign")
        _exact_keys(campaign, {"id", "protocol", "protocol_sha256", "repetitions"} | ({"dispatch_seed"} & set(campaign)),
                    "campaign")
        campaign_id = _require_id(campaign["id"], "campaign.id")
        protocol_path = _resolve_source(root, campaign["protocol"], "campaign.protocol", False)
        protocol_sha = _require_sha(campaign["protocol_sha256"], "campaign.protocol_sha256")
        if _file_digest(protocol_path) != protocol_sha:
            raise ValueError("campaign.protocol_sha256 does not match protocol")
        protocol = SourceRef(str(campaign["protocol"]), protocol_sha)
        repetitions = _require_repetitions(campaign["repetitions"])
        dispatch_seed = _require_dispatch_seed(campaign["dispatch_seed"]) if "dispatch_seed" in campaign else None

        execution = _load_execution(_require_mapping(raw["execution"], "execution"))

        variants: list[Variant] = []
        seen: set[str] = set()
        for index, item in enumerate(_require_list(raw["variants"], "variants")):
            table = _require_mapping(item, f"variants[{index}]")
            if "absent" in table:
                _exact_keys(table, {"id", "absent"}, f"variants[{index}]")
                if table["absent"] is not True:
                    raise ValueError(f"variants[{index}].absent must be true when present")
            else:
                _exact_keys(table, {"id", "claude_md", "sha256"}, f"variants[{index}]")
            identifier = _require_id(table["id"], f"variants[{index}].id")
            if identifier in seen:
                raise ValueError(f"duplicate variant id: {identifier}")
            seen.add(identifier)
            if "absent" in table:
                variants.append(Variant(identifier, None, None))
                continue
            source = _resolve_source(root, table["claude_md"], f"variants[{index}].claude_md", False)
            sha256 = _require_sha(table["sha256"], f"variants[{index}].sha256")
            if _file_digest(source) != sha256:
                raise ValueError(f"variant {identifier} sha256 does not match its file")
            variants.append(Variant(identifier, SourceRef(str(table["claude_md"]), sha256), source))
        if not variants:
            raise ValueError("variants must contain at least one entry")

        probes: list[Probe] = []
        seen.clear()
        for index, item in enumerate(_require_list(raw["probes"], "probes")):
            table = _require_mapping(item, f"probes[{index}]")
            _exact_keys(table, {"id", "path", "tree_sha256"}, f"probes[{index}]")
            identifier = _require_id(table["id"], f"probes[{index}].id")
            if identifier in seen:
                raise ValueError(f"duplicate probe id: {identifier}")
            seen.add(identifier)
            source = _resolve_source(root, table["path"], f"probes[{index}].path", True)
            sha256 = _require_sha(table["tree_sha256"], f"probes[{index}].tree_sha256")
            if _tree_digest(source) != sha256:
                raise ValueError(f"probe {identifier} tree_sha256 does not match its tree")
            fixture = _read_json(source / "fixture.json", f"probe {identifier} fixture")
            _exact_keys(fixture, {"prompt"} | ({"oracle"} & set(fixture)), f"probe {identifier} fixture")
            prompt = _require_string(fixture["prompt"], f"probe {identifier} prompt")
            seed = source / "seed"
            if not seed.is_dir() or seed.is_symlink():
                raise ValueError(f"probe {identifier} must contain a regular seed directory")
            if (seed / "CLAUDE.md").exists() or (seed / "CLAUDE.md").is_symlink():
                raise ValueError(f"probe {identifier} seed must not contain CLAUDE.md")
            oracle = _load_oracle(fixture.get("oracle"), source, f"probe {identifier}")
            _refuse_credential_shapes(seed, f"probe {identifier} seed")
            if oracle is not None:
                _refuse_credential_shapes(source / "oracle", f"probe {identifier} oracle")
            for variant in variants if execution["adapter"] == SYNTHETIC_ADAPTER else ():
                response = source / "synthetic" / f"{variant.id}.json"
                if response.is_symlink() or not response.is_file():
                    raise ValueError(f"probe {identifier} lacks synthetic response for {variant.id}")
                _validate_synthetic(
                    _read_canonical(response, f"synthetic response {identifier}/{variant.id}")
                )
            probes.append(Probe(identifier, str(table["path"]), sha256, prompt, source, oracle))
        if not probes:
            raise ValueError("probes must contain at least one entry")

        measures: list[dict] = []
        kinds: set[str] = set()
        seen.clear()
        for index, item in enumerate(_require_list(raw["measures"], "measures")):
            table = _require_mapping(item, f"measures[{index}]")
            identifier = _require_id(table.get("id"), f"measures[{index}].id")
            if identifier in seen:
                raise ValueError(f"duplicate measure id: {identifier}")
            seen.add(identifier)
            kind = table.get("kind")
            if kind == "deterministic":
                grader = table.get("grader")
                if grader == "contains":
                    _exact_keys(table, {"id", "kind", "grader", "needle"}, f"measures[{index}]")
                    measure = {"id": identifier, "kind": kind, "grader": grader,
                               "needle": _require_string(table["needle"], f"measures[{index}].needle")}
                elif grader == "max_words" or grader in DENSITY_GRADERS:
                    _exact_keys(table, {"id", "kind", "grader", "maximum"}, f"measures[{index}]")
                    measure = {"id": identifier, "kind": kind, "grader": grader,
                               "maximum": _require_positive_int(table["maximum"], f"measures[{index}].maximum")}
                elif grader in ("oracle_pass", "final_message_scan"):
                    if execution["adapter"] != AGENTIC_ADAPTER:
                        raise ValueError(f"measures[{index}].grader {grader} needs adapter {AGENTIC_ADAPTER}")
                    if grader == "oracle_pass":
                        _exact_keys(table, {"id", "kind", "grader"}, f"measures[{index}]")
                        if any(probe.oracle is None for probe in probes):
                            raise ValueError(f"measures[{index}]: every probe must declare an oracle")
                        measure = {"id": identifier, "kind": kind, "grader": grader}
                    else:
                        _exact_keys(table, {"id", "kind", "grader", "field", "maximum"}, f"measures[{index}]")
                        measure = {"id": identifier, "kind": kind, "grader": grader,
                                   "field": _scan_field(table["field"], f"measures[{index}].field"),
                                   "maximum": _require_count(table["maximum"], f"measures[{index}].maximum")}
                else:
                    raise ValueError(f"measures[{index}].grader is unsupported")
            elif kind == "judgmental":
                _exact_keys(table, {"id", "kind", "question", "rubric", "rubric_sha256"}, f"measures[{index}]")
                rubric_path = _resolve_source(root, table["rubric"], f"measures[{index}].rubric", False)
                rubric_sha = _require_sha(table["rubric_sha256"], f"measures[{index}].rubric_sha256")
                if _file_digest(rubric_path) != rubric_sha:
                    raise ValueError(f"measure {identifier} rubric_sha256 does not match its file")
                measure = {"id": identifier, "kind": kind,
                           "question": _require_string(table["question"], f"measures[{index}].question"),
                           "rubric": str(table["rubric"]), "rubric_sha256": rubric_sha,
                           "rubric_text": rubric_path.read_bytes().decode("utf-8")}
            else:
                raise ValueError(f"measures[{index}].kind must be deterministic or judgmental")
            kinds.add(kind)
            measures.append(measure)
        if kinds != {"deterministic", "judgmental"}:
            raise ValueError("measures must declare deterministic and judgmental boundaries")

        return cls(
            declaration.resolve(), _file_digest(declaration), campaign_id,
            protocol, repetitions, execution,
            tuple(sorted(variants, key=lambda item: item.id)),
            tuple(sorted(probes, key=lambda item: item.id)),
            tuple(sorted(measures, key=lambda item: item["id"])),
            dispatch_seed,
        )

    def plan(self) -> dict:
        self._assert_sources_current()
        cases = []
        synthetic = self.execution["adapter"] == SYNTHETIC_ADAPTER
        for variant in self.variants:
            for probe in self.probes:
                response_sha = (
                    _file_digest(probe.source / "synthetic" / f"{variant.id}.json")
                    if synthetic else None
                )
                for repetition in range(1, self.repetitions + 1):
                    body = {
                        "variant_id": variant.id,
                        "claude_md_sha256": variant.claude_md.sha256 if variant.claude_md else None,
                        "probe_id": probe.id,
                        "probe_tree_sha256": probe.tree_sha256,
                        "seed_tree_sha256": _tree_digest(probe.source / "seed"),
                        "prompt": probe.prompt,
                        "prompt_sha256": _digest_bytes(probe.prompt.encode("utf-8")),
                        "repetition": repetition,
                    }
                    if synthetic:
                        body["synthetic_response_sha256"] = response_sha
                    case_sha = _digest(body)
                    case = dict(body)
                    case["trial_id"] = f"{variant.id}--{probe.id}--r{repetition:03d}--{case_sha[:12]}"
                    cases.append(_seal(case, "case_sha256"))
        execution = {
            **self.execution,
            "harness_sha256": _file_digest(Path(__file__)),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
        if self.execution["adapter"] == AGENTIC_ADAPTER:
            if SCAN_MODULE.is_symlink() or not SCAN_MODULE.is_file():
                raise ValueError(f"{AGENTIC_ADAPTER} needs {SCAN_MODULE.name} beside the harness to seal scan_sha256")
            execution["scan_sha256"] = _file_digest(SCAN_MODULE)
        body = {
            "schema": PLAN_SCHEMA,
            "campaign_id": self.campaign_id,
            "declaration_sha256": self.declaration_sha256,
            "protocol": {"path": self.protocol.path, "sha256": self.protocol.sha256},
            "execution": execution,
            "measures": list(self.measures),
            "cases": cases,
        }
        if self.dispatch_seed is not None:
            body["dispatch_seed"] = self.dispatch_seed
        plan = _seal(body, "plan_sha256")
        _validate_plan(plan)
        return plan

    def _assert_sources_current(self) -> None:
        if _file_digest(self.declaration) != self.declaration_sha256:
            raise ValueError("campaign declaration changed after it was loaded")
        protocol = self.declaration.parent / self.protocol.path
        if _file_digest(protocol) != self.protocol.sha256:
            raise ValueError("campaign protocol changed after it was loaded")
        for variant in self.variants:
            if variant.source is None:
                continue
            if _file_digest(variant.source) != variant.claude_md.sha256:
                raise ValueError(f"variant {variant.id} changed after the campaign was loaded")
        for probe in self.probes:
            if _tree_digest(probe.source) != probe.tree_sha256:
                raise ValueError(f"probe {probe.id} changed after the campaign was loaded")
        for measure in self.measures:
            if measure["kind"] != "judgmental":
                continue
            rubric = self.declaration.parent / measure["rubric"]
            if _file_digest(rubric) != measure["rubric_sha256"]:
                raise ValueError(f"measure {measure['id']} rubric changed after load")

    def exercise(self, run_dir: Path, authorization: Path | None = None,
                 deadline_utc: str | datetime | None = None) -> dict:
        run_dir = Path(run_dir)
        if run_dir.exists() and (run_dir.is_symlink() or not run_dir.is_dir()):
            raise ValueError("run directory must be a regular directory")
        deadline = _parse_deadline(deadline_utc)
        run_dir.mkdir(parents=True, exist_ok=True)
        _assert_no_symlinks(run_dir)
        plan = self.plan()
        if self.execution["adapter"] in LIVE_ADAPTERS:
            # Checked before any artifact exists: an unauthorized plan leaves
            # the run directory as it was found.
            grant = _check_authorization(authorization, plan)
            _write_immutable(run_dir / "plan.json", plan)
            _write_immutable(run_dir / "authorization.json", grant)
            self._exercise_live(run_dir, plan, deadline)
        else:
            _write_immutable(run_dir / "plan.json", plan)
            self._exercise_synthetic(run_dir, plan)

        trials = _load_trials(run_dir, plan)
        grades, judgments = _grade_artifacts(plan, trials)
        _write_immutable(run_dir / "grades.json", grades)
        _write_immutable(run_dir / "judgments.json", judgments)
        summary = _make_summary(plan, trials, grades, judgments)
        _write_immutable(run_dir / "summary.json", summary)
        return self.verify(run_dir)

    def _exercise_synthetic(self, run_dir: Path, plan: dict) -> None:
        variants = {item.id: item for item in self.variants}
        probes = {item.id: item for item in self.probes}
        for case in plan["cases"]:
            trial_path = run_dir / "trials" / f"{case['trial_id']}.json"
            if trial_path.exists():
                _load_one_trial(trial_path, plan, case)
                continue
            variant = variants[case["variant_id"]]
            probe = probes[case["probe_id"]]
            with tempfile.TemporaryDirectory(prefix="clause-campaign-") as temporary:
                workspace = Path(temporary) / "workspace"
                shutil.copytree(probe.source / "seed", workspace)
                if _tree_digest(workspace) != case["seed_tree_sha256"]:
                    raise ValueError(f"workspace seed drift for {case['trial_id']}")
                _place_variant(variant, workspace, case)
                response_path = probe.source / "synthetic" / f"{variant.id}.json"
                if _file_digest(response_path) != case["synthetic_response_sha256"]:
                    raise ValueError(f"synthetic response drift for {case['trial_id']}")
                response = _execute_synthetic(response_path, case["trial_id"])
                trial = _make_trial(plan, case, response)
                _ensure_safe(trial, "trial")
                _write_immutable(trial_path, trial)

    def _exercise_live(self, run_dir: Path, plan: dict, deadline: datetime | None = None) -> None:
        execution = plan["execution"]
        binary = Path(execution["binary"]).expanduser()
        if _file_digest(binary) != execution["binary_sha256"]:
            raise ValueError("pinned binary changed since the campaign was loaded")
        variants = {item.id: item for item in self.variants}
        probes = {item.id: item for item in self.probes}
        pending = []
        for case in plan["cases"]:
            trial_path = run_dir / "trials" / f"{case['trial_id']}.json"
            if trial_path.exists():
                _load_one_trial(trial_path, plan, case)
            else:
                pending.append(case)
        if not pending:
            return
        if execution["adapter"] == AGENTIC_ADAPTER:
            recorded = {case["trial_id"] for case in plan["cases"]} - {case["trial_id"] for case in pending}
            pending = [case for case in dispatch_order(plan) if case["trial_id"] not in recorded]

        stop = threading.Event()
        state = {"failures": 0, "censored": 0, "stop_reason": None, "deadline_reached": False,
                 "undispatched": 0}
        lock = threading.Lock()
        planned = len(plan["cases"])

        def work(case: dict) -> None:
            if stop.is_set():
                with lock:
                    state["undispatched"] += 1
                return
            if deadline is not None and _now() >= deadline:
                with lock:
                    state["deadline_reached"] = True
                    state["undispatched"] += 1
                stop.set()
                return
            try:
                trial, raw = _run_live_trial(
                    binary, execution, case, variants[case["variant_id"]], probes[case["probe_id"]], plan
                )
            except LiveTrialError as exc:
                with lock:
                    _record_failure(run_dir, case, exc)
                    if exc.kind in RUNAWAY_KINDS:
                        state["censored"] += 1
                        if state["censored"] / planned > RUNAWAY_STOP_FRACTION:
                            state["stop_reason"] = f"timeout/budget fraction exceeded {RUNAWAY_STOP_FRACTION}"
                    else:
                        state["failures"] += 1
                        if exc.kind in ("authentication", "model", "version"):
                            state["stop_reason"] = f"{exc.kind}: {exc}"
                        elif state["failures"] / planned > FAILURE_STOP_FRACTION:
                            state["stop_reason"] = f"failure fraction exceeded {FAILURE_STOP_FRACTION}"
                    if state["stop_reason"]:
                        stop.set()
                return
            with lock:
                _write_immutable_bytes(run_dir / "trials" / f"{case['trial_id']}.stdout.jsonl", raw)
                _write_immutable(run_dir / "trials" / f"{case['trial_id']}.json", trial)

        with ThreadPoolExecutor(max_workers=execution["workers"]) as pool:
            list(pool.map(work, pending))
        if state["stop_reason"]:
            raise ValueError(f"run stopped: {state['stop_reason']}; rerun resumes recorded trials")
        unrecorded = state["failures"] + state["censored"]
        if state["deadline_reached"]:
            raise ValueError(
                f"deadline {deadline.isoformat(timespec='seconds')} reached; "
                f"{state['undispatched']} trial(s) not dispatched and {unrecorded} failed or censored; "
                "rerun resumes recorded trials"
            )
        if unrecorded:
            raise ValueError(
                f"{state['failures']} trial(s) failed and {state['censored']} timed out or exceeded budget; "
                "recorded under failures/; rerun to retry"
            )

    @classmethod
    def verify(cls, run_dir: Path) -> dict:
        run_dir = Path(run_dir)
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise ValueError("run directory must be a regular directory")
        plan = _read_canonical(run_dir / "plan.json", "plan")
        _validate_plan(plan)
        live = plan["execution"]["adapter"] in LIVE_ADAPTERS
        if plan["execution"]["adapter"] == AGENTIC_ADAPTER and (
            not SCAN_MODULE.is_file() or _file_digest(SCAN_MODULE) != plan["execution"]["scan_sha256"]
        ):
            raise ValueError(
                f"{SCAN_MODULE.name} differs from the sealed scan_sha256; scan grades cannot be rederived"
            )
        expected_files = {"plan.json", "grades.json", "judgments.json", "summary.json"}
        expected_files.update(f"trials/{case['trial_id']}.json" for case in plan["cases"])
        if live:
            expected_files.add("authorization.json")
            expected_files.update(f"trials/{case['trial_id']}.stdout.jsonl" for case in plan["cases"])
        actual_files = set()
        for path in run_dir.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"run contains a symlink: {path.relative_to(run_dir)}")
            if not path.is_file():
                continue
            relative = path.relative_to(run_dir).as_posix()
            if live and relative.startswith("failures/") and relative.endswith(".json"):
                _read_json(path, f"failure record {relative}")
                continue
            actual_files.add(relative)
        if actual_files != expected_files:
            missing = sorted(expected_files - actual_files)
            extra = sorted(actual_files - expected_files)
            raise ValueError(f"run artifact set differs; missing={missing}, extra={extra}")
        if live:
            grant = _read_canonical(run_dir / "authorization.json", "authorization")
            if grant.get("plan_sha256") != plan["plan_sha256"]:
                raise ValueError("authorization does not name this plan")

        trials = _load_trials(run_dir, plan)
        if live:
            for trial in trials:
                raw = run_dir / "trials" / f"{trial['trial_id']}.stdout.jsonl"
                if _file_digest(raw) != trial["generation"]["raw_stdout_sha256"]:
                    raise ValueError(f"trial {trial['trial_id']} raw stream does not match its record")
                # The record must also say what the stream says: a forged
                # `output.text` re-sealed with `_make_trial` would otherwise pass
                # (bakeoff 11 code review, 2026-09-05). The oracle verdict is not
                # rederivable here because the workspace is discarded.
                payload = parse_stream_json(raw.read_text(encoding="utf-8"), source=f"trial {trial['trial_id']} stream")
                generation = trial["generation"]
                if payload.get("result") != trial["output"]["text"]:
                    raise ValueError(f"trial {trial['trial_id']} output text does not match its stream")
                if payload["_answer_models"] != generation["answer_models"]:
                    raise ValueError(f"trial {trial['trial_id']} answer models do not match its stream")
                if payload.get("num_turns") != generation["num_turns"]:
                    raise ValueError(f"trial {trial['trial_id']} turn count does not match its stream")
        grades = _read_canonical(run_dir / "grades.json", "grades")
        judgments = _read_canonical(run_dir / "judgments.json", "judgments")
        expected_grades, expected_judgments = _grade_artifacts(plan, trials)
        if grades != expected_grades:
            raise ValueError("grades do not rederive from plan and trials")
        if judgments != expected_judgments:
            raise ValueError("judgments do not rederive from plan and trials")
        summary = _read_canonical(run_dir / "summary.json", "summary")
        expected_summary = _make_summary(plan, trials, grades, judgments)
        if summary != expected_summary:
            raise ValueError("summary does not rederive from run artifacts")
        return summary


def _load_execution(execution: dict, *, check_binary: bool = True) -> dict:
    adapter = execution.get("adapter")
    if adapter == SYNTHETIC_ADAPTER:
        _exact_keys(execution, {"adapter", "network", "model"}, "execution")
        if execution["network"] is not False:
            raise ValueError("execution.network must be false for the synthetic adapter")
        return {"adapter": adapter, "network": False,
                "model": _require_string(execution["model"], "execution.model")}
    if adapter not in LIVE_ADAPTERS:
        raise ValueError(f"execution.adapter must be {SYNTHETIC_ADAPTER}, {LIVE_ADAPTER} or {AGENTIC_ADAPTER}")
    live_keys = {"adapter", "network", "model", "effort", "binary", "binary_version",
                 "binary_sha256", "timeout_seconds", "workers"}
    if adapter == AGENTIC_ADAPTER:
        _exact_keys(execution, live_keys | {"tools", "permission_mode", "allowed_tools", "max_budget_usd",
                                            "python_interpreter", "python_version"}, "execution")
    else:
        _exact_keys(execution, live_keys, "execution")
    if execution["network"] is not True:
        raise ValueError(f"execution.network must be true for {adapter}")
    effort = _require_string(execution["effort"], "execution.effort")
    if effort not in EFFORTS:
        raise ValueError(f"execution.effort must be one of {', '.join(EFFORTS)}")
    binary_text = _require_string(execution["binary"], "execution.binary")
    binary_sha = _require_sha(execution["binary_sha256"], "execution.binary_sha256")
    if check_binary:
        binary = Path(binary_text).expanduser()
        if binary.is_symlink() or not binary.is_file():
            raise ValueError("execution.binary must be a regular file (a pinned binary copy)")
        if _file_digest(binary) != binary_sha:
            raise ValueError("execution.binary_sha256 does not match the pinned binary")
    loaded = {
        "adapter": adapter,
        "network": True,
        "model": _require_string(execution["model"], "execution.model"),
        "effort": effort,
        "binary": binary_text,
        "binary_version": _require_string(execution["binary_version"], "execution.binary_version"),
        "binary_sha256": binary_sha,
        "timeout_seconds": _require_positive_int(execution["timeout_seconds"], "execution.timeout_seconds"),
        "workers": _require_positive_int(execution["workers"], "execution.workers"),
    }
    if adapter != AGENTIC_ADAPTER:
        return loaded
    tools = [_require_string(item, "execution.tools[]") for item in _require_list(execution["tools"], "execution.tools")]
    if not tools or len(set(tools)) != len(tools) or any(tool not in AGENTIC_TOOLS for tool in tools):
        raise ValueError(f"execution.tools must be distinct names from {', '.join(AGENTIC_TOOLS)}")
    mode = _require_string(execution["permission_mode"], "execution.permission_mode")
    if mode not in AGENTIC_PERMISSION_MODES:
        raise ValueError(f"execution.permission_mode must be one of {', '.join(AGENTIC_PERMISSION_MODES)}")
    allowed = [_require_string(item, "execution.allowed_tools[]")
               for item in _require_list(execution["allowed_tools"], "execution.allowed_tools")]
    if any(not ALLOWED_TOOL_RULE.fullmatch(rule) for rule in allowed):
        raise ValueError("execution.allowed_tools entries must look like Tool or Tool(rule)")
    loaded.update({
        "tools": sorted(tools),
        "permission_mode": mode,
        "allowed_tools": allowed,
        "max_budget_usd": _require_positive_number(execution["max_budget_usd"], "execution.max_budget_usd"),
        "python_interpreter": _require_string(execution["python_interpreter"], "execution.python_interpreter"),
        "python_version": _require_string(execution["python_version"], "execution.python_version"),
    })
    if not Path(loaded["python_interpreter"]).is_absolute():
        raise ValueError("execution.python_interpreter must be an absolute path")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", loaded["python_version"]):
        raise ValueError("execution.python_version must be major.minor.patch")
    if check_binary:
        _check_interpreter(loaded["python_interpreter"], loaded["python_version"])
    return loaded


def _check_interpreter(interpreter: str, version: str) -> None:
    path = Path(interpreter)
    if path.is_symlink() or not path.is_file():
        raise ValueError("execution.python_interpreter must be a regular file (the real interpreter path)")
    proc = subprocess.run([interpreter, "-I", "-c", "import platform; print(platform.python_version())"],
                          capture_output=True, text=True, errors="replace", timeout=30)
    reported = proc.stdout.strip()
    if proc.returncode != 0 or reported != version:
        raise ValueError(f"execution.python_interpreter reports {reported!r}, declared {version!r}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_deadline(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"deadline must be an ISO 8601 timestamp: {exc}") from exc
    if value.tzinfo is None:
        raise ValueError("deadline must carry a timezone (for example 2026-09-05T13:00:00Z)")
    return value.astimezone(timezone.utc)


def _load_oracle(value: object, probe_dir: Path, label: str) -> dict | None:
    tree = probe_dir / "oracle"
    if value is None:
        if tree.exists() or tree.is_symlink():
            raise ValueError(f"{label} has an oracle/ tree but no oracle declaration")
        return None
    table = _require_mapping(value, f"{label} oracle")
    _exact_keys(table, {"argv", "timeout_seconds"}, f"{label} oracle")
    argv = [_require_string(item, f"{label} oracle.argv[]") for item in _require_list(table["argv"], f"{label} oracle.argv")]
    if not argv or argv[0] != "python3":
        raise ValueError(f"{label} oracle.argv must start with python3")
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError(f"{label} must contain a regular oracle directory")
    if (tree / "CLAUDE.md").exists() or (tree / "CLAUDE.md").is_symlink():
        raise ValueError(f"{label} oracle tree must not contain CLAUDE.md")
    _tree_digest(tree)  # refuses symlinks and non-file entries
    return {"argv": argv, "timeout_seconds": _require_positive_int(table["timeout_seconds"], f"{label} oracle.timeout_seconds")}


def _refuse_credential_shapes(tree: Path, label: str) -> None:
    # Everything under the tree can be read by the model and echoed into the
    # retained stream, where a strict credential shape refuses the paid trial.
    for item in sorted(tree.rglob("*")):
        if item.is_file() and not item.is_symlink():
            if _strict_credential_hit(item.read_bytes().decode("utf-8", errors="replace")):
                raise ValueError(f"{label} file {item.relative_to(tree).as_posix()} carries a credential shape")


def _scan_text(text: str) -> dict:
    import final_message_scan  # scripts/final_message_scan.py, sealed by scan_sha256
    return final_message_scan.scan(text)


def _scan_field(value: object, label: str) -> str:
    field = _require_string(value, label)
    if SCAN_MODULE.is_symlink() or not SCAN_MODULE.is_file():
        raise ValueError(f"{label} needs {SCAN_MODULE.name} beside the harness")
    probe = _scan_text("")
    if not isinstance(probe, dict) or {"field", "maximum"} & set(probe):
        raise ValueError(f"{SCAN_MODULE.name}.scan must return a dict without field/maximum keys")
    if field not in probe or isinstance(probe[field], float) or not isinstance(probe[field], (bool, int)):
        raise ValueError(f"{label} must name an int or bool key of {SCAN_MODULE.name}.scan")
    return field


def _redact_strings(value: object) -> object:
    if isinstance(value, dict):
        return {key: _redact_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_strings(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value


def child_environment(*, path_prepend: Path | None = None, tmpdir: Path | None = None) -> dict[str, str]:
    """Allow-listed child environment; names only from CHILD_ENV_ALLOWLIST."""
    env = {name: os.environ[name] for name in CHILD_ENV_ALLOWLIST if name in os.environ}
    env.update(CHILD_ENV_FIXED)
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir) + os.sep
    if path_prepend is not None:
        env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
    return env


def _scheme_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_profile(workspace: Path, private_temp: Path) -> str:
    """The bakeoff 9 SDK runner's Bash profile (its sandboxProfile), translated verbatim."""
    denied = " ".join(f"(subpath {_scheme_string(path)})" for path in (
        "/Users", "/Volumes", "/Applications", "/private/tmp", "/tmp", "/private/var", "/var", "/opt",
    ))
    allowed = " ".join(f"(subpath {_scheme_string(path)})" for path in (
        "/private/var/db", "/private/var/select", "/opt/homebrew", str(workspace), str(private_temp),
    ))
    return "\n".join([
        "(version 1)", "(deny default)", "(allow process*)", "(allow signal)",
        "(allow sysctl-read)", "(allow mach-lookup)", "(allow ipc-posix-shm)",
        "(allow file-read-metadata)", "(allow file-read*)",
        f"(deny file-read* {denied})", f"(allow file-read* {allowed})",
        f"(allow file-write* (subpath {_scheme_string(str(workspace))}) "
        f"(subpath {_scheme_string(str(private_temp))}))",
        "(deny network*)", "",
    ])


def create_sandbox(workspace: Path, private_temp: Path, shim_dir: Path, interpreter: str) -> dict:
    """Write the profile and a `python3` shim that runs the pinned interpreter under it.

    The shim and profile live in `shim_dir`, which the profile does not make
    writable, so a sandboxed process cannot rewrite its own wrapper.
    """
    if not Path(SANDBOX_EXEC).is_file():
        raise LiveTrialError("environment", f"{SANDBOX_EXEC} is unavailable; refusing to run tools")
    shim_dir.mkdir(parents=True)
    profile = shim_dir / "sandbox.sb"
    profile.write_text(sandbox_profile(workspace.resolve(), private_temp.resolve()))
    shim = shim_dir / "python3"
    shim.write_text(
        "#!/bin/sh\n"
        f"export TMPDIR={shlex.quote(str(private_temp.resolve()) + os.sep)}\n"
        f"exec {shlex.quote(SANDBOX_EXEC)} -f {shlex.quote(str(profile))} "
        f"{shlex.quote(interpreter)} \"$@\"\n"
    )
    shim.chmod(0o700)
    return {"shim": shim, "record": {"profile_sha256": _file_digest(profile), "python3": interpreter}}


def shim_check(interpreter: str | None = None) -> dict:
    """Offline proof that the shim confines the interpreter (Darwin only).

    Runs a script through a fresh shim in a temporary workspace and reports
    whether a workspace write succeeded while a loopback `urlopen`, a read of
    `~/.codex/auth.json`, and a write outside the workspace all failed.
    """
    interpreter = interpreter or os.path.realpath(shutil.which("python3") or "python3")
    script = (
        "import json, os, pathlib, urllib.request\n"
        "out = {}\n"
        "def attempt(name, fn):\n"
        "    try:\n"
        "        fn(); out[name] = 'ok'\n"
        "    except Exception as exc:\n"
        "        reason = getattr(exc, 'reason', None)\n"
        "        out[name] = 'failed: ' + type(reason if isinstance(reason, Exception) else exc).__name__\n"
        "attempt('workspace_write', lambda: pathlib.Path('inside.txt').write_text('ok'))\n"
        "attempt('loopback_urlopen', lambda: urllib.request.urlopen('http://127.0.0.1:9', timeout=2))\n"
        "attempt('codex_auth_read', lambda: open(os.path.expanduser('~/.codex/auth.json'), 'rb').read())\n"
        "attempt('outside_write', lambda: pathlib.Path(os.path.expanduser('~/clause-shim-check.tmp')).write_text('x'))\n"
        "out['tmpdir'] = os.environ.get('TMPDIR')\n"
        "print(json.dumps(out))\n"
    )
    with tempfile.TemporaryDirectory(prefix="clause-shim-check-") as temporary:
        base = Path(temporary).resolve()
        workspace = base / "workspace"
        workspace.mkdir()
        private_temp = base / "private-tmp"
        private_temp.mkdir()
        sandbox = create_sandbox(workspace, private_temp, base / "shim", interpreter)
        env = child_environment(path_prepend=sandbox["shim"].parent, tmpdir=private_temp)
        proc = subprocess.run(["python3", "-I", "-c", script], cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, errors="replace", timeout=60)
        if proc.returncode != 0:
            raise ValueError(f"shim check could not run the interpreter: {proc.stderr[-500:]}")
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    result["interpreter"] = interpreter
    result["profile_sha256"] = sandbox["record"]["profile_sha256"]
    expected = {"workspace_write": result["workspace_write"] == "ok",
                "loopback_urlopen": result["loopback_urlopen"].startswith("failed: PermissionError"),
                "codex_auth_read": result["codex_auth_read"].startswith("failed:"),
                "outside_write": result["outside_write"].startswith("failed: PermissionError"),
                "tmpdir": result["tmpdir"] == str(private_temp) + os.sep}
    result["passed"] = all(expected.values())
    if not result["passed"]:
        raise ValueError(f"shim check failed: {json.dumps(result, sort_keys=True)}")
    return result


def _check_authorization(path: Path | None, plan: dict) -> dict:
    if path is None:
        raise ValueError(
            f"{LIVE_ADAPTER} dispatch needs --authorization naming plan {plan['plan_sha256'][:12]}"
        )
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("authorization must be a regular file")
    grant = _read_canonical(path, "authorization")
    _exact_keys(grant, {"schema", "plan_sha256", "authorized_by", "authorized_on", "statement"}, "authorization")
    if grant["schema"] != AUTHORIZATION_SCHEMA:
        raise ValueError(f"authorization schema must be {AUTHORIZATION_SCHEMA}")
    if grant["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError(
            f"authorization names plan {str(grant['plan_sha256'])[:12]}, not this plan "
            f"{plan['plan_sha256'][:12]}"
        )
    for key in ("authorized_by", "authorized_on", "statement"):
        _require_string(grant[key], f"authorization.{key}")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", grant["authorized_on"]):
        raise ValueError("authorization.authorized_on must be an ISO date")
    return grant


class LiveTrialError(Exception):
    def __init__(self, kind: str, detail: str, *, exit_code: int | None = None, stderr: str = ""):
        super().__init__(detail)
        self.kind = kind
        self.exit_code = exit_code
        self.stderr = stderr


def _binary_version(binary: Path) -> str:
    proc = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, errors="replace", timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise LiveTrialError("version", f"cannot read binary version: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def _place_variant(variant: "Variant", workspace: Path, case: dict) -> None:
    """Copy the arm's CLAUDE.md into the workspace, or assert there is none."""
    target = workspace / "CLAUDE.md"
    if variant.source is None:
        if case["claude_md_sha256"] is not None:
            raise ValueError(f"workspace variant drift for {case['trial_id']}: absent arm has a hash")
        if target.exists() or target.is_symlink():
            raise ValueError(f"workspace variant drift for {case['trial_id']}: CLAUDE.md present in an absent arm")
        return
    shutil.copyfile(variant.source, target)
    if _file_digest(target) != case["claude_md_sha256"]:
        raise ValueError(f"workspace variant drift for {case['trial_id']}")


def _ambient_instruction_files(workspace: Path) -> list[str]:
    found = []
    for directory in (workspace, *workspace.parents):
        for relative in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            candidate = directory / relative
            if candidate.is_file() and candidate != workspace / "CLAUDE.md":
                found.append(str(candidate))
    return found


def _agentic_flags(execution: dict) -> list[str]:
    """Tool surface and permission policy for claude-code/2, kept in one place.

    --tools fixes what the model is shown (identical across arms); the
    allow rules and mode decide what runs; the budget is a runaway guard.
    `--restricted` is deliberately absent: on 2.1.258 it suppresses project
    CLAUDE.md (canary check, 2026-09-05), which would remove the treatment.
    """
    flags = ["--tools", ",".join(execution["tools"])]
    if execution["allowed_tools"]:
        flags += ["--allowedTools", *execution["allowed_tools"]]
    flags += ["--permission-mode", execution["permission_mode"],
              "--max-budget-usd", str(execution["max_budget_usd"])]
    return flags


def _live_command(binary: Path, execution: dict, prompt: str) -> list[str]:
    agentic = execution["adapter"] == AGENTIC_ADAPTER
    return [
        str(binary), "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", execution["model"], "--effort", execution["effort"],
        *(_agentic_flags(execution) if agentic else ["--tools", ""]),
        "--setting-sources", "project",
        "--settings", '{"autoMemoryEnabled":false}',
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        *([] if agentic else ["--permission-mode", "dontAsk"]),
        "--no-session-persistence",
        "--prompt-suggestions", "false",
    ]


def _failure_kind(lowered: str, subtype: object = None, *, budget: bool = False) -> str:
    if any(marker in lowered for marker in AUTH_FAILURE_MARKERS):
        return "authentication"
    if budget and ("budget" in str(subtype or "").lower() or "max_budget" in lowered):
        return "budget"
    return "error"


def _withhold_reminders(text: str) -> tuple[str, int, bool]:
    """Replace every paired reminder span; report the count and whether a tag is left."""
    retained, count = REMINDER_SPAN.subn(REMINDER_PLACEHOLDER, text)
    unpaired = bool(REMINDER_TAG.search(retained)) or "</system-reminder>" in retained.lower()
    return retained, count, unpaired


def _content_blocks(item: dict) -> list[dict]:
    message = item.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _referenced_paths(name: str, inputs: dict) -> list[str]:
    if name in ("Read", "Edit", "Write"):
        keys = ("file_path",)
    elif name in ("Grep", "Glob"):
        keys = ("path",)
    elif name == "Bash":
        command = inputs.get("command")
        return ABSOLUTE_PATH_TOKEN.findall(command) if isinstance(command, str) else []
    else:
        return []
    return [inputs[key] for key in keys if isinstance(inputs.get(key), str) and inputs[key]]


def _inside_workspace(workspace: Path, path: str) -> bool:
    if path.startswith("~"):
        return False
    candidate = Path(path)
    if not candidate.is_absolute():
        return True
    roots = {workspace, workspace.resolve()}
    return any(candidate.is_relative_to(root) or Path(os.path.realpath(path)).is_relative_to(root)
               for root in roots)


def _scan_events(raw: str, workspace: Path) -> dict:
    """Tool activity from a stream that parse_stream_json has already accepted."""
    init_tools = None
    init_mode = None
    calls: dict[str, int] = {}
    sequence: list[dict] = []
    bash: list[str | None] = []
    outside: list[dict] = []
    results = 0
    claude_md_referenced = False
    for line in raw.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("type") == "system" and item.get("subtype") == "init":
            init_tools = item.get("tools")
            init_mode = item.get("permissionMode")
        elif item.get("type") == "assistant":
            for block in _content_blocks(item):
                if block.get("type") != "tool_use":
                    continue
                name = str(block.get("name"))
                inputs = block.get("input") if isinstance(block.get("input"), dict) else {}
                index = len(sequence)
                sequence.append({"index": index, "name": name})
                calls[name] = calls.get(name, 0) + 1
                if name == "Bash":
                    command = inputs.get("command")
                    bash.append(redact(command) if isinstance(command, str) else None)
                # Executed or denied alike: every requested input is scanned.
                for path in _referenced_paths(name, inputs):
                    if not _inside_workspace(workspace, path):
                        outside.append({"index": index, "name": name, "path": redact(path)})
                if any(isinstance(value, str) and "claude.md" in value.lower() for value in inputs.values()):
                    claude_md_referenced = True
        elif item.get("type") == "user":
            results += sum(1 for block in _content_blocks(item) if block.get("type") == "tool_result")
    return {
        "init_tools": init_tools,
        "init_permission_mode": init_mode,
        "tool_calls": dict(sorted(calls.items())),
        "tool_call_sequence": sequence,
        "bash_commands": bash,
        "tool_results": results,
        "paths_outside_workspace": outside,
        "claude_md_referenced": claude_md_referenced,
    }


def _denial_input(denial: dict) -> str:
    inputs = denial.get("tool_input") if isinstance(denial.get("tool_input"), dict) else {}
    for key in ("command", "file_path", "path", "pattern"):
        if isinstance(inputs.get(key), str):
            return inputs[key]
    return _canonical(inputs).decode("utf-8")[:500]


def _tree_entries(root: Path) -> dict[str, dict]:
    entries = {}
    for item in sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()):
        relative = item.relative_to(root)
        if "__pycache__" in relative.parts or relative.as_posix() == "CLAUDE.md":
            continue
        if item.is_symlink():
            entries[relative.as_posix()] = {"sha256": None, "symlink": True}
        elif item.is_file():
            entries[relative.as_posix()] = {"sha256": _file_digest(item)}
    return entries


def _snapshot_workspace(seed: Path, workspace: Path) -> dict:
    before = _tree_entries(seed)
    after = _tree_entries(workspace)
    changed = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            change = "added"
        elif path not in after:
            change = "removed"
        elif before[path] != after[path]:
            change = "modified"
        else:
            continue
        entry = {"path": redact(path), "change": change, "sha256": after.get(path, {}).get("sha256")}
        if after.get(path, {}).get("symlink"):
            entry["symlink"] = True
        changed.append(entry)
    tree = [{"path": path, **entry} for path, entry in sorted(after.items())]
    added_top_level_py = sorted(
        entry["path"] for entry in changed
        if entry["change"] == "added" and "/" not in entry["path"] and entry["path"].endswith(".py")
    )
    return {"tree_sha256": _digest(tree), "files_changed": changed, "added_top_level_py": added_top_level_py}


def _run_oracle(probe: "Probe", workspace: Path, env: dict[str, str], shim: Path, interpreter: str) -> dict | None:
    if probe.oracle is None:
        return None
    for cache in [item for item in workspace.rglob("__pycache__") if item.is_dir() and not item.is_symlink()]:
        shutil.rmtree(cache)
    # probes/<id>/oracle/ lands as workspace/oracle/, so the declared argv
    # (for example `python3 -I -B oracle/run.py`) resolves from the workspace.
    source = probe.source / "oracle"
    copied: list[str] = []
    overwrote: list[str] = []
    error = None
    try:
        for item in sorted(source.rglob("*")):
            if not item.is_file():
                continue
            relative = (Path("oracle") / item.relative_to(source)).as_posix()
            target = workspace / relative
            if target.is_symlink() or target.exists():
                overwrote.append(relative)
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
            copied.append(relative)
    except OSError as exc:
        error = redact(f"oracle copy-in failed: {exc}")
    # argv[0] "python3" means the pinned interpreter, entered through the shim.
    record = {"argv": [interpreter, *probe.oracle["argv"][1:]], "exit_code": None, "timed_out": False,
              "duration_sec": 0.0, "stdout_tail": "", "stderr_tail": "",
              "copied": copied, "overwrote": overwrote, "error": error}
    if error is not None:
        return record
    oracle_env = {**env, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
    argv = [str(shim), *probe.oracle["argv"][1:]]
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=workspace, env=oracle_env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, errors="replace",
                              timeout=probe.oracle["timeout_seconds"])
        record["exit_code"], out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        record["timed_out"], out, err = True, text_output(exc.stdout), text_output(exc.stderr)
    record["duration_sec"] = round(time.monotonic() - started, 3)
    record["stdout_tail"] = redact(out[-TAIL_CHARS:])
    record["stderr_tail"] = redact(err[-TAIL_CHARS:])
    return record


def _run_live_trial(
    binary: Path, execution: dict, case: dict, variant: "Variant", probe: "Probe", plan: dict
) -> tuple[dict, bytes]:
    agentic = execution["adapter"] == AGENTIC_ADAPTER
    version = _binary_version(binary)
    if version != execution["binary_version"]:
        raise LiveTrialError("version", f"binary reports {version!r}, declared {execution['binary_version']!r}")
    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory(prefix="clause-campaign-live-") as temporary:
        base = Path(temporary).resolve()
        workspace = base / "workspace"
        shutil.copytree(probe.source / "seed", workspace)
        if _tree_digest(workspace) != case["seed_tree_sha256"]:
            raise LiveTrialError("environment", "workspace seed drift")
        try:
            _place_variant(variant, workspace, case)
        except ValueError as exc:
            raise LiveTrialError("environment", str(exc)) from exc
        if Path.home().resolve() in workspace.parents:
            raise LiveTrialError("environment", "workspace must not sit under $HOME")
        if REPO_ROOT in workspace.parents:
            raise LiveTrialError("environment", "workspace must not sit under the repository")
        ambient = _ambient_instruction_files(workspace)
        if ambient:
            raise LiveTrialError("environment", f"ambient instruction files: {ambient}")
        if agentic:
            private_temp = base / "private-tmp"
            private_temp.mkdir()
            sandbox = create_sandbox(workspace, private_temp, base / "shim", execution["python_interpreter"])
            env = child_environment(path_prepend=sandbox["shim"].parent, tmpdir=private_temp)
            stripped: list[str] = []
        else:
            env = isolated_environment()
            stripped = sorted(name for name in STRIPPED_ENV if env.pop(name, None) is not None)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                _live_command(binary, execution, case["prompt"]),
                cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, errors="replace",
                timeout=execution["timeout_seconds"],
            )
        except subprocess.TimeoutExpired as exc:
            raise LiveTrialError("timeout", f"no result within {execution['timeout_seconds']}s",
                                 stderr=str(exc.stderr or "")[-500:]) from exc
        duration = round(time.monotonic() - started, 3)
        if agentic:
            # The oracle needs the workspace, which does not outlive this block.
            final_claude_md = workspace / "CLAUDE.md"
            claude_md_final = (
                _file_digest(final_claude_md)
                if final_claude_md.is_file() and not final_claude_md.is_symlink() else None
            )
            if claude_md_final != case["claude_md_sha256"]:
                what = "appeared" if case["claude_md_sha256"] is None else "changed"
                raise LiveTrialError("environment", f"workspace CLAUDE.md {what} during the session",
                                     exit_code=proc.returncode)
            workspace_record = _snapshot_workspace(probe.source / "seed", workspace)
            oracle_record = _run_oracle(probe, workspace, env, sandbox["shim"], execution["python_interpreter"])
    stdout, stderr = proc.stdout, proc.stderr
    withheld, unpaired = 0, False
    if agentic:
        stdout, withheld, unpaired = _withhold_reminders(stdout)
    # Failure records keep only a redacted tail of each stream: enough to
    # diagnose, never the raw bytes.
    tail = redact(stderr[-500:] + ("\n--- stdout ---\n" + stdout[-700:] if stdout else ""))
    lowered = f"{stdout}\n{stderr}".lower()
    if unpaired:
        raise LiveTrialError("environment", "stream carries an unpaired reminder tag; not retained",
                             exit_code=proc.returncode, stderr=REMINDER_TAG.sub("<withheld:tag>", tail))
    if proc.returncode != 0:
        kind = _failure_kind(lowered, budget=agentic)
        raise LiveTrialError(kind, f"binary exited {proc.returncode}", exit_code=proc.returncode, stderr=tail)
    try:
        payload = parse_stream_json(stdout, source="live trial stream")
    except ValueError as exc:
        raise LiveTrialError("error", f"invalid stream: {exc}", exit_code=proc.returncode, stderr=tail) from exc
    if payload.get("is_error") or payload.get("subtype") not in (None, "success"):
        kind = _failure_kind(lowered, payload.get("subtype"), budget=agentic)
        raise LiveTrialError(kind, f"result subtype {payload.get('subtype')!r}, is_error {payload.get('is_error')!r}",
                             exit_code=proc.returncode, stderr=tail)
    if payload["_answer_models"] != [execution["model"]]:
        raise LiveTrialError("model", f"answer models {payload['_answer_models']} are not [{execution['model']!r}]",
                             exit_code=proc.returncode, stderr=tail)
    text = payload.get("result")
    if not isinstance(text, str) or not text.strip():
        raise LiveTrialError("error", "empty result", exit_code=proc.returncode, stderr=tail)
    if not agentic and "<system-reminder>" in lowered:
        raise LiveTrialError("environment", "stream carries a reminder payload; not retained",
                             exit_code=proc.returncode, stderr=tail)
    # The stream is the model's answer plus harness metadata from a session
    # with no credential in its inputs; refuse only an unmistakable
    # credential shape (see STRICT_CREDENTIAL_PATTERNS), never prose.
    if _strict_credential_hit(stdout):
        raise LiveTrialError("environment", "stream carries a credential; not retained",
                             exit_code=proc.returncode, stderr=tail)
    raw = stdout.encode("utf-8")
    generation = {
        "binary_version": version,
        "binary_sha256": execution["binary_sha256"],
        "requested_model": execution["model"],
        "requested_effort": execution["effort"],
        "init_model": payload.get("_init_model"),
        "answer_models": payload["_answer_models"],
        "stop_reason": payload.get("stop_reason"),
        "num_turns": payload.get("num_turns"),
        "usage": payload.get("usage"),
        "total_cost_usd": payload.get("total_cost_usd"),
        "started_utc": started_utc,
        "duration_sec": duration,
        "exit_code": proc.returncode,
        "raw_stdout_sha256": _digest_bytes(raw),
    }
    if not agentic:
        generation["stripped_env"] = stripped  # names only; values are never read into a record
    else:
        events = _scan_events(stdout, workspace)
        if events["init_tools"] is None or sorted(events["init_tools"]) != list(execution["tools"]):
            raise LiveTrialError("environment", f"init tools {events['init_tools']!r} are not the declared surface",
                                 exit_code=proc.returncode, stderr=tail)
        if events["init_permission_mode"] != execution["permission_mode"]:
            raise LiveTrialError("environment", f"init permission mode {events['init_permission_mode']!r} differs",
                                 exit_code=proc.returncode, stderr=tail)
        denials = payload.get("permission_denials")
        generation.update({
            **events,
            "child_env_names": sorted(env),  # names only; values are never read into a record
            "sandbox": sandbox["record"],
            "permission_denials": [
                {"tool_name": item.get("tool_name"), "input": redact(_denial_input(item))}
                for item in (denials if isinstance(denials, list) else []) if isinstance(item, dict)
            ],
            "model_usage": payload.get("modelUsage"),
            "max_budget_usd": execution["max_budget_usd"],
            "claude_md_final_sha256": claude_md_final,
            "retained_stream": "reminder-spans-withheld",
            "reminder_spans_withheld": withheld,
            "workspace": workspace_record,
            "oracle": oracle_record,
        })
    trial = _make_trial(plan, case, text, generation)
    _ensure_safe(trial, "trial")
    return trial, raw


GENERATION_KEYS = {
    LIVE_ADAPTER: {
        "stripped_env", "binary_version", "binary_sha256", "requested_model", "requested_effort",
        "init_model", "answer_models", "stop_reason", "num_turns", "usage", "total_cost_usd",
        "started_utc", "duration_sec", "exit_code", "raw_stdout_sha256",
    },
}
GENERATION_KEYS[AGENTIC_ADAPTER] = (GENERATION_KEYS[LIVE_ADAPTER] - {"stripped_env"}) | {
    "child_env_names", "sandbox", "init_tools", "init_permission_mode", "tool_calls",
    "tool_call_sequence", "bash_commands", "tool_results", "paths_outside_workspace",
    "permission_denials", "model_usage", "max_budget_usd", "claude_md_final_sha256",
    "claude_md_referenced", "retained_stream", "reminder_spans_withheld", "workspace", "oracle",
}


def _validate_generation(generation: dict, plan: dict, label: str) -> None:
    execution = plan["execution"]
    if execution["adapter"] not in LIVE_ADAPTERS:
        raise ValueError(f"{label} carries a generation record under a non-live adapter")
    _exact_keys(generation, GENERATION_KEYS[execution["adapter"]], f"{label}.generation")
    if generation["binary_version"] != execution["binary_version"]:
        raise ValueError(f"{label} ran on binary {generation['binary_version']!r}, not the declared one")
    if generation["binary_sha256"] != execution["binary_sha256"]:
        raise ValueError(f"{label} ran on a binary other than the pinned one")
    if generation["requested_model"] != execution["model"] or generation["requested_effort"] != execution["effort"]:
        raise ValueError(f"{label} requested a model or effort other than the declared one")
    if generation["answer_models"] != [execution["model"]]:
        raise ValueError(f"{label} was answered by {generation['answer_models']}")
    _require_sha(generation["raw_stdout_sha256"], f"{label}.generation.raw_stdout_sha256")


def _record_failure(run_dir: Path, case: dict, error: LiveTrialError) -> None:
    failures = run_dir / "failures"
    failures.mkdir(exist_ok=True)
    attempt = 1
    while (failures / f"{case['trial_id']}--{attempt:03d}.json").exists():
        attempt += 1
    record = {
        "trial_id": case["trial_id"],
        "case_sha256": case["case_sha256"],
        "variant_id": case["variant_id"],
        "probe_id": case["probe_id"],
        "kind": error.kind,
        "detail": str(error),
        "exit_code": error.exit_code,
        "stderr_tail": redact(error.stderr),
        "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_immutable(failures / f"{case['trial_id']}--{attempt:03d}.json", record)


def _write_immutable_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"immutable path is not a regular file: {path}")
        if path.read_bytes() != data:
            raise ValueError(f"immutable artifact differs: {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError(f"immutable artifact differs: {path}")
    finally:
        temporary.unlink(missing_ok=True)


def _validate_synthetic(value: dict) -> str:
    _exact_keys(value, {"response"}, "synthetic response")
    response = _require_string(value["response"], "synthetic response.response")
    _ensure_safe({"response": response}, "synthetic response")
    return response


def _assert_no_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"run contains a symlink: {path.relative_to(root)}")


def _execute_synthetic(path: Path, trial_id: str) -> str:
    return _validate_synthetic(_read_canonical(path, f"synthetic response {trial_id}"))


def _make_trial(plan: dict, case: dict, response: str, generation: dict | None = None) -> dict:
    if "synthetic_response_sha256" in case:
        response_fixture_sha256 = _digest_bytes(_pretty({"response": response}))
        if response_fixture_sha256 != case["synthetic_response_sha256"]:
            raise ValueError(
                f"trial {case['trial_id']} output does not match the pinned synthetic response"
            )
    body = {
        "schema": TRIAL_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "case_sha256": case["case_sha256"],
        "trial_id": case["trial_id"],
        "variant_id": case["variant_id"],
        "claude_md_sha256": case["claude_md_sha256"],
        "probe_id": case["probe_id"],
        "probe_tree_sha256": case["probe_tree_sha256"],
        "seed_tree_sha256": case["seed_tree_sha256"],
        "prompt": case["prompt"],
        "prompt_sha256": case["prompt_sha256"],
        "repetition": case["repetition"],
        "execution": plan["execution"],
        "output": {
            "text": response,
            "sha256": _digest_bytes(response.encode("utf-8")),
            "words": len(response.split()),
        },
    }
    if "synthetic_response_sha256" in case:
        body["synthetic_response_sha256"] = case["synthetic_response_sha256"]
    if plan["execution"]["adapter"] in LIVE_ADAPTERS:
        if not isinstance(generation, dict):
            raise ValueError(f"trial {case['trial_id']} lacks a generation record")
        body["generation"] = generation
    return _seal(body, "trial_sha256")


def dispatch_order(plan: dict) -> list[dict]:
    """The order a live agentic run dispatches the plan's cases.

    Repetition-major, so a stop leaves complete blocks across arms. Inside a
    block the order is canonical (probe, variant) unless the plan carries a
    `dispatch_seed`; then each block is shuffled by `random.Random(seed * 1000
    + repetition)` (repetitions are at most 999, so the streams are distinct),
    which breaks the arm-with-time confound inside a block that bakeoffs 11
    and 12 carried. The plan's own case order stays canonical; this function
    is the only source of the dispatch order and reproduces it from the plan.
    """
    seed = plan.get("dispatch_seed")
    blocks: dict[int, list[dict]] = {}
    for case in plan["cases"]:
        blocks.setdefault(case["repetition"], []).append(case)
    ordered = []
    for repetition in sorted(blocks):
        block = sorted(blocks[repetition], key=lambda item: (item["probe_id"], item["variant_id"]))
        if seed is not None:
            random.Random(seed * 1000 + repetition).shuffle(block)
        ordered.extend(block)
    return ordered


def _validate_plan(plan: dict) -> None:
    _verify_seal(plan, "plan_sha256", "plan")
    _exact_keys(
        plan,
        {"schema", "campaign_id", "declaration_sha256", "protocol", "execution", "measures", "cases", "plan_sha256"}
        | ({"dispatch_seed"} & set(plan)),
        "plan",
    )
    if "dispatch_seed" in plan:
        _require_dispatch_seed(plan["dispatch_seed"])
    if plan["schema"] != PLAN_SCHEMA:
        raise ValueError(f"plan schema must be {PLAN_SCHEMA}")
    _require_id(plan["campaign_id"], "plan.campaign_id")
    _require_sha(plan["declaration_sha256"], "plan.declaration_sha256")
    protocol = _require_mapping(plan["protocol"], "plan.protocol")
    _exact_keys(protocol, {"path", "sha256"}, "plan.protocol")
    _require_string(protocol["path"], "plan.protocol.path")
    _require_sha(protocol["sha256"], "plan.protocol.sha256")
    execution = _require_mapping(plan["execution"], "plan.execution")
    declared = {key: value for key, value in execution.items()
                if key not in {"harness_sha256", "python", "scan_sha256"}}
    if _load_execution(declared, check_binary=False) != declared:
        raise ValueError("plan execution is not a normalized adapter declaration")
    live = execution["adapter"] in LIVE_ADAPTERS
    _require_sha(execution["harness_sha256"], "plan.execution.harness_sha256")
    if execution["adapter"] == AGENTIC_ADAPTER:
        _require_sha(execution.get("scan_sha256"), "plan.execution.scan_sha256")
    elif "scan_sha256" in execution:
        raise ValueError("plan.execution.scan_sha256 belongs to the agentic adapter only")
    if not re.fullmatch(r"[0-9]+\.[0-9]+", _require_string(execution["python"], "plan.execution.python")):
        raise ValueError("plan.execution.python must pin major.minor")
    measures = _require_list(plan["measures"], "plan.measures")
    if not measures:
        raise ValueError("plan must contain measures")
    measure_ids = [_validate_planned_measure(item) for item in measures]
    if len(measure_ids) != len(measures) or len(set(measure_ids)) != len(measure_ids):
        raise ValueError("plan measures must be unique tables")
    if measure_ids != sorted(measure_ids):
        raise ValueError("plan measures are not canonical")
    kinds = {item.get("kind") for item in measures}
    if kinds != {"deterministic", "judgmental"}:
        raise ValueError("plan must preserve both grading boundaries")
    cases = _require_list(plan["cases"], "plan.cases")
    if not cases:
        raise ValueError("plan must contain cases")
    ids = []
    for case in cases:
        table = _require_mapping(case, "plan case")
        _verify_seal(table, "case_sha256", "plan case")
        hashes = ["claude_md_sha256", "probe_tree_sha256", "seed_tree_sha256", "prompt_sha256"]
        if not live:
            hashes.append("synthetic_response_sha256")
        _exact_keys(table, {"variant_id", "probe_id", "prompt", "repetition", "trial_id", "case_sha256", *hashes}, "plan case")
        _require_id(table["variant_id"], "case.variant_id")
        _require_id(table["probe_id"], "case.probe_id")
        _require_positive_int(table["repetition"], "case.repetition")
        for key in hashes:
            if key == "claude_md_sha256" and table[key] is None:
                continue  # absent-file arm: the workspace holds no CLAUDE.md
            _require_sha(table[key], f"case.{key}")
        prompt = _require_string(table["prompt"], "case.prompt")
        if _digest_bytes(prompt.encode("utf-8")) != table["prompt_sha256"]:
            raise ValueError("case prompt hash does not match prompt")
        trial_id = _require_string(table["trial_id"], "case.trial_id")
        if not TRIAL_ID.fullmatch(trial_id):
            raise ValueError("case.trial_id has an invalid shape")
        seed = {key: value for key, value in table.items()
                if key not in {"trial_id", "case_sha256"}}
        expected_id = (
            f"{table['variant_id']}--{table['probe_id']}--r{table['repetition']:03d}--"
            f"{_digest(seed)[:12]}"
        )
        if trial_id != expected_id:
            raise ValueError("case.trial_id does not match its content")
        ids.append(trial_id)
    if len(ids) != len(set(ids)):
        raise ValueError("plan contains duplicate trial ids")
    canonical_order = sorted(
        cases, key=lambda item: (item["variant_id"], item["probe_id"], item["repetition"])
    )
    if cases != canonical_order:
        raise ValueError("plan cases are not in canonical order")
    _ensure_safe(plan, "plan")


def _validate_planned_measure(value: object) -> str:
    measure = _require_mapping(value, "plan measure")
    identifier = _require_id(measure.get("id"), "plan measure id")
    if measure.get("kind") == "deterministic" and measure.get("grader") == "contains":
        _exact_keys(measure, {"id", "kind", "grader", "needle"}, f"plan measure {identifier}")
        _require_string(measure["needle"], f"plan measure {identifier}.needle")
    elif measure.get("kind") == "deterministic" and (
        measure.get("grader") == "max_words" or measure.get("grader") in DENSITY_GRADERS
    ):
        _exact_keys(measure, {"id", "kind", "grader", "maximum"}, f"plan measure {identifier}")
        _require_positive_int(measure["maximum"], f"plan measure {identifier}.maximum")
    elif measure.get("kind") == "deterministic" and measure.get("grader") == "oracle_pass":
        _exact_keys(measure, {"id", "kind", "grader"}, f"plan measure {identifier}")
    elif measure.get("kind") == "deterministic" and measure.get("grader") == "final_message_scan":
        _exact_keys(measure, {"id", "kind", "grader", "field", "maximum"}, f"plan measure {identifier}")
        _require_string(measure["field"], f"plan measure {identifier}.field")
        _require_count(measure["maximum"], f"plan measure {identifier}.maximum")
    elif measure.get("kind") == "judgmental":
        _exact_keys(
            measure,
            {"id", "kind", "question", "rubric", "rubric_sha256", "rubric_text"},
            f"plan measure {identifier}",
        )
        _require_string(measure["question"], f"plan measure {identifier}.question")
        _require_string(measure["rubric"], f"plan measure {identifier}.rubric")
        rubric_text = _require_string(measure["rubric_text"], f"plan measure {identifier}.rubric_text")
        if _digest_bytes(rubric_text.encode("utf-8")) != _require_sha(
            measure["rubric_sha256"], f"plan measure {identifier}.rubric_sha256"
        ):
            raise ValueError(f"plan measure {identifier} rubric hash does not match its text")
    else:
        raise ValueError(f"plan measure {identifier} has an unsupported boundary")
    return identifier


def _load_trials(run_dir: Path, plan: dict) -> list[dict]:
    trials = []
    for case in plan["cases"]:
        path = run_dir / "trials" / f"{case['trial_id']}.json"
        trials.append(_load_one_trial(path, plan, case))
    return trials


def _load_one_trial(path: Path, plan: dict, case: dict) -> dict:
    label = f"trial {case['trial_id']}"
    if not path.is_file():
        raise ValueError(f"{label} has not been recorded")
    trial = _read_canonical(path, label)
    _verify_seal(trial, "trial_sha256", label)
    output = _require_mapping(trial.get("output"), f"{label}.output")
    _exact_keys(output, {"text", "sha256", "words"}, f"{label}.output")
    text = _require_string(output["text"], f"{label}.output.text")
    generation = trial.get("generation")
    if generation is not None:
        _validate_generation(_require_mapping(generation, f"{label}.generation"), plan, label)
    expected = _make_trial(plan, case, text, generation)
    if trial != expected:
        raise ValueError(f"{label} does not match its planned case")
    _ensure_safe(trial, label)
    return trial


def _grade_artifacts(plan: dict, trials: list[dict]) -> tuple[dict, dict]:
    deterministic = [item for item in plan["measures"] if item["kind"] == "deterministic"]
    judgmental = [item for item in plan["measures"] if item["kind"] == "judgmental"]
    rows = []
    tasks = []
    for trial in trials:
        text = trial["output"]["text"]
        for measure in deterministic:
            if measure["grader"] == "contains":
                observation = {"contains": measure["needle"] in text, "needle": measure["needle"]}
                passed = observation["contains"]
            elif measure["grader"] == "max_words":
                observation = {"maximum": measure["maximum"], "words": trial["output"]["words"]}
                passed = observation["words"] <= observation["maximum"]
            elif measure["grader"] in DENSITY_GRADERS:
                # The whole measurement is retained so a reader can recompute
                # arm medians from the rows; `passed` is the declared split.
                observation = {"maximum": measure["maximum"], **measure_density(text)}
                value = observation[DENSITY_GRADERS[measure["grader"]]]
                passed = value is not None and value <= observation["maximum"]
            elif measure["grader"] == "oracle_pass":
                oracle = trial["generation"]["oracle"]
                observation = {"exit_code": oracle["exit_code"], "timed_out": oracle["timed_out"],
                               "overwrote": len(oracle["overwrote"]), "error": oracle["error"]}
                passed = oracle["exit_code"] == 0 and not oracle["timed_out"]
            elif measure["grader"] == "final_message_scan":
                # The whole scan is retained (strings redacted) so a reader can
                # recompute any field from the rows; `passed` is the declared split.
                scan = _redact_strings(_scan_text(text))
                observation = {**scan, "field": measure["field"], "maximum": measure["maximum"]}
                passed = int(scan[measure["field"]]) <= measure["maximum"]
            else:
                raise ValueError(f"unsupported planned grader: {measure['grader']}")
            row = {
                "trial_id": trial["trial_id"],
                "trial_sha256": trial["trial_sha256"],
                "variant_id": trial["variant_id"],
                "measure_id": measure["id"],
                "passed": passed,
                "observation": observation,
            }
            rows.append(_seal(row, "grade_sha256"))
        for measure in judgmental:
            binding = {
                "trial_sha256": trial["trial_sha256"],
                "output_sha256": trial["output"]["sha256"],
                "measure_id": measure["id"],
                "rubric_sha256": measure["rubric_sha256"],
            }
            task = {
                "task_id": _digest(binding),
                "binding_sha256": _digest(binding),
                "measure_id": measure["id"],
                "question": measure["question"],
                "rubric": measure["rubric_text"],
                "rubric_sha256": measure["rubric_sha256"],
                # The prompt is identical across variants, so it carries no
                # variant identity; a judge needs it for any coverage question.
                "prompt": trial["prompt"],
                "prompt_sha256": trial["prompt_sha256"],
                "response": text,
                "response_sha256": trial["output"]["sha256"],
                "status": "pending",
            }
            tasks.append(_seal(task, "task_sha256"))
    grades = _seal({"schema": GRADES_SCHEMA, "plan_sha256": plan["plan_sha256"], "rows": rows}, "grades_sha256")
    judgments = _seal({
        "schema": JUDGMENTS_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "tasks": sorted(tasks, key=lambda task: task["task_id"]),
    }, "judgments_sha256")
    _ensure_safe(grades, "grades")
    _ensure_safe(judgments, "judgments")
    return grades, judgments


def _evidence_scope(execution: dict) -> str:
    # claude-code/1 keeps the label bakeoff 10 sealed (T-024); its report
    # states the mislabel. The successor adapter names what the plan pins.
    if execution["adapter"] != AGENTIC_ADAPTER:
        return "synthetic-integration-only"
    return f"live:{execution['model']}:{execution['binary_version']}:{execution['binary_sha256'][:12]}"


def _make_summary(plan: dict, trials: list[dict], grades: dict, judgments: dict,
                  partial: bool = False) -> dict:
    variants = {}
    variant_ids = {trial["variant_id"] for trial in trials}
    if partial:
        variant_ids |= {case["variant_id"] for case in plan["cases"]}
    for variant_id in sorted(variant_ids):
        variant_rows = [row for row in grades["rows"] if row["variant_id"] == variant_id]
        measures = {}
        for measure_id in sorted({row["measure_id"] for row in variant_rows}):
            measure_rows = [row for row in variant_rows if row["measure_id"] == measure_id]
            measures[measure_id] = {
                "passes": sum(row["passed"] for row in measure_rows),
                "checks": len(measure_rows),
            }
        variants[variant_id] = {
            "trials": sum(trial["variant_id"] == variant_id for trial in trials),
            "deterministic_measures": measures,
        }
        if partial:
            variants[variant_id]["planned"] = sum(case["variant_id"] == variant_id for case in plan["cases"])
    body = {
        "schema": SUMMARY_SCHEMA,
        "campaign_id": plan["campaign_id"],
        "plan_sha256": plan["plan_sha256"],
        "trial_sha256s": [trial["trial_sha256"] for trial in trials],
        "grades_sha256": grades["grades_sha256"],
        "judgments_sha256": judgments["judgments_sha256"],
        "trial_count": len(trials),
        "pending_judgment_count": len(judgments["tasks"]),
        "variants": variants,
        "evidence_scope": _evidence_scope(plan["execution"]),
        "decision_status": "judgment-required" if judgments["tasks"] else "descriptive-only",
    }
    if partial:
        recorded = {trial["trial_id"] for trial in trials}
        repetitions = sorted({case["repetition"] for case in plan["cases"]})
        complete = [
            repetition for repetition in repetitions
            if all(case["trial_id"] in recorded for case in plan["cases"] if case["repetition"] == repetition)
        ]
        body.update({
            "partial": True,
            "planned_cases": len(plan["cases"]),
            "recorded_cases": len(trials),
            "repetitions": len(repetitions),
            "complete_repetitions": len(complete),
            "truncated": len(complete) < len(repetitions),
        })
    summary = _seal(body, "summary_sha256")
    _ensure_safe(summary, "summary")
    return summary


def grade_partial(run_dir: Path, out_dir: Path) -> dict:
    """Grade the trials a live run has recorded so far, into a directory beside it.

    The output carries the sealed plan (byte copy), grades, the blind judgment
    export, and a summary marked `partial`; `clause_judge.py run` accepts it.
    It is not a run directory and `verify` will not accept it as one.
    """
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError("run directory must be a regular directory")
    if out_dir.resolve() == run_dir.resolve() or run_dir.resolve() in out_dir.resolve().parents:
        raise ValueError("partial grades must be written outside the run directory")
    plan_bytes = (run_dir / "plan.json").read_bytes()
    plan = _read_canonical(run_dir / "plan.json", "plan")
    _validate_plan(plan)
    if plan["execution"]["adapter"] not in LIVE_ADAPTERS:
        raise ValueError("grade-partial applies to live runs only")
    trials = []
    for case in plan["cases"]:
        path = run_dir / "trials" / f"{case['trial_id']}.json"
        if path.is_file() and not path.is_symlink():
            trials.append(_load_one_trial(path, plan, case))
    if not trials:
        raise ValueError("no trial has been recorded yet")
    grades, judgments = _grade_artifacts(plan, trials)
    summary = _make_summary(plan, trials, grades, judgments, partial=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_immutable_bytes(out_dir / "plan.json", plan_bytes)
    _write_immutable(out_dir / "grades.json", grades)
    _write_immutable(out_dir / "judgments.json", judgments)
    _write_immutable(out_dir / "summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="validate and print the immutable plan")
    check.add_argument("declaration", type=Path)
    exercise = commands.add_parser("exercise", help="run the complete campaign lifecycle")
    exercise.add_argument("declaration", type=Path)
    exercise.add_argument("--run-dir", required=True, type=Path)
    exercise.add_argument(
        "--authorization", type=Path,
        help=f"{AUTHORIZATION_SCHEMA} file naming the plan hash; required by {' and '.join(LIVE_ADAPTERS)}",
    )
    exercise.add_argument(
        "--deadline-utc",
        help="ISO 8601 instant with timezone; no new trial is dispatched at or after it",
    )
    verify = commands.add_parser("verify", help="rederive and verify a completed run")
    verify.add_argument("run_dir", type=Path)
    partial = commands.add_parser("grade-partial", help="grade the trials a live run has recorded so far")
    partial.add_argument("run_dir", type=Path)
    partial.add_argument("--out", required=True, type=Path, help="output directory outside the run")
    shim = commands.add_parser("shim-check", help="prove the sandbox shim confines the interpreter (Darwin)")
    shim.add_argument("--python", help="interpreter path; default: the real path of python3 on PATH")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            result = ClauseCampaign.load(args.declaration).plan()
        elif args.command == "exercise":
            result = ClauseCampaign.load(args.declaration).exercise(
                args.run_dir, args.authorization, args.deadline_utc
            )
        elif args.command == "grade-partial":
            result = grade_partial(args.run_dir, args.out)
        elif args.command == "shim-check":
            result = shim_check(args.python)
        else:
            result = ClauseCampaign.verify(args.run_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
