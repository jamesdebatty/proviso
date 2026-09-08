"""Shared parsing and path-safety helpers for eval artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

TRIAL_ID = re.compile(r"^[a-z0-9][a-z0-9-]*-r[1-9][0-9]*-[12]-(?:control|ste)$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def isolated_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    env.pop("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", None)
    return env


def parse_stream_json(raw: str, *, source: str = "stream") -> dict:
    final = None
    init_model = None
    answer_models = set()
    final_count = 0
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid {source} JSON at line {line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"invalid {source} JSON at line {line_number}: expected object")
        if item.get("type") == "system" and item.get("subtype") == "init":
            init_model = item.get("model")
        if item.get("type") == "assistant" and isinstance(item.get("message"), dict):
            model = item["message"].get("model")
            if isinstance(model, str):
                answer_models.add(model)
        if item.get("type") == "result":
            final = item
            final_count += 1
    if not isinstance(final, dict) or final_count != 1:
        raise ValueError(f"{source} must contain exactly one final result object")
    final["_init_model"] = init_model
    final["_answer_models"] = sorted(answer_models)
    return final


def answer_from_payload(payload: dict) -> str:
    value = payload.get("result") or payload.get("response") or ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def safe_trial_file(run_dir: Path, trial_id: str, filename: str) -> Path:
    if not TRIAL_ID.fullmatch(trial_id):
        raise ValueError(f"unsafe trial id: {trial_id!r}")
    if filename not in {"stdout.json", "stdout.jsonl"}:
        raise ValueError(f"unsafe trial artifact name: {filename!r}")
    trials_root = (run_dir / "trials").resolve()
    path = (trials_root / trial_id / filename).resolve()
    if path.parent.parent != trials_root:
        raise ValueError(f"trial path escapes run directory: {trial_id!r}")
    return path


def safe_trial_stdout(run_dir: Path, trial_id: str) -> Path:
    return safe_trial_file(run_dir, trial_id, "stdout.json")


def validated_response_payload(run_dir: Path, record: dict) -> dict:
    trial_id = record.get("trial_id")
    raw_path = safe_trial_file(run_dir, trial_id, "stdout.jsonl")
    parsed_path = safe_trial_file(run_dir, trial_id, "stdout.json")
    if record.get("raw_stdout_sha256") != sha256_file(raw_path):
        raise ValueError(f"raw response hash mismatch: {trial_id}")
    if record.get("parsed_stdout_sha256") != sha256_file(parsed_path):
        raise ValueError(f"parsed response hash mismatch: {trial_id}")
    reconstructed = parse_stream_json(raw_path.read_text(), source=f"response {trial_id}")
    parsed = json.loads(parsed_path.read_text())
    if reconstructed != parsed:
        raise ValueError(f"parsed response does not match raw stream: {trial_id}")
    return parsed
