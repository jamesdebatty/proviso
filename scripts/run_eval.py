#!/usr/bin/env python3
"""Historical control/STE generator. Use execution.py for the active path."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from harness_common import (
    TRIAL_ID,
    isolated_environment,
    parse_stream_json,
    sha256_file,
    text_output,
)

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_PATH = ROOT / "config" / "prompts.jsonl"
ARMS_PATH = ROOT / "config" / "arms.json"
RESULTS_ROOT = ROOT / "results" / "runs"
DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "high"
DEFAULT_REPETITIONS = 3
DEFAULT_TIMEOUT = 300
sha256 = sha256_file


def load_prompts() -> list[dict]:
    prompts = []
    for line_number, line in enumerate(PROMPTS_PATH.read_text().splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not item.get("id") or not item.get("prompt") or not item.get("must_cover"):
            raise ValueError(f"invalid prompt at line {line_number}")
        prompts.append(item)
    ids = [item["id"] for item in prompts]
    if len(ids) != len(set(ids)):
        raise ValueError("prompt ids must be unique")
    return prompts


def load_arms() -> dict:
    arms = json.loads(ARMS_PATH.read_text())
    if set(arms) != {"control", "ste"}:
        raise ValueError("arms.json must define exactly control and ste")
    return arms


def select_prompts(prompts: list[dict], wanted: list[str]) -> list[dict]:
    if not wanted:
        return prompts
    by_id = {item["id"]: item for item in prompts}
    missing = [item for item in wanted if item not in by_id]
    if missing:
        raise ValueError(f"unknown prompt id(s): {', '.join(missing)}")
    return [by_id[item] for item in wanted]


def planned_trials(prompts: list[dict], repetitions: int) -> list[dict]:
    trials = []
    for prompt_index, prompt in enumerate(prompts):
        for repetition in range(1, repetitions + 1):
            order = ("control", "ste") if (prompt_index + repetition) % 2 else ("ste", "control")
            for position, arm in enumerate(order, 1):
                trials.append(
                    {
                        "prompt_id": prompt["id"],
                        "category": prompt["category"],
                        "repetition": repetition,
                        "position": position,
                        "arm": arm,
                    }
                )
    return trials


def claude_args(model: str, effort: str, prompt: str) -> list[str]:
    return [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--effort",
        effort,
        "--tools",
        "",
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--prompt-suggestions",
        "false",
    ]


def isolated_env() -> dict[str, str]:
    return isolated_environment()


def materialize(workdir: Path, arm: str, arms: dict) -> dict:
    workdir.mkdir(parents=True, exist_ok=False)
    source = arms[arm]["claude_md"]
    copied = None
    if source:
        source_path = ROOT / source
        copied = workdir / "CLAUDE.md"
        shutil.copyfile(source_path, copied)
    files = sorted(str(path.relative_to(workdir)) for path in workdir.rglob("*") if path.is_file())
    return {
        "files_before": files,
        "claude_md_sha256": sha256(copied) if copied else None,
    }


def extract_models(payload: dict) -> list[str]:
    usage = payload.get("modelUsage") or payload.get("model_usage") or {}
    if isinstance(usage, dict):
        return sorted(str(key) for key in usage)
    return []


def answer_model(payload: dict) -> str | None:
    models = payload.get("_answer_models") or []
    if isinstance(models, list) and len(models) == 1 and isinstance(models[0], str):
        return models[0]
    return None


def verifies_opus_5(payload: dict) -> bool:
    model = answer_model(payload)
    return bool(model and "opus-5" in model.lower())


def ancestor_instruction_files(workdir: Path) -> list[str]:
    found = []
    for directory in (workdir, *workdir.parents):
        for relative in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            candidate = directory / relative
            if candidate.is_file():
                found.append(str(candidate))
    return found


def failure_threshold_exceeded(error_count: int, planned_count: int) -> bool:
    if planned_count < 1 or error_count < 0:
        raise ValueError("counts must be non-negative and planned_count must be positive")
    return error_count / planned_count > 0.10


def cli_version_changed(expected: str, observed: str) -> bool:
    return expected != observed


def authentication_failed(*outputs: str) -> bool:
    message = "\n".join(outputs).lower()
    markers = (
        "authentication failed",
        "not authenticated",
        "not logged in",
        "please run /login",
        "unauthorized",
        "invalid api key",
        "invalid oauth",
    )
    return any(marker in message for marker in markers)


def stop_status(record: dict, error_count: int, planned_count: int) -> str | None:
    terminal = {
        "authentication": "stopped_on_authentication_failure",
        "model_mismatch": "stopped_on_model_mismatch",
    }
    if record.get("failure_kind") in terminal:
        return terminal[record["failure_kind"]]
    if failure_threshold_exceeded(error_count, planned_count):
        return "stopped_on_failure_threshold"
    return None


def run_trial(
    run_dir: Path,
    trial: dict,
    prompt: dict,
    arms: dict,
    args: argparse.Namespace,
    current_cli_version: str,
) -> dict:
    trial_id = f'{trial["prompt_id"]}-r{trial["repetition"]}-{trial["position"]}-{trial["arm"]}'
    if not TRIAL_ID.fullmatch(trial_id):
        raise ValueError(f"unsafe trial id: {trial_id!r}")
    trial_dir = run_dir / "trials" / trial_id
    trial_dir.mkdir(parents=True, exist_ok=False)
    command = claude_args(args.model, args.effort, prompt["prompt"])
    with tempfile.TemporaryDirectory(prefix="opus5-ste-") as temporary:
        workdir = Path(temporary).resolve()
        setup = materialize(workdir / "project", trial["arm"], arms)
        workdir = workdir / "project"
        ancestors = ancestor_instruction_files(workdir)
        if trial["arm"] == "ste":
            ancestors = [path for path in ancestors if Path(path) != workdir / "CLAUDE.md"]
        if ancestors:
            raise RuntimeError(f"ambient CLAUDE.md files found: {ancestors}")
        started = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=workdir,
                env=isolated_env(),
                capture_output=True,
                text=True,
                errors="replace",
                timeout=args.timeout,
            )
            error = None
        except subprocess.TimeoutExpired as exc:
            proc = None
            error = f"timeout after {args.timeout}s"
            stdout = text_output(exc.stdout)
            stderr = text_output(exc.stderr)
    duration = round(time.monotonic() - started, 3)
    if proc is not None:
        stdout, stderr = proc.stdout, proc.stderr
    (trial_dir / "stdout.jsonl").write_text(stdout, encoding="utf-8")
    raw_stdout_path = trial_dir / "stdout.jsonl"
    parsed_stdout_path = trial_dir / "stdout.json"
    if stderr:
        (trial_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    payload = None
    if not error:
        if proc.returncode != 0:
            error = f"claude exited {proc.returncode}"
        else:
            try:
                payload = parse_stream_json(stdout, source="agent stream")
                parsed_stdout_path.write_text(json.dumps(payload, indent=2) + "\n")
            except (json.JSONDecodeError, ValueError) as exc:
                error = f"invalid stream output: {exc}"
    if not error and not verifies_opus_5(payload or {}):
        error = f"answer model is not verified as Opus 5: {answer_model(payload or {})!r}"
    failure_kind = None
    if error:
        if authentication_failed(stdout, stderr):
            failure_kind = "authentication"
        elif error.startswith("answer model is not verified as Opus 5"):
            failure_kind = "model_mismatch"
        else:
            failure_kind = "trial_error"
    record = {
        **trial,
        "trial_id": trial_id,
        "duration_sec": duration,
        "exit_code": proc.returncode if proc is not None else None,
        "error": error,
        "failure_kind": failure_kind,
        "raw_stdout_sha256": sha256(raw_stdout_path),
        "parsed_stdout_sha256": (
            sha256(parsed_stdout_path) if payload is not None and parsed_stdout_path.is_file() else None
        ),
        "requested_model": args.model,
        "requested_effort": args.effort,
        "resolved_models": extract_models(payload or {}),
        "answer_model": answer_model(payload or {}),
        "opus_5_verified": verifies_opus_5(payload or {}),
        "prompt_sha256": hashlib.sha256(prompt["prompt"].encode()).hexdigest(),
        "claude_version": current_cli_version,
        **setup,
    }
    (trial_dir / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def cli_version() -> str:
    proc = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, errors="replace", timeout=10
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"could not read Claude Code version: {proc.stderr.strip()}")
    return proc.stdout.strip()


def write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(path)


def freeze_inputs(run_dir: Path) -> dict[str, str]:
    inputs = run_dir / "inputs"
    inputs.mkdir()
    source_paths = {
        "prompts.jsonl": PROMPTS_PATH,
        "arms.json": ARMS_PATH,
        "human-review-sample.json": ROOT / "config" / "human-review-sample.json",
        "rubric.md": ROOT / "grader" / "rubric.md",
        "preregistration.md": ROOT / "notes" / "preregistration-2026-08-04.md",
        "treatment-CLAUDE.md": ROOT / "treatment" / "CLAUDE.md",
        "run_eval.py": Path(__file__),
        "judge_eval.py": ROOT / "scripts" / "judge_eval.py",
        "score_eval.py": ROOT / "scripts" / "score_eval.py",
        "harness_common.py": ROOT / "scripts" / "harness_common.py",
        "human_review.py": ROOT / "scripts" / "human_review.py",
    }
    hashes = {}
    for name, source in source_paths.items():
        target = inputs / name
        shutil.copyfile(source, target)
        hashes[name] = sha256(target)
    return hashes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Historical control/STE generator; bakeoff 9 does not use this command."
    )
    parser.add_argument("--execute", action="store_true", help="perform live model calls")
    parser.add_argument("--dry-run", action="store_true", help="print the trial plan only")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--prompt-id", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1 or args.timeout < 1:
        raise ValueError("repetitions and timeout must be positive")
    prompts = select_prompts(load_prompts(), args.prompt_id)
    arms = load_arms()
    trials = planned_trials(prompts, args.repetitions)
    args.model = DEFAULT_MODEL
    args.effort = DEFAULT_EFFORT
    plan = {
        "requested_model": args.model,
        "requested_effort": args.effort,
        "prompt_count": len(prompts),
        "repetitions": args.repetitions,
        "trial_count": len(trials),
        "trials": trials,
    }
    if args.dry_run or not args.execute:
        print(json.dumps(plan, indent=2))
        if not args.dry_run:
            print("\nNo calls made. Add --execute to run live trials.", file=sys.stderr)
        return 0

    version_before = cli_version()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / f"opus5-ste-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    frozen_input_hashes = freeze_inputs(run_dir)
    prompt_map = {item["id"]: item for item in prompts}
    records = []
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "claude_version_before": version_before,
        "claude_version_after": None,
        "cli_stable": None,
        "requested_model": args.model,
        "requested_effort": args.effort,
        "frozen_input_hashes": frozen_input_hashes,
        "setting_sources": ["project"],
        "auto_memory_disabled": True,
        "prompt_suggestions_disabled": True,
        "external_workdirs": True,
        "planned_trial_count": len(trials),
        "trial_count": 0,
        "errors": 0,
        "failure_stop_threshold": 0.10,
        "records": records,
    }
    manifest_path = run_dir / "manifest.json"
    write_manifest(manifest_path, manifest)
    for index, trial in enumerate(trials, 1):
        current_version = cli_version()
        if cli_version_changed(version_before, current_version):
            manifest["status"] = "stopped_on_cli_drift"
            manifest["cli_version_after"] = current_version
            manifest["cli_stable"] = False
            write_manifest(manifest_path, manifest)
            break
        print(f'[{index}/{len(trials)}] {trial["prompt_id"]} r{trial["repetition"]} {trial["arm"]}', flush=True)
        record = run_trial(
            run_dir,
            trial,
            prompt_map[trial["prompt_id"]],
            arms,
            args,
            current_version,
        )
        records.append(record)
        manifest["trial_count"] = len(records)
        manifest["errors"] = sum(bool(item["error"]) for item in records)
        write_manifest(manifest_path, manifest)
        terminal_status = stop_status(record, manifest["errors"], len(trials))
        if terminal_status:
            manifest["status"] = terminal_status
            write_manifest(manifest_path, manifest)
            break
    version_after = cli_version()
    manifest["claude_version_after"] = version_after
    manifest["cli_stable"] = version_before == version_after
    complete = len(records) == len(trials) and not manifest["errors"] and manifest["cli_stable"]
    if complete:
        manifest["status"] = "complete"
    elif manifest["status"] == "running":
        manifest["status"] = "complete_with_errors"
    write_manifest(manifest_path, manifest)
    print(run_dir)
    return 0 if manifest["status"] == "complete" and manifest["cli_stable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
