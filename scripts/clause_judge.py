#!/usr/bin/env python3
"""Blind judging for a clause-campaign/1 run's `judgments.json` export.

A judge sees one task at a time: the measure's question, its rubric, the task
prompt, and the response. It never sees a variant, trial, or campaign
identity, and this module never reads anything from the run directory except
the blind export. Results are written beside the run, not inside it, so the
run directory stays exactly what `clause_campaign.py verify` expects.

Two transports, both pinned binaries chosen by the campaign at authorization:

- `codex`: Codex CLI `exec --json --output-schema`, model `gpt-5.6-sol`,
  reasoning effort high. The session rollout is retained and its
  `turn_context.model` must equal the requested model.
- `claude`: Claude Code print mode with `--json-schema`, model
  `claude-sonnet-5`, effort high, no tools. The stream's assistant `model`
  must equal the requested model.

Every result is sealed and re-derivable from its retained raw stream; `verify`
rechecks that. Any string the transports return is refused if it carries
credential-shaped text, the same policy the campaign module applies.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from capture_spine import redact
from clause_campaign import (
    AUTH_FAILURE_MARKERS, _digest, _digest_bytes, _exact_keys, _file_digest, _pretty, _read_canonical,
    _require_mapping, _require_string, _seal, _verify_seal, _write_immutable,
    _write_immutable_bytes, _strict_credential_hit, child_environment,
)


class JudgeError(RuntimeError):
    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind



def _final_result_is_error(raw: str) -> bool:
    """True only when the stream's final `result` event says `is_error: true`.

    Bakeoff 11's first Sonnet pass refused 196 successful tasks because a
    transient API-error event earlier in the stream matched a whole-stream
    regex; only the final result decides.
    """
    final = None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            final = event
    return final is None or bool(final.get("is_error"))

def _refuse_failed_transport(judge: str, proc: subprocess.CompletedProcess) -> None:
    # An authentication failure is a run-level condition (bakeoff 10 attempts 1
    # and 2 died on a stale token in the shell); it must stop the run rather
    # than be recorded once per task.
    # Codex streams carry no `result` event; only the Claude transport is
    # checked for a final `is_error`.
    if proc.returncode == 0 and (judge != "claude" or not _final_result_is_error(proc.stdout)):
        return
    lowered = f"{proc.stdout}\n{proc.stderr}".lower()
    kind = "authentication" if any(marker in lowered for marker in AUTH_FAILURE_MARKERS) else "error"
    tail = redact(proc.stderr[-500:] + ("\n--- stdout ---\n" + proc.stdout[-700:] if proc.stdout else ""))
    raise JudgeError(kind, f"{judge} judge exited {proc.returncode} ({kind}): {tail}")

RESULT_SCHEMA = "clause-judgment/1"
JUDGES = {
    "codex": {"vendor": "OpenAI", "model": "gpt-5.6-sol", "effort": "high"},
    "claude": {"vendor": "Anthropic", "model": "claude-sonnet-5", "effort": "high"},
}
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "excerpts": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["label", "excerpts", "reason"],
}


def judge_prompt(task: dict) -> str:
    return (
        "You are a blind judge. Answer only the question below about the response, "
        "applying the rubric exactly. Return a JSON object with three fields: "
        "`label` (one of the labels the rubric names), `excerpts` (the exact passages "
        "or list entries the rubric asks you to return, or an empty list), and "
        "`reason` (within the rubric's word limit). Return nothing else.\n\n"
        f"Question: {task['question']}\n\n"
        f"Rubric:\n{task['rubric']}\n\n"
        f"Task prompt the response answered:\n<prompt>\n{task['prompt']}\n</prompt>\n\n"
        f"Response to judge:\n<response>\n{task['response']}\n</response>\n"
    )


def _parse_judgment(value: object) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("judgment is not a JSON object")
    _exact_keys(value, {"label", "excerpts", "reason"}, "judgment")
    _require_string(value["label"], "judgment.label")
    _require_string(value["reason"], "judgment.reason")
    if not isinstance(value["excerpts"], list) or not all(isinstance(x, str) for x in value["excerpts"]):
        raise ValueError("judgment.excerpts must be a list of strings")
    return {"label": value["label"], "excerpts": list(value["excerpts"]), "reason": value["reason"]}


def parse_codex_stream(raw: str) -> dict:
    messages, completed = [], False
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError(f"codex stream line {number} is not an object")
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) \
                and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            messages.append(item["text"])
        if event.get("type") == "turn.completed":
            completed = True
    if not completed:
        raise ValueError("codex stream has no completed turn")
    if len(messages) != 1:
        raise ValueError(f"codex stream must carry exactly one agent message, found {len(messages)}")
    return _parse_judgment(messages[0])


def codex_rollout_model(raw: str) -> str:
    models = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict) and item.get("type") == "turn_context":
            payload = item.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("model"), str):
                models.add(payload["model"])
    if len(models) != 1:
        raise ValueError(f"rollout must record exactly one model, found {sorted(models)}")
    return models.pop()


def parse_claude_stream(raw: str) -> tuple[dict, str]:
    from harness_common import parse_stream_json
    payload = parse_stream_json(raw, source="claude judge stream")
    models = payload["_answer_models"]
    if len(models) != 1:
        raise ValueError(f"claude judge stream names {len(models)} answer models")
    return _parse_judgment(payload.get("result")), models[0]


def _binary_version(binary: Path) -> str:
    proc = subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                          errors="replace", timeout=30)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"cannot read version of {binary}: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def _refuse_unsafe(text: str, label: str) -> None:
    # The judge stream and the Codex rollout quote the task prompt, the rubric,
    # the response, and the transport's own built-in instructions, all prose.
    # Only an unmistakable credential shape (STRICT_CREDENTIAL_PATTERNS in
    # clause_campaign) or a reminder payload refuses the record; the capture
    # spine's word-keyed sanitizer would reject Codex 0.147.0's own instructions
    # ("basic confirmations") and any answer that names an Idempotency-Key header.
    if _strict_credential_hit(text) or "<system-reminder>" in text.lower():
        raise ValueError(f"{label} carries a credential shape or reminder text; not retained")


def judge_one(task: dict, judge: str, binary: Path, out_dir: Path, timeout: int = 900) -> dict:
    spec = JUDGES[judge]
    record_path = out_dir / f"{task['task_id']}.json"
    if record_path.exists():
        return load_result(record_path, task, judge)
    version = _binary_version(binary)
    prompt = judge_prompt(task)
    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started = time.monotonic()
    rollout: bytes | None = None
    with tempfile.TemporaryDirectory(prefix=f"clause-judge-{judge}-") as temporary:
        base = Path(temporary)
        cwd = base / "workdir"
        cwd.mkdir()
        # Allow-listed (clause_campaign.CHILD_ENV_ALLOWLIST): the shell's
        # CLAUDE_CODE_OAUTH_TOKEN and every other unlisted name never reach the judge.
        env = child_environment()
        if judge == "codex":
            home = base / "codex-home"
            home.mkdir()
            auth = Path.home() / ".codex" / "auth.json"
            if not auth.is_file():
                raise RuntimeError("~/.codex/auth.json is required for the Codex judge")
            shutil.copyfile(auth, home / "auth.json")
            schema_path = base / "schema.json"
            schema_path.write_text(json.dumps(OUTPUT_SCHEMA, indent=2) + "\n")
            env["CODEX_HOME"] = str(home)
            command = [
                str(binary), "exec", "--skip-git-repo-check", "-s", "read-only",
                "-m", spec["model"], "-c", f'model_reasoning_effort="{spec["effort"]}"',
                "--json", "--output-schema", str(schema_path), prompt,
            ]
        else:
            command = [
                str(binary), "-p", prompt,
                "--json-schema", json.dumps(OUTPUT_SCHEMA, separators=(",", ":")),
                "--output-format", "stream-json", "--verbose",
                "--model", spec["model"], "--effort", spec["effort"],
                "--tools", "", "--setting-sources", "project",
                "--settings", '{"autoMemoryEnabled":false}',
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--permission-mode", "dontAsk", "--no-session-persistence",
                "--prompt-suggestions", "false",
            ]
        proc = subprocess.run(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, errors="replace", timeout=timeout)
        _refuse_failed_transport(judge, proc)
        if judge == "codex":
            rollouts = sorted((base / "codex-home" / "sessions").rglob("rollout-*.jsonl"))
            if len(rollouts) != 1:
                raise RuntimeError(f"expected exactly one codex rollout, found {len(rollouts)}")
            rollout = rollouts[0].read_bytes()
    duration = round(time.monotonic() - started, 3)
    raw = proc.stdout
    _refuse_unsafe(raw, "judge stream")
    if judge == "codex":
        judgment = parse_codex_stream(raw)
        _refuse_unsafe(rollout.decode("utf-8", "replace"), "codex rollout")
        resolved = codex_rollout_model(rollout.decode("utf-8", "replace"))
    else:
        judgment, resolved = parse_claude_stream(raw)
    if resolved != spec["model"]:
        raise ValueError(f"{judge} judge resolved to {resolved!r}, not {spec['model']!r}")
    body = {
        "schema": RESULT_SCHEMA,
        "task_id": task["task_id"],
        "task_sha256": task["task_sha256"],
        "measure_id": task["measure_id"],
        "judge": judge,
        "vendor": spec["vendor"],
        "requested_model": spec["model"],
        "resolved_model": resolved,
        "effort": spec["effort"],
        "transport_version": version,
        "raw_sha256": _digest_bytes(raw.encode("utf-8")),
        "rollout_sha256": _digest_bytes(rollout) if rollout is not None else None,
        "started_utc": started_utc,
        "duration_sec": duration,
        "judgment": judgment,
    }
    record = _seal(body, "record_sha256")
    _write_immutable_bytes(out_dir / f"{task['task_id']}.stdout.jsonl", raw.encode("utf-8"))
    if rollout is not None:
        _write_immutable_bytes(out_dir / f"{task['task_id']}.rollout.jsonl", rollout)
    _write_immutable(record_path, record)
    return record


def load_result(record_path: Path, task: dict, judge: str) -> dict:
    label = f"judgment {task['task_id']} ({judge})"
    record = _read_canonical(record_path, label)
    _verify_seal(record, "record_sha256", label)
    if record.get("schema") != RESULT_SCHEMA or record.get("judge") != judge:
        raise ValueError(f"{label}: wrong schema or judge")
    if record.get("task_sha256") != task["task_sha256"] or record.get("measure_id") != task["measure_id"]:
        raise ValueError(f"{label}: does not belong to this task")
    raw_path = record_path.with_name(f"{task['task_id']}.stdout.jsonl")
    raw = raw_path.read_bytes()
    if _digest_bytes(raw) != record.get("raw_sha256"):
        raise ValueError(f"{label}: raw stream does not match its record")
    if judge == "codex":
        rollout = record_path.with_name(f"{task['task_id']}.rollout.jsonl").read_bytes()
        if _digest_bytes(rollout) != record.get("rollout_sha256"):
            raise ValueError(f"{label}: rollout does not match its record")
        rederived = parse_codex_stream(raw.decode("utf-8"))
        resolved = codex_rollout_model(rollout.decode("utf-8"))
    else:
        rederived, resolved = parse_claude_stream(raw.decode("utf-8"))
    if rederived != record["judgment"] or resolved != record["resolved_model"]:
        raise ValueError(f"{label}: judgment does not rederive from its raw stream")
    if resolved != JUDGES[judge]["model"]:
        raise ValueError(f"{label}: resolved model is not the frozen one")
    return record


def load_tasks(run_dir: Path) -> tuple[dict, list[dict]]:
    export = _read_canonical(Path(run_dir) / "judgments.json", "judgments export")
    _verify_seal(export, "judgments_sha256", "judgments export")
    tasks = export["tasks"]
    for task in tasks:
        _verify_seal(task, "task_sha256", f"task {task.get('task_id')}")
        if "variant_id" in task or "trial_id" in task:
            raise ValueError("blind export carries variant or trial identity")
    return export, tasks


def run(run_dir: Path, out_root: Path, judge: str, binary: Path, workers: int,
        limit: int | None = None) -> dict:
    if judge not in JUDGES:
        raise ValueError(f"judge must be one of {', '.join(JUDGES)}")
    binary = Path(binary).expanduser()
    if binary.is_symlink() and judge == "claude" or not binary.exists():
        raise ValueError("judge binary must be a pinned copy that exists")
    export, tasks = load_tasks(run_dir)
    out_dir = Path(out_root) / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    if limit is not None:
        tasks = tasks[:limit]
    errors: list[str] = []
    stop = threading.Event()
    state = {"stop_reason": None, "not_attempted": 0}
    lock = threading.Lock()

    def work(task: dict) -> dict | None:
        if stop.is_set():
            with lock:
                state["not_attempted"] += 1
            return None
        try:
            return judge_one(task, judge, binary, out_dir)
        except Exception as exc:  # noqa: BLE001 - recorded, then surfaced together
            with lock:
                errors.append(f"{task['task_id']}: {type(exc).__name__}: {exc}")
                if isinstance(exc, JudgeError) and exc.kind == "authentication" and not state["stop_reason"]:
                    state["stop_reason"] = f"authentication: {exc}"
                    stop.set()
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = [item for item in pool.map(work, tasks) if item is not None]
    manifest = {
        "schema": "clause-judge-manifest/1",
        "judge": judge,
        **{key: JUDGES[judge][key] for key in ("vendor", "model", "effort")},
        "transport_version": _binary_version(binary),
        "binary_sha256": _file_digest(binary) if binary.is_file() else None,
        "judgments_sha256": export["judgments_sha256"],
        "tasks": len(tasks),
        "judged": len(records),
        "not_attempted": state["not_attempted"],
        "stop_reason": state["stop_reason"],
        "errors": errors,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_bytes(_pretty(manifest))
    return manifest


def verify(run_dir: Path, out_root: Path, judge: str) -> dict:
    export, tasks = load_tasks(run_dir)
    out_dir = Path(out_root) / judge
    records = {}
    missing = []
    for task in tasks:
        path = out_dir / f"{task['task_id']}.json"
        if not path.is_file():
            missing.append(task["task_id"])
            continue
        records[task["task_id"]] = load_result(path, task, judge)
    return {
        "judge": judge,
        "judgments_sha256": export["judgments_sha256"],
        "verified": len(records),
        "missing": missing,
        "labels": {task_id: record["judgment"]["label"] for task_id, record in sorted(records.items())},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("run_dir", type=Path)
        sub.add_argument("--judge", required=True, choices=sorted(JUDGES))
        sub.add_argument("--out", required=True, type=Path, help="judge output root, outside the run directory")
        if name == "run":
            sub.add_argument("--binary", required=True, type=Path)
            sub.add_argument("--workers", type=int, default=3)
            sub.add_argument("--limit", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            result = run(args.run_dir, args.out, args.judge, args.binary, args.workers, args.limit)
        else:
            result = verify(args.run_dir, args.out, args.judge)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not result.get("errors") and not result.get("missing") and not result.get("stop_reason") else 1


if __name__ == "__main__":
    raise SystemExit(main())
