"""Promptfoo provider for isolated Claude Code clause variants (bakeoff 6)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parent
PROJECT = CAMPAIGN.parent.parent
sys.path.insert(0, str(PROJECT / "scripts"))

from harness_common import isolated_environment, parse_stream_json, sha256_file  # noqa: E402
from run_eval import ancestor_instruction_files, claude_args, verifies_opus_5  # noqa: E402

ARMS = {"control", "guarded-subtractive-v2"}
VARIANT_FILES = {
    "control": None,
    "guarded-subtractive-v2": "variants/guarded-subtractive-v2.md",
}
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def artifact_dir(task_id: str, repetition: int, arm: str) -> Path:
    if not SAFE_ID.fullmatch(task_id) or arm not in ARMS or repetition < 1:
        raise ValueError("unsafe bakeoff artifact identity")
    root = Path(os.environ["BAKEOFF6_OUT_DIR"]).resolve() / "responses"
    path = (root / f"{task_id}-r{repetition}-{arm}").resolve()
    if path.parent != root:
        raise ValueError("bakeoff artifact path escapes output root")
    return path


def cli_version() -> str:
    proc = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, errors="replace", timeout=10
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"could not read Claude Code version: {proc.stderr.strip()}")
    return proc.stdout.strip()


def variant_path(variant_file: str) -> Path:
    source = (CAMPAIGN / variant_file).resolve()
    if source.parent != (CAMPAIGN / "variants").resolve() or not source.is_file():
        raise ValueError("invalid campaign variant file")
    return source


def clause_sha256(variant_file: str | None) -> str | None:
    return sha256_file(variant_path(variant_file)) if variant_file else None


def materialize(workdir: Path, variant_file: str | None) -> str | None:
    workdir.mkdir(parents=True, exist_ok=False)
    if not variant_file:
        return None
    source = variant_path(variant_file)
    target = workdir / "CLAUDE.md"
    shutil.copyfile(source, target)
    return sha256_file(target)


def response_provenance(
    task_id: str,
    repetition: int,
    arm: str,
    cli: str,
    prompt: str,
    variant_file: str | None,
) -> dict:
    return {
        "task_id": task_id,
        "repetition": repetition,
        "arm": arm,
        "claude_version": cli,
        "requested_model": "opus",
        "requested_effort": "high",
        "clause_sha256": clause_sha256(variant_file),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    }


def load_cached(path: Path, expected: dict) -> dict | None:
    meta_path = path / "meta.json"
    payload_path = path / "response.json"
    raw_path = path / "stdout.jsonl"
    if not all(item.is_file() for item in (meta_path, payload_path, raw_path)):
        return None
    meta = json.loads(meta_path.read_text())
    for key, value in expected.items():
        if meta.get(key) != value:
            raise ValueError(f"cached response provenance mismatch for {key}")
    if meta.get("raw_sha256") != sha256_file(raw_path):
        raise ValueError("cached raw response hash mismatch")
    if meta.get("response_sha256") != sha256_file(payload_path):
        raise ValueError("cached parsed response hash mismatch")
    payload = json.loads(payload_path.read_text())
    if parse_stream_json(raw_path.read_text(), source="cached bakeoff stream") != payload:
        raise ValueError("cached response does not match raw stream")
    if not verifies_opus_5(payload):
        raise ValueError("cached answer model is not Opus 5")
    return {"output": payload["result"], "cached": True}


def archive_incomplete(path: Path) -> None:
    attempt = 1
    while path.with_name(f"{path.name}.failed-{attempt}").exists():
        attempt += 1
    path.rename(path.with_name(f"{path.name}.failed-{attempt}"))


def call_api(prompt: str, options: dict, context: dict) -> dict:
    config = options.get("config") or {}
    arm = config.get("arm")
    if arm not in ARMS:
        return {"error": f"unknown arm: {arm!r}"}
    task_id = context.get("vars", {}).get("task_id")
    repetition = int(context.get("repeatIndex", 0)) + 1
    expected_cli = os.environ.get("BAKEOFF6_CLAUDE_VERSION")
    if not expected_cli:
        return {"error": "BAKEOFF6_CLAUDE_VERSION is required"}
    try:
        current_cli = cli_version()
        if current_cli != expected_cli:
            raise RuntimeError(f"Claude CLI drift: {current_cli!r} != {expected_cli!r}")
        output_dir = artifact_dir(task_id, repetition, arm)
        variant_file = config.get("variant_file")
        if variant_file != VARIANT_FILES[arm]:
            raise ValueError("provider variant does not match the frozen arm definition")
        expected = response_provenance(
            task_id, repetition, arm, expected_cli, prompt, variant_file
        )
        cached = load_cached(output_dir, expected)
        if cached:
            return cached
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        if output_dir.exists():
            archive_incomplete(output_dir)
        with tempfile.TemporaryDirectory(
            prefix=f".{output_dir.name}.attempt-", dir=output_dir.parent
        ) as staging_name:
            staging = Path(staging_name)
            with tempfile.TemporaryDirectory(prefix="opus5-clause-bakeoff6-") as temporary:
                workdir = Path(temporary).resolve() / "project"
                clause_hash = materialize(workdir, variant_file)
                if clause_hash != expected["clause_sha256"]:
                    raise RuntimeError("variant changed while preparing the response")
                ambient = ancestor_instruction_files(workdir)
                expected_local = workdir / "CLAUDE.md"
                ambient = [item for item in ambient if Path(item) != expected_local]
                if ambient:
                    raise RuntimeError(f"ambient CLAUDE.md files found: {ambient}")
                started = time.monotonic()
                proc = subprocess.run(
                    claude_args("opus", "high", prompt),
                    cwd=workdir,
                    env=isolated_environment(),
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=300,
                )
            raw_path = staging / "stdout.jsonl"
            raw_path.write_text(proc.stdout)
            if proc.stderr:
                (staging / "stderr.txt").write_text(proc.stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[-500:]}")
            payload = parse_stream_json(proc.stdout, source="bakeoff response stream")
            if not verifies_opus_5(payload):
                raise RuntimeError("bakeoff answer model is not verified as Opus 5")
            payload_path = staging / "response.json"
            payload_path.write_text(json.dumps(payload, indent=2) + "\n")
            meta = {
                **expected,
                "answer_models": payload.get("_answer_models"),
                "raw_sha256": sha256_file(raw_path),
                "response_sha256": sha256_file(payload_path),
                "duration_sec": round(time.monotonic() - started, 3),
            }
            (staging / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
            staging.rename(output_dir)
        return {"output": payload["result"], "cached": False}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
