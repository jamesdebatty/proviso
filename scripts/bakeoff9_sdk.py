#!/usr/bin/env python3
"""Repository-local Claude Agent SDK adapter for bakeoff 9.

The JavaScript process owns SDK wire types and emits an acknowledged stream of
sanitized boundary fragments. This module translates those fragments into the
campaign's provider-neutral ``TrajectoryRecorder`` while each hook is still
blocked, so tree snapshots preserve the real command/edit order.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import threading
import re
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping

try:
    from . import capture_spine
    from .bakeoff9_run import AdapterKind, GenerationFailure, GenerationResult
except ImportError:
    import capture_spine
    try:
        from bakeoff9_run import AdapterKind, GenerationFailure, GenerationResult
    except ImportError:  # standalone adapter tests before the core branch is merged
        from enum import Enum

        class AdapterKind(str, Enum):
            SDK_QUERY = "sdk-query"

        @dataclass(frozen=True)
        class GenerationResult:
            response: str
            usage: Mapping
            capture: Mapping

        @dataclass(frozen=True)
        class GenerationFailure:
            code: str
            detail: str
            capture: Mapping


SDK_VERSION = "0.3.233"
FRAGMENT_SCHEMA = "bakeoff9-sdk-fragment/1"
RESULT_SCHEMA = "bakeoff9-sdk-result/1"
NODE_DRIVER = Path(__file__).with_suffix(".mjs")
TOOL_SURFACE = ("Bash", "Read", "Edit", "Write", "Grep", "Glob")
LIVE_MUTABLE_SURFACES = {"system", "system_reminder"}
LIVE_INVARIANT_FIELDS = (
    "entrypoint", "model", "thinking", "output_config", "output_format", "tools_sha256",
)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SDK_BASELINE = REPO_ROOT / "sources/2026-08-24-t002-arm-baseline-sdk-declared.json"
NODE_ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
    "TZ", "TMPDIR", "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
)
LIVE_OAUTH_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
FORBIDDEN_PROVIDER_ENV = re.compile(
    r"ANTHROPIC_API_KEY|CLAUDE_API_KEY|ANTHROPIC_BASE_URL|"
    r"BEDROCK|VERTEX|FOUNDRY|GOOGLE_APPLICATION_CREDENTIALS|"
    r"GOOGLE_CLOUD_PROJECT|AWS_ACCESS|AWS_SECRET|AWS_SESSION|AWS_PROFILE|CLAUDE_CODE_USE_",
    re.I,
)


class SDKAdapterError(RuntimeError):
    """The SDK boundary could not produce complete, safe trial evidence."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_declaration(declaration: Path | Mapping) -> dict:
    if isinstance(declaration, Mapping):
        return dict(declaration)
    import tomllib

    return tomllib.loads(Path(declaration).read_text())


def node_process_env(mode: str, parent: Mapping[str, str] | None = None,
                     sandbox_temp_dir: Path | None = None) -> dict[str, str]:
    """Minimal environment for the Node host, never the caller's full process."""
    source = dict(os.environ if parent is None else parent)
    if mode == "live":
        refused = sorted(
            name for name, value in source.items()
            if value and name not in {LIVE_OAUTH_ENV, "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL"}
            and FORBIDDEN_PROVIDER_ENV.search(name)
        )
        if refused:
            raise SDKAdapterError(
                "live mode refuses alternate-provider or credential environment: "
                + ", ".join(refused)
            )
    child = {name: source[name] for name in NODE_ENV_ALLOWLIST if source.get(name) is not None}
    if mode == "live" and source.get(LIVE_OAUTH_ENV):
        child[LIVE_OAUTH_ENV] = source[LIVE_OAUTH_ENV]
    if mode != "fake":
        temp = Path(sandbox_temp_dir or "").resolve()
        if not temp.is_dir() or temp == REPO_ROOT or REPO_ROOT in temp.parents:
            raise SDKAdapterError("Node process needs an outside-repository sandbox temp directory")
        child["TMPDIR"] = str(temp) + os.sep
    return child


def build_request(
    *,
    mode: str,
    workspace: Path,
    fragment_dir: Path,
    prompt: str,
    harness_prompt: str,
    claude_executable: Path | None,
    model: str,
    fake_fixture: Path | None = None,
    system_prompt_file: Path | None = None,
    base_url: str | None = None,
    surface_verdict: str | None = None,
    observe_hooks: bool = True,
    preflight_home: Path | None = None,
    raw_body_dir: Path | None = None,
    sandbox_temp_dir: Path | None = None,
) -> dict:
    """Build and validate the JSON-only process request."""
    if mode not in {"live", "preflight", "fake"}:
        raise ValueError("mode must be live, preflight, or fake")
    workspace = Path(workspace).resolve()
    fragment_dir = Path(fragment_dir).resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    if fragment_dir == workspace or workspace in fragment_dir.parents:
        raise ValueError("fragment_dir must be outside the workspace")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty")
    if harness_prompt not in {"intact", "ablated"}:
        raise ValueError("harness_prompt must be intact or ablated")
    request = {
        "mode": mode,
        "workspace": str(workspace),
        "fragment_dir": str(fragment_dir),
        "prompt": prompt,
        "harness_prompt": harness_prompt,
        "model": model,
        "observe_hooks": bool(observe_hooks),
    }
    if mode != "fake":
        executable = Path(claude_executable or "").expanduser().resolve()
        if not executable.is_file():
            raise ValueError(f"pinned Claude executable is missing: {executable}")
        request["claude_executable"] = str(executable)
    if fake_fixture is not None:
        fixture = Path(fake_fixture).resolve()
        if not fixture.is_file():
            raise ValueError(f"fake fixture is missing: {fixture}")
        request["fake_fixture"] = str(fixture)
    if harness_prompt == "ablated":
        system = Path(system_prompt_file or "").resolve()
        if not system.is_file():
            raise ValueError("ablated mode needs a per-fixture system prompt file")
        request["system_prompt_file"] = str(system)
    if base_url is not None:
        request["base_url"] = base_url
    if mode == "preflight":
        isolated_home = Path(preflight_home or "").resolve()
        if not isolated_home.is_dir():
            raise ValueError("preflight_home must be an existing isolated directory")
        request["preflight_home"] = str(isolated_home)
    if mode != "fake":
        sandbox = Path(sandbox_temp_dir or "").resolve()
        if not sandbox.is_dir() or sandbox == workspace or workspace in sandbox.parents:
            raise ValueError("sandbox_temp_dir must be an existing directory outside the workspace")
        if sandbox == REPO_ROOT or REPO_ROOT in sandbox.parents:
            raise ValueError("sandbox_temp_dir must be outside the repository")
        request["sandbox_temp_dir"] = str(sandbox)
    if mode == "live":
        raw = Path(raw_body_dir or "").resolve()
        if not raw.is_dir() or raw == REPO_ROOT or REPO_ROOT in raw.parents:
            raise ValueError("raw_body_dir must be an existing directory outside the repository")
        if raw == workspace or workspace in raw.parents:
            raise ValueError("raw_body_dir must be outside the workspace")
        request["raw_body_dir"] = str(raw)
    if surface_verdict is not None:
        request["surface_verdict"] = surface_verdict
    return request


def fragment_problems(fragment: object) -> list[str]:
    """Validate the provider-neutral durable fragment shape."""
    if not isinstance(fragment, dict):
        return ["fragment is not an object"]
    problems = []
    if fragment.get("schema") != FRAGMENT_SCHEMA:
        problems.append(f"wrong fragment schema: {fragment.get('schema')!r}")
    if not isinstance(fragment.get("sequence"), int) or fragment["sequence"] < 0:
        problems.append("fragment sequence is not a non-negative integer")
    if fragment.get("phase") not in {"start", "finish", "failure", "denied", "batch"}:
        problems.append(f"unknown fragment phase: {fragment.get('phase')!r}")
    forbidden = {"hook_event_name", "tool_input", "tool_response", "tool_use_id", "session_id"}

    def visit(value, path=""):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in forbidden:
                    problems.append(f"{path}/{key}: SDK wire field escaped")
                visit(item, f"{path}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif isinstance(value, str):
            if "<system-reminder>" in value.lower():
                problems.append(f"{path}: system reminder escaped")
            if capture_spine.redact(value) != value:
                problems.append(f"{path}: credential-shaped text escaped")

    visit(fragment)
    return problems


def load_fragments(fragment_dir: Path) -> list[dict]:
    """Load one complete, unique sequence from atomic fragment files."""
    paths = sorted(Path(fragment_dir).glob("*.json"))
    fragments = []
    names = set()
    sequences = set()
    for path in paths:
        if path.name in names:
            raise SDKAdapterError(f"duplicate fragment filename: {path.name}")
        names.add(path.name)
        fragment = json.loads(path.read_text())
        problems = fragment_problems(fragment)
        if problems:
            raise SDKAdapterError(f"unsafe fragment {path.name}: {'; '.join(problems)}")
        sequence = fragment["sequence"]
        if sequence in sequences:
            raise SDKAdapterError(f"duplicate fragment sequence: {sequence}")
        sequences.add(sequence)
        fragments.append(fragment)
    fragments.sort(key=lambda item: item["sequence"])
    if [item["sequence"] for item in fragments] != list(range(len(fragments))):
        raise SDKAdapterError("fragment sequence is incomplete")
    return fragments


def command_argv(command: str) -> list[str]:
    """Translate a Bash command into the scorer's shell-joined argv contract."""
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise SDKAdapterError(f"Bash command cannot be parsed: {exc}") from exc
    if not argv:
        raise SDKAdapterError("Bash command is empty")
    return argv


def apply_boundary(fragment: dict, trajectory) -> None:
    """Apply one acknowledged fragment to the provider-neutral recorder."""
    phase, tool = fragment["phase"], fragment.get("tool")
    command_id = fragment.get("tool_use_sha256")
    if phase != "batch" and fragment.get("ambiguous"):
        raise SDKAdapterError(f"ambiguous {phase} boundary")
    if phase == "start" and tool == "Bash":
        trajectory.begin_command(
            command_id,
            command_argv(fragment.get("command") or ""),
            cwd=fragment.get("cwd") or ".",
        )
    elif phase in {"finish", "failure"} and tool == "Bash":
        bash = fragment.get("bash") or {}
        exit_code = bash.get("exit_code")
        if not isinstance(exit_code, int):
            raise SDKAdapterError("Bash boundary has no exit status")
        trajectory.finish_command(
            command_id,
            exit_code=exit_code,
            output="",
            failed=bash.get("failed"),
            skipped=bash.get("skipped"),
            expected_failures=bash.get("expected_failures"),
        )
    elif phase == "denied" and tool == "Bash":
        trajectory.cancel_unexecuted_command(command_id)
    elif phase in {"finish", "failure"} and tool in {"Edit", "Write"}:
        record = getattr(trajectory, "record_edit_boundary", None)
        if record is None:
            if fragment.get("edits"):
                raise SDKAdapterError("trajectory recorder cannot record Edit/Write boundaries")
            return
        record(command_id)


def live_surface_problems(surfaces: list[dict], baseline: Mapping) -> list[str]:
    if not surfaces:
        return ["no live primary request surface"]
    problems = []
    for index, surface in enumerate(surfaces):
        unexpected = sorted(
            set(surface.get("differing_surfaces") or ()) - LIVE_MUTABLE_SURFACES
        )
        if unexpected:
            problems.append(f"surface {index} changed invariant fields: {', '.join(unexpected)}")
        for field in LIVE_INVARIANT_FIELDS:
            if surface.get(field) != baseline.get(field):
                problems.append(f"surface {index} changed {field}")
    return problems


def arm_reminder_evidence(requests: list[dict], arm_path: Path, arm_sha256: str) -> dict:
    arm_text = Path(arm_path).read_text()
    verified = 0
    for request in requests:
        spans = []
        for message in request.get("messages") or []:
            content = message.get("content") if isinstance(message, dict) else None
            blocks = content if isinstance(content, list) else (
                [{"text": content}] if isinstance(content, str) else []
            )
            for block in blocks:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    spans.extend(capture_spine.REMINDER_SPAN.findall(block["text"]))
        if any(arm_text in span for span in spans):
            verified += 1
    return {
        "verified": bool(requests) and verified == len(requests),
        "verified_requests": verified,
        "primary_request_count": len(requests),
        "arm_sha256": arm_sha256,
    }


def _run_node(request: dict, trajectory, *, node_executable: str) -> dict:
    """Run Node and acknowledge each boundary only after core records it."""
    with tempfile.TemporaryDirectory(prefix="bakeoff9-sdk-request-") as directory:
        request_path = Path(directory) / "request.json"
        request_path.write_text(json.dumps(request, separators=(",", ":")))
        process = subprocess.Popen(
            [node_executable, str(NODE_DRIVER), "--request", str(request_path)],
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=node_process_env(
                request["mode"], sandbox_temp_dir=request.get("sandbox_temp_dir")
            ),
        )
        assert process.stdin is not None and process.stdout is not None
        result = None
        sdk_messages = []
        request_bodies = []
        transport_error = None
        try:
            for line in process.stdout:
                message = json.loads(line)
                transport = message.get("transport")
                if transport == "boundary":
                    fragment = message.get("fragment")
                    problems = fragment_problems(fragment)
                    if problems:
                        raise SDKAdapterError("unsafe streamed fragment: " + "; ".join(problems))
                    apply_boundary(fragment, trajectory)
                    process.stdin.write(json.dumps({"ack": fragment["sequence"]}) + "\n")
                    process.stdin.flush()
                elif transport == "sdk-message":
                    sdk_messages.append(message.get("message"))
                elif transport == "raw-request":
                    request_bodies.append(message.get("raw"))
                else:
                    if result is not None:
                        raise SDKAdapterError("Node emitted more than one result")
                    result = message
        except BaseException as exc:
            transport_error = exc
            process.kill()
        return_code = process.wait(timeout=10)
        stderr = process.stderr.read() if process.stderr is not None else ""
        process.stdin.close()
        process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        if transport_error is not None:
            raise transport_error
        if return_code != 0:
            raise SDKAdapterError(f"Node adapter refused: {capture_spine.redact(stderr).strip()}")
        if not isinstance(result, dict) or result.get("schema") != RESULT_SCHEMA:
            raise SDKAdapterError("Node adapter returned no valid result")
        result["_sdk_messages"] = sdk_messages
        result["_request_bodies"] = request_bodies
        return result


def _canonical_sha256(value: object) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight_binding(
    *, binary: Path, model: str, harness_prompt: str, prompt: str,
    workspace: Path, baseline: Path, declared_configuration: Mapping,
) -> dict:
    """Hash-bind every preflight input without retaining prompt or workspace text."""
    return {
        "binary_sha256": _file_sha256(Path(binary)),
        "binary_path_sha256": _sha256(str(Path(binary).resolve()).encode()),
        "model": model,
        "harness_prompt": harness_prompt,
        "prompt_chars": len(prompt),
        "prompt_sha256": _sha256(prompt.encode()),
        "workspace_path_sha256": _sha256(str(Path(workspace).resolve()).encode()),
        "baseline_sha256": _file_sha256(Path(baseline)),
        "declared_configuration_sha256": _canonical_sha256(declared_configuration),
    }


def validate_preflight_receipt(receipt: Mapping, *, binary: Path, model: str,
                               harness_prompt: str, baseline: Path,
                               prompt: str, workspace: Path,
                               node_executable: str = "node") -> list[str]:
    problems = []
    for key, expected in (
        ("admitted", True),
        ("surface_verdict", "match"),
        ("hooks_surface_neutral", True),
        ("control_baseline_match", True),
        ("instrumented_baseline_match", True),
        ("inference_purchased", False),
    ):
        if receipt.get(key) != expected:
            problems.append(f"preflight {key} is not {expected!r}")
    binding = receipt.get("binding") or {}
    if binding.get("binary_sha256") != _file_sha256(Path(binary)):
        problems.append("preflight binary hash differs from the live adapter")
    if binding.get("model") != model:
        problems.append("preflight model differs from the live adapter")
    if binding.get("harness_prompt") != harness_prompt:
        problems.append("preflight harness prompt differs from the trial")
    if binding.get("prompt_chars") != len(prompt) or binding.get("prompt_sha256") != _sha256(
        prompt.encode()
    ):
        problems.append("preflight prompt differs from the trial")
    if binding.get("workspace_path_sha256") != _sha256(str(Path(workspace).resolve()).encode()):
        problems.append("preflight workspace differs from the trial")
    if binding.get("baseline_sha256") != _file_sha256(Path(baseline)):
        problems.append("preflight baseline hash differs from the frozen baseline")
    if binding.get("declared_configuration_sha256") != _canonical_sha256(
        describe(node_executable=node_executable)
    ):
        problems.append("preflight declared configuration differs from the live adapter")
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    if claimed != _canonical_sha256(body):
        problems.append("preflight receipt hash is invalid")
    return problems


def build_preflight_receipt(*, control: Mapping, instrumented: Mapping,
                            baseline: Mapping, binding: Mapping,
                            declared_configuration: Mapping,
                            primary_request_count: Mapping | None = None,
                            auxiliary_request_count: Mapping | None = None,
                            auxiliary_surfaces: Mapping | None = None) -> dict:
    """Pure three-way surface admission and receipt construction."""
    neutrality_differing = capture_spine.surface_diff(instrumented, control)
    control_differing = capture_spine.surface_diff(control, baseline)
    instrumented_differing = capture_spine.surface_diff(instrumented, baseline)
    admitted = not neutrality_differing and not control_differing and not instrumented_differing
    receipt = {
        "admitted": admitted,
        "surface_verdict": "match" if admitted else "mismatch",
        "hooks_surface_neutral": not neutrality_differing,
        "control_baseline_match": not control_differing,
        "instrumented_baseline_match": not instrumented_differing,
        "neutrality_differing_surfaces": neutrality_differing,
        "control_baseline_differing_surfaces": control_differing,
        "instrumented_baseline_differing_surfaces": instrumented_differing,
        "control_surface_key": capture_spine.surface_key(control),
        "instrumented_surface_key": capture_spine.surface_key(instrumented),
        "baseline_surface_key": capture_spine.surface_key(baseline),
        "baseline_sha256": binding["baseline_sha256"],
        "baseline_prompt_stable": {
            "system_joined_stable_sha256": baseline.get("system_joined_stable_sha256"),
            "system_reminder": {
                key: (baseline.get("system_reminder") or {}).get(key)
                for key in ("payload_chars", "payload_sha256", "payload_source")
            },
        },
        "binding": dict(binding),
        "declared_configuration": dict(declared_configuration),
        "primary_request_count": dict(primary_request_count or {}),
        "auxiliary_request_count": dict(auxiliary_request_count or {}),
        "auxiliary_surfaces": dict(auxiliary_surfaces or {}),
        "auxiliary_cost_caveat": (
            "Auxiliary SDK title requests are counted separately and may incur provider "
            "usage; they are not trial request surfaces."
        ),
        "inference_purchased": False,
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


@dataclass(frozen=True)
class AgentSDKAdapter:
    """Primary bakeoff 9 generation adapter."""

    binary: Path
    model: str = "claude-opus-5"
    node_executable: str = "node"
    mode: str = "live"
    fake_fixture: Path | None = None
    preflight_receipt: Mapping | None = None
    ablated_prompt_dir: Path | None = None
    baseline_path: Path = DEFAULT_SDK_BASELINE

    kind = AdapterKind.SDK_QUERY

    def with_preflight(self, receipt: Mapping) -> "AgentSDKAdapter":
        return replace(self, preflight_receipt=dict(receipt))

    def _system_prompt_file(self, case) -> Path | None:
        if case.harness_prompt == "intact":
            return None
        if self.ablated_prompt_dir is None:
            return None
        return self.ablated_prompt_dir / f"{case.fixture_id}.txt"

    def generate(self, case, workspace: Path, trajectory) -> GenerationResult | GenerationFailure:
        if self.mode == "live" and not self.preflight_receipt:
            return GenerationFailure(
                "preflight-required",
                "live SDK generation requires an admitted frozen-baseline preflight receipt",
                {"surface_verdict": "unrecorded"},
            )
        if self.mode == "live":
            receipt_problems = validate_preflight_receipt(
                self.preflight_receipt,
                binary=self.binary,
                model=self.model,
                harness_prompt=case.harness_prompt,
                baseline=self.baseline_path,
                prompt=case.prompt,
                workspace=workspace,
                node_executable=self.node_executable,
            )
            if receipt_problems:
                return GenerationFailure(
                    "preflight-required", "; ".join(receipt_problems),
                    {"surface_verdict": "unrecorded"},
                )
        raw_dir = None
        try:
            baseline = json.loads(Path(self.baseline_path).read_text())
            stable = (self.preflight_receipt or {}).get("baseline_prompt_stable")
            if stable:
                baseline["system_joined_stable_sha256"] = stable.get(
                    "system_joined_stable_sha256"
                )
                baseline.setdefault("system_reminder", {}).update(
                    stable.get("system_reminder") or {}
                )
            if self.mode == "live":
                raw_dir = Path(tempfile.mkdtemp(prefix="bakeoff9-sdk-raw-"))
            with tempfile.TemporaryDirectory(prefix="bakeoff9-sdk-fragments-") as fragments, \
                 tempfile.TemporaryDirectory(prefix="bakeoff9-sdk-sandbox-") as sandbox:
                request = build_request(
                    mode=self.mode,
                    workspace=workspace,
                    fragment_dir=Path(fragments),
                    prompt=case.prompt,
                    harness_prompt=case.harness_prompt,
                    claude_executable=self.binary,
                    model=self.model,
                    fake_fixture=self.fake_fixture,
                    system_prompt_file=self._system_prompt_file(case),
                    surface_verdict=(self.preflight_receipt or {}).get("surface_verdict"),
                    raw_body_dir=raw_dir,
                    sandbox_temp_dir=Path(sandbox),
                )
                result = _run_node(request, trajectory, node_executable=self.node_executable)
                files = load_fragments(Path(fragments))
                if len(files) != (result.get("capture") or {}).get("fragment_count"):
                    raise SDKAdapterError("stream/file fragment count mismatch")
            sdk_messages = result.pop("_sdk_messages")
            in_memory_requests = result.pop("_request_bodies")
            if self.mode == "live":
                raw_records = capture_spine.raw_body_records(raw_dir)
            else:
                raw_records = in_memory_requests
            primary_requests, auxiliary_requests = capture_spine.partition_request_records(
                raw_records
            )
            request_surfaces = capture_spine.observed_surface_records(
                primary_requests, baseline
            )
            auxiliary_request_surfaces = capture_spine.observed_surface_records(
                auxiliary_requests, None
            )
            sdk_record = capture_spine.sdk_capture_record(sdk_messages) if sdk_messages else None
            if self.mode == "live" and (not sdk_record or not sdk_record["turns"]):
                raise SDKAdapterError("live SDK stream carried no init/assistant turn record")
            live_bootstrap = None
            arm_reminder = None
            if self.mode == "live":
                invariant_problems = live_surface_problems(request_surfaces, baseline)
                if invariant_problems:
                    raise SDKAdapterError("; ".join(invariant_problems))
                arm_path = Path(workspace) / "CLAUDE.md"
                arm_reminder = arm_reminder_evidence(
                    primary_requests, arm_path, case.arm_sha256
                )
                if not arm_reminder["verified"]:
                    raise SDKAdapterError("live requests did not carry the exact declared arm reminder")
                first_surface = capture_spine.observed_surface_records(
                    primary_requests[:1], None
                )[0]
                live_bootstrap = {
                    "schema": "bakeoff9-live-surface-bootstrap/1",
                    "policy": "oauth-system-reminder-bootstrap",
                    "first_primary": first_surface,
                }
        except (OSError, ValueError, SDKAdapterError, json.JSONDecodeError) as exc:
            failure_capture = {"surface_verdict": "unrecorded"}
            if raw_dir is not None and raw_dir.exists():
                failure_capture.update({
                    "raw_preserved": True,
                    "raw_path_sha256": _sha256(str(raw_dir).encode()),
                })
            return GenerationFailure(
                "sdk-adapter-refused",
                capture_spine.redact(str(exc)),
                failure_capture,
            )
        capture = dict(result["capture"])
        if self.mode == "live" and live_bootstrap and arm_reminder:
            surface_verdict = "match"
        elif request_surfaces:
            surface_verdict = (
                "match" if all(surface.get("matches_baseline") for surface in request_surfaces)
                else "mismatch"
            )
        else:
            surface_verdict = "fake" if self.mode == "fake" else "unrecorded"
        capture.update({
            "schema": capture_spine.MANIFEST_SCHEMA_VERSION,
            "surface_verdict": surface_verdict,
            "request_surfaces": request_surfaces,
            "primary_request_count": len(primary_requests),
            "auxiliary_request_count": len(auxiliary_requests),
            "auxiliary_request_surfaces": auxiliary_request_surfaces,
            "auxiliary_cost_caveat": (
                "Auxiliary SDK title requests are counted separately and may incur provider "
                "usage; they are not trial request surfaces."
            ),
            "result_usage": result["usage"],
            "baseline": {
                "sha256": _file_sha256(self.baseline_path),
                "surface_key": capture_spine.surface_key(baseline),
            },
            "raw_bodies_retained": False,
            "raw_dir_purged": self.mode == "live",
        })
        if live_bootstrap is not None:
            capture["live_surface_bootstrap"] = live_bootstrap
        if arm_reminder is not None:
            capture["arm_reminder"] = arm_reminder
        if sdk_record:
            capture.update({
                "sdk_init": sdk_record["init"],
                "turns": sdk_record["turns"],
                "usage_totals": sdk_record["usage_totals"],
                "cli_versions": sdk_record["cli_versions"],
                "model_provenance": {
                    "requested": self.model,
                    "resolved": sdk_record["init"].get("model"),
                    "account_source": sdk_record["init"].get("account_source"),
                },
            })
        if self.preflight_receipt:
            capture["preflight"] = dict(self.preflight_receipt)
        retention = capture_spine.retention_problems(capture)
        if retention:
            return GenerationFailure(
                "sdk-capture-refused",
                "capture-spine retention boundary failed: " + "; ".join(retention),
                {"surface_verdict": "unrecorded", "raw_preserved": bool(raw_dir)},
            )
        if raw_dir is not None:
            try:
                capture_spine.purge_raw(raw_dir)
            except (OSError, ValueError) as exc:
                return GenerationFailure(
                    "sdk-capture-refused",
                    "capture-spine could not purge the validated raw tier: "
                    + capture_spine.redact(str(exc)),
                    {"surface_verdict": "unrecorded", "raw_preserved": True,
                     "raw_path_sha256": _sha256(str(raw_dir).encode())},
                )
        return GenerationResult(
            response=result["response"],
            usage=result["usage"],
            capture=capture,
        )


def build_generation_adapter(*, campaign_dir: Path, declaration: Path | Mapping) -> AgentSDKAdapter:
    """Construct the primary adapter from the authoritative campaign declaration."""
    spec = _load_declaration(declaration)
    pins = spec.get("pins") or {}
    if pins.get("generator") != "sdk-query":
        raise ValueError("campaign declaration does not select SDK query generation")
    if pins.get("tool_surface_option") != "tools" or tuple(pins.get("tool_surface") or ()) != TOOL_SURFACE:
        raise ValueError("campaign declaration tool surface differs from the SDK adapter")
    if (
        pins.get("setting_sources") != ["project"]
        or pins.get("permission_callback") != "none"
        or pins.get("permission_mode") != "bypassPermissions"
        or pins.get("allow_dangerously_skip_permissions") is not True
    ):
        raise ValueError("campaign declaration settings/permission boundary differs from the SDK adapter")
    binary = Path(pins["generator_binary"]).expanduser()
    return AgentSDKAdapter(
        binary=binary,
        model=pins.get("generator_model", "claude-opus-5"),
        baseline_path=DEFAULT_SDK_BASELINE,
    )


class _Synthetic401:
    """Capture one request body in memory and return a synthetic auth error."""

    def __init__(self):
        self.bodies: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                try:
                    owner.bodies.append(json.loads(body))
                except json.JSONDecodeError:
                    pass
                payload = json.dumps({
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "synthetic capture stop"},
                }).encode()
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()


def synthetic_401_preflight(
    *,
    binary: Path,
    workspace: Path,
    model: str = "claude-opus-5",
    node_executable: str = "node",
    harness_prompt: str = "intact",
    system_prompt_file: Path | None = None,
    prompt: str = "ping",
    baseline_path: Path = DEFAULT_SDK_BASELINE,
) -> dict:
    """Admit hook-neutral surfaces only when both match the frozen baseline."""
    baseline_path = Path(baseline_path).resolve()
    baseline = json.loads(baseline_path.read_text())
    summaries = []
    primary_counts = {}
    auxiliary_counts = {}
    auxiliary_summaries = {}
    with tempfile.TemporaryDirectory(prefix="bakeoff9-preflight-home-") as home:
        def capture_one(label, used_prompt, observe_hooks):
            with _Synthetic401() as probe, tempfile.TemporaryDirectory(
                prefix="bakeoff9-preflight-fragments-"
            ) as fragments, tempfile.TemporaryDirectory(
                prefix="bakeoff9-preflight-sandbox-"
            ) as sandbox:
                request = build_request(
                    mode="preflight",
                    workspace=workspace,
                    fragment_dir=Path(fragments),
                    prompt=used_prompt,
                    harness_prompt=harness_prompt,
                    claude_executable=binary,
                    model=model,
                    system_prompt_file=system_prompt_file,
                    base_url=probe.base_url,
                    observe_hooks=observe_hooks,
                    preflight_home=Path(home),
                    sandbox_temp_dir=Path(sandbox),
                )

                class EmptyTrajectory:
                    pass

                _run_node(request, EmptyTrajectory(), node_executable=node_executable)
                primary, auxiliary = capture_spine.partition_request_records(probe.bodies)
                if not primary:
                    raise SDKAdapterError("synthetic preflight captured no primary request")
                distinct = capture_spine.observed_surface_records(primary, None)
                if len(distinct) != 1:
                    raise SDKAdapterError(
                        f"synthetic preflight {label} retries carried {len(distinct)} primary surfaces"
                    )
                summary, _ = capture_spine.summarize_request(primary[0])
                return summary, len(primary), len(auxiliary), capture_spine.observed_surface_records(
                    auxiliary, None
                )

        if prompt == "ping":
            reference = None
        else:
            reference, _, _, _ = capture_one("baseline-reference", "ping", False)
        if reference is not None:
            baseline = capture_spine.prompt_stable_baseline(
                baseline,
                reference,
                allowed_reference_differences=("system_reminder",),
            )
        for label, observe_hooks in (("control", False), ("instrumented", True)):
            summary, primary_count, auxiliary_count, aux_surfaces = capture_one(
                label, prompt, observe_hooks
            )
            summaries.append(summary)
            primary_counts[label] = primary_count
            auxiliary_counts[label] = auxiliary_count
            auxiliary_summaries[label] = aux_surfaces
    if reference is None:
        baseline = capture_spine.prompt_stable_baseline(baseline, summaries[0])
    declared_configuration = describe(node_executable=node_executable)
    binding = preflight_binding(
        binary=binary, model=model, harness_prompt=harness_prompt, prompt=prompt,
        workspace=workspace, baseline=baseline_path,
        declared_configuration=declared_configuration,
    )
    return build_preflight_receipt(
        control=summaries[0], instrumented=summaries[1], baseline=baseline,
        binding=binding, declared_configuration=declared_configuration,
        primary_request_count=primary_counts,
        auxiliary_request_count=auxiliary_counts,
        auxiliary_surfaces=auxiliary_summaries,
    )


def describe(*, node_executable: str = "node") -> dict:
    completed = subprocess.run(
        [node_executable, str(NODE_DRIVER), "--describe"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=node_process_env("fake"),
        check=False,
    )
    if completed.returncode:
        raise SDKAdapterError(capture_spine.redact(completed.stderr))
    return json.loads(completed.stdout)
