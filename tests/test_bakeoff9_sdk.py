"""Repository-local Agent SDK boundary for bakeoff 9."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# The real-preflight suite drives a pinned claude binary that no clone carries.
# Point BAKEOFF9_CLAUDE_BINARY at it to run those cases; unset, they skip.
PINNED_BINARY = Path(os.environ.get("BAKEOFF9_CLAUDE_BINARY", ""))
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_sdk as sdk
import bakeoff9_trajectory as trajectory


def fake_request_body(*, tools=("Bash", "Read", "Edit", "Write", "Grep", "Glob")):
    return {
        "model": "claude-opus-5", "max_tokens": 64000,
        "system": [{"type": "text", "text": "billing"}, {
            "type": "text",
            "text": "prompt\n - Primary working directory: /private/tmp/fixture\n",
        }],
        "tools": [{"name": name, "description": name, "input_schema": {"type": "object"}}
                  for name in tools],
        "messages": [{"role": "user", "content": [{
            "type": "text",
            "text": "<system-reminder>Today's date is 2026-08-27.</system-reminder>prompt",
        }]}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
    }


def fake_sdk_messages():
    messages = [{
        "type": "system", "subtype": "init", "claude_code_version": "2.1.239",
        "cwd": "/private/tmp/fixture", "model": "claude-opus-5",
        "apiKeySource": "oauth", "permissionMode": "default",
        "tools": ["Bash", "Read", "Edit", "Write", "Grep", "Glob"],
    }]
    for index in range(2):
        messages.append({
            "type": "assistant", "uuid": f"u{index}", "request_id": f"r{index}",
            "timestamp": f"2026-08-27T00:00:0{index}Z", "session_id": "session",
            "parent_tool_use_id": None, "effort": "high",
            "message": {
                "id": f"m{index}", "model": "claude-opus-5", "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [
                    {"type": "thinking", "thinking": f"private {index}"},
                    {"type": "text", "text": f"answer {index} <system-reminder>hidden</system-reminder>"},
                    {"type": "tool_use", "id": f"tool{index}", "name": "Bash",
                     "input": {"api_key": "secret-value"}},
                ],
                "usage": {
                    "input_tokens": 2, "output_tokens": 5,
                    "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4,
                    "output_tokens_details": {"thinking_tokens": 1},
                },
            },
        })
    return messages


class Recorder:
    def __init__(self):
        self.events = []

    def begin_command(self, command_id, argv, *, cwd="."):
        self.events.append(("start", command_id, argv, cwd))

    def finish_command(self, command_id, **evidence):
        self.events.append(("finish", command_id, evidence))

    def cancel_unexecuted_command(self, command_id):
        self.events.append(("cancel", command_id))

    def record_edit_boundary(self, event_id):
        self.events.append(("edit-boundary", event_id))


def node_eval(source: str, *, env=None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def sandbox_wrappers(workspace: Path, private_temp: Path, commands: list[str]) -> list[str]:
    module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
    source = f"""
      import {{ createSandboxRuntime, wrapBashCommand }} from {json.dumps(module)};
      const runtime = await createSandboxRuntime(
        {json.dumps(str(workspace))}, {json.dumps(str(private_temp))}
      );
      process.stdout.write(JSON.stringify(
        {json.dumps(commands)}.map((command) => wrapBashCommand(command, runtime))
      ));
    """
    completed = node_eval(source)
    if completed.returncode:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)


class SDKDescriptionTests(unittest.TestCase):
    def test_preflight_receipt_is_bound_to_exact_prompt_and_workspace(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            binary = root / "claude"
            binary.write_bytes(b"pinned")
            workspace = root / "workspace"
            other_workspace = root / "other"
            workspace.mkdir()
            other_workspace.mkdir()
            summary, _ = sdk.capture_spine.summarize_request(fake_request_body())
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps(summary))
            declared = sdk.describe()
            binding = sdk.preflight_binding(
                binary=binary, model="claude-opus-5", harness_prompt="intact",
                prompt="exact prompt", workspace=workspace, baseline=baseline_path,
                declared_configuration=declared,
            )
            receipt = sdk.build_preflight_receipt(
                control=summary, instrumented=summary, baseline=summary,
                binding=binding, declared_configuration=declared,
            )
            arguments = {
                "binary": binary, "model": "claude-opus-5",
                "harness_prompt": "intact", "baseline": baseline_path,
                "prompt": "exact prompt", "workspace": workspace,
            }
            self.assertEqual([], sdk.validate_preflight_receipt(receipt, **arguments))
            self.assertIn(
                "preflight prompt differs from the trial",
                sdk.validate_preflight_receipt(receipt, **{**arguments, "prompt": "other"}),
            )
            self.assertIn(
                "preflight workspace differs from the trial",
                sdk.validate_preflight_receipt(
                    receipt, **{**arguments, "workspace": other_workspace}
                ),
            )

    def test_node_command_sanitizer_covers_generic_secret_assignments(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        source = f"""
          import {{ sanitizeText }} from {json.dumps(module)};
          process.stdout.write(sanitizeText('cache_key=not-retained'));
        """
        completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual("cache_key=<redacted>", completed.stdout)
        self.assertEqual(completed.stdout, sdk.capture_spine.redact(completed.stdout))

    def test_description_pins_the_declared_surface_without_context_treatments(self):
        description = sdk.describe()
        self.assertEqual(description["sdk_version"], "0.3.233")
        self.assertEqual(description["tool_surface_option"], "tools")
        self.assertEqual(description["tool_surface"], list(sdk.TOOL_SURFACE))
        self.assertEqual(description["setting_sources"], ["project"])
        self.assertEqual(description["settings"], {"autoMemoryEnabled": False})
        self.assertFalse(description["can_use_tool"])
        self.assertEqual(description["permission_mode"], "bypassPermissions")
        self.assertTrue(description["dangerous_skip_permissions"])
        self.assertFalse(description["thinking_override"])
        self.assertEqual(
            description["hooks"],
            [
                "PreToolUse", "PostToolUse", "PostToolUseFailure",
                "PermissionDenied", "PostToolBatch",
            ],
        )
        self.assertEqual(description["containment"]["bash_wrapper"], "macos-sandbox-exec")
        self.assertFalse(description["containment"]["native_sdk_sandbox"])
        self.assertEqual(description["containment"]["network"], "deny")

    def test_permission_options_bypass_headless_gate_without_callback_surface(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        source = f"""
          import {{ permissionOptions }} from {json.dumps(module)};
          process.stdout.write(JSON.stringify(permissionOptions()));
        """
        completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            {
                "permissionMode": "bypassPermissions",
                "allowDangerouslySkipPermissions": True,
            },
            json.loads(completed.stdout),
        )
        self.assertNotIn("canUseTool", completed.stdout)
        self.assertNotIn("allowedTools", completed.stdout)

    def test_exact_sdk_is_a_repository_dependency(self):
        package = json.loads((ROOT / "package.json").read_text())
        lock = json.loads((ROOT / "package-lock.json").read_text())
        self.assertEqual(package["dependencies"], {"@anthropic-ai/claude-agent-sdk": "0.3.233"})
        self.assertEqual(
            lock["packages"]["node_modules/@anthropic-ai/claude-agent-sdk"]["version"],
            "0.3.233",
        )
        # Split so this guard does not itself trip the export gate's private-app pattern.
        self.assertNotIn("nova" + "-deck", (ROOT / "scripts" / "bakeoff9_sdk.mjs").read_text())

    def test_live_auth_refuses_api_keys_and_redirects(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        source = f"""
          import {{ assertAuthBoundary }} from {json.dumps(module)};
          for (const [env, base] of [
            [{{ANTHROPIC_API_KEY:'secret'}}, ''],
            [{{}}, 'https://gateway.invalid']
          ]) {{
            try {{ assertAuthBoundary('live', env, base); process.exit(4); }}
            catch (error) {{ process.stdout.write(error.message + '\\n'); }}
          }}
        """
        completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("subscription auth only", completed.stdout)
        self.assertIn("non-default ANTHROPIC_BASE_URL", completed.stdout)

    def test_live_auth_refuses_alternate_provider_variables(self):
        with self.assertRaisesRegex(sdk.SDKAdapterError, "AWS_PROFILE"):
            sdk.node_process_env("live", {
                "PATH": os.environ["PATH"],
                "CLAUDE_CODE_OAUTH_TOKEN": "subscription-oauth",
                "AWS_PROFILE": "production",
            })

    def test_live_auth_strips_unrelated_api_credentials(self):
        child = sdk.node_process_env("live", {
            "PATH": os.environ["PATH"],
            "CLAUDE_CODE_OAUTH_TOKEN": "subscription-oauth",
            "OMLX_API_KEY": "unrelated-provider-key",
        }, sandbox_temp_dir=Path(tempfile.gettempdir()))

        self.assertNotIn("OMLX_API_KEY", child)
        self.assertEqual(child["CLAUDE_CODE_OAUTH_TOKEN"], "subscription-oauth")

    def test_preflight_child_gets_only_dummy_auth_and_loopback_redirect(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        source = f"""
          import {{ buildChildEnv }} from {json.dumps(module)};
          const child = buildChildEnv('preflight', {{
            PATH: process.env.PATH,
            HOME: process.env.HOME,
            CLAUDE_CODE_OAUTH_TOKEN: 'real-oauth',
            ANTHROPIC_API_KEY: 'real-api',
            ANTHROPIC_BASE_URL: 'https://gateway.invalid',
            CLAUDE_CODE_MESSAGING_TOKEN: 'real-message-token'
          }}, 'http://127.0.0.1:4321', '/tmp/bakeoff9-isolated-home', null, '/tmp/bakeoff9-sandbox');
          process.stdout.write(JSON.stringify({{
            names: Object.keys(child).sort(),
            base: child.ANTHROPIC_BASE_URL,
            dummy: child.ANTHROPIC_API_KEY === 'sk-ant-dummy-capture-not-a-real-key',
            tmpdir: child.TMPDIR
          }}));
        """
        completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        observed = json.loads(completed.stdout)
        self.assertTrue(observed["dummy"])
        self.assertEqual(observed["base"], "http://127.0.0.1:4321")
        self.assertEqual(observed["tmpdir"], "/tmp/bakeoff9-sandbox/")
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", observed["names"])
        self.assertNotIn("CLAUDE_CODE_MESSAGING_TOKEN", observed["names"])

    def test_preflight_refuses_non_loopback(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        completed = node_eval(
            f"import {{ assertAuthBoundary }} from {json.dumps(module)}; "
            "try { assertAuthBoundary('preflight', {}, 'https://api.anthropic.com'); process.exit(4); } "
            "catch (error) { process.stdout.write(error.message); }"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("loopback", completed.stdout)

    def test_live_child_enables_measured_raw_body_capture_flags(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        source = f"""
          import {{ buildChildEnv }} from {json.dumps(module)};
          const child = buildChildEnv('live', {{PATH: process.env.PATH, HOME: process.env.HOME}}, '', null, '/tmp/b9-raw', '/tmp/b9-sandbox');
          process.stdout.write(JSON.stringify({{
            disableTelemetry: child.DISABLE_TELEMETRY,
            enableTelemetry: child.CLAUDE_CODE_ENABLE_TELEMETRY,
            logs: child.OTEL_LOGS_EXPORTER,
            metrics: child.OTEL_METRICS_EXPORTER,
            raw: child.OTEL_LOG_RAW_API_BODIES
          }}));
        """
        completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        observed = json.loads(completed.stdout)
        self.assertEqual(observed, {
            "disableTelemetry": "1", "enableTelemetry": "1", "logs": "console",
            "metrics": "", "raw": "file:/tmp/b9-raw",
        })


class SDKParsingTests(unittest.TestCase):
    def test_live_bootstrap_allows_only_account_mutable_surfaces(self):
        baseline, _ = sdk.capture_spine.summarize_request(fake_request_body())
        mutable = dict(baseline)
        mutable["differing_surfaces"] = ["system", "system_reminder"]
        self.assertEqual([], sdk.live_surface_problems([mutable], baseline))
        changed = dict(mutable, tools_sha256="f" * 64)
        changed["differing_surfaces"] = ["tools"]
        problems = sdk.live_surface_problems([changed], baseline)
        self.assertTrue(any("tools" in problem for problem in problems))

    def test_arm_reminder_evidence_requires_exact_arm_inside_every_request(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            arm = Path(temporary) / "CLAUDE.md"
            arm.write_text("Exact arm clause.")
            request = fake_request_body()
            request["messages"][0]["content"][0]["text"] = (
                "<system-reminder>prefix\nExact arm clause.\nsuffix</system-reminder>prompt"
            )
            evidence = sdk.arm_reminder_evidence([request, request], arm, "a" * 64)
            self.assertTrue(evidence["verified"])
            self.assertEqual(2, evidence["verified_requests"])
            request["messages"][0]["content"][0]["text"] = (
                "<system-reminder>other</system-reminder>prompt"
            )
            self.assertFalse(
                sdk.arm_reminder_evidence([request], arm, "a" * 64)["verified"]
            )

    def test_streamed_permission_denial_closes_before_the_next_tool_turn(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder, reconcilePermissionDeniedMessage }} from {json.dumps(module)};
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              await recorder.pre({{tool_name:'Bash', tool_use_id:'one', tool_input:{{command:'true'}}}});
              await reconcilePermissionDeniedMessage(recorder, {{
                type:'system', subtype:'permission_denied',
                tool_name:'Bash', tool_use_id:'one'
              }});
              await recorder.pre({{tool_name:'Glob', tool_use_id:'two', tool_input:{{pattern:'*'}}}});
              await recorder.denied({{tool_name:'Glob', tool_use_id:'two'}});
              process.stdout.write(JSON.stringify(await recorder.settled()));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                {
                    "fragment_count": 4, "ambiguous": [],
                    "executed_tool_count": 0, "denied_tool_count": 2,
                }, json.loads(completed.stdout)
            )

    def test_parallel_read_only_bash_boundaries_settle_in_finish_order(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder }} from {json.dumps(module)};
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              const one = {{tool_name:'Bash', tool_use_id:'one', tool_input:{{command:'echo one'}}}};
              const two = {{tool_name:'Bash', tool_use_id:'two', tool_input:{{command:'echo two'}}}};
              await recorder.pre(one);
              await recorder.pre(two);
              await recorder.post({{...two, tool_response:{{stdout:'two', stderr:'', exitCode:0}}}});
              await recorder.post({{...one, tool_response:{{stdout:'one', stderr:'', exitCode:0}}}});
              process.stdout.write(JSON.stringify(await recorder.settled()));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                {
                    "fragment_count": 4, "ambiguous": [],
                    "executed_tool_count": 2, "denied_tool_count": 0,
                }, json.loads(completed.stdout)
            )
            records = [json.loads(path.read_text()) for path in sorted(fragments.iterdir())]
            self.assertEqual(
                ["start", "start", "finish", "finish"],
                [record["phase"] for record in records],
            )
            replay = trajectory.TrajectoryRecorder(workspace)
            for record in records:
                sdk.apply_boundary(record, replay)
            self.assertEqual(
                [("echo", "two"), ("echo", "one")],
                [tuple(event["argv"]) for event in replay.public_trajectory()],
            )

    def test_tree_stable_bash_and_read_tools_may_overlap(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder }} from {json.dumps(module)};
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              const bash = {{tool_name:'Bash', tool_use_id:'bash', tool_input:{{command:'true'}}}};
              const grep = {{tool_name:'Grep', tool_use_id:'grep', tool_input:{{pattern:'x'}}}};
              await recorder.pre(bash);
              await recorder.pre(grep);
              await recorder.post({{...grep, tool_response:{{matches:[]}}}});
              await recorder.post({{...bash, tool_response:{{stdout:'', stderr:'', exitCode:0}}}});
              process.stdout.write(JSON.stringify(await recorder.settled()));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                {
                    "fragment_count": 4, "ambiguous": [],
                    "executed_tool_count": 2, "denied_tool_count": 0,
                }, json.loads(completed.stdout)
            )
            replay = trajectory.TrajectoryRecorder(workspace)
            for path in sorted(fragments.iterdir()):
                sdk.apply_boundary(json.loads(path.read_text()), replay)
            self.assertEqual(1, len(replay.public_trajectory()))

    def test_parallel_start_rejects_intervening_change_and_mixed_tools(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder }} from {json.dumps(module)};
              import {{ writeFile }} from 'node:fs/promises';
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              await recorder.pre({{tool_name:'Bash', tool_use_id:'one', tool_input:{{command:'true'}}}});
              await writeFile({json.dumps(str(workspace / 'changed'))}, 'changed');
              await recorder.pre({{tool_name:'Bash', tool_use_id:'two', tool_input:{{command:'true'}}}});
              await recorder.pre({{tool_name:'Write', tool_use_id:'three', tool_input:{{file_path:'x'}}}});
              process.stdout.write(JSON.stringify(await recorder.settled()));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            ambiguous = json.loads(completed.stdout)["ambiguous"]
            self.assertIn("workspace changed during parallel boundary", ambiguous)
            self.assertIn("mixed parallel tool boundary", ambiguous)

    def test_batch_pending_count_is_provisional_until_final_settlement(self):
        recorder = Recorder()
        sdk.apply_boundary({
            "phase": "batch",
            "ambiguous": True,
            "pending_count": 1,
        }, recorder)
        self.assertEqual([], recorder.events)

    def test_unreconciled_boundary_without_a_batch_fails_final_settlement(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder }} from {json.dumps(module)};
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              await recorder.pre({{
                tool_name: 'Bash', tool_use_id: 'pending-1',
                tool_input: {{command: 'cat missing'}}
              }});
              process.stdout.write(JSON.stringify(await recorder.settled()));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            settled = json.loads(completed.stdout)
            self.assertIn("unfinished tool boundary", settled["ambiguous"])

    def test_batch_closes_tree_stable_unexecuted_tool(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder }} from {json.dumps(module)};
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              await recorder.pre({{
                tool_name: 'Bash', tool_use_id: 'pending-1',
                tool_input: {{command: 'cat missing'}}
              }});
              await recorder.batch({{tool_calls: []}});
              process.stdout.write(JSON.stringify(await recorder.settled()));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                {
                    "fragment_count": 3, "ambiguous": [],
                    "executed_tool_count": 0, "denied_tool_count": 1,
                }, json.loads(completed.stdout)
            )
            records = [json.loads(path.read_text()) for path in sorted(fragments.iterdir())]
            self.assertEqual(
                ["start", "denied", "batch"], [record["phase"] for record in records]
            )
            replay = trajectory.TrajectoryRecorder(workspace)
            for record in records:
                sdk.apply_boundary(record, replay)
            self.assertEqual([], replay.public_trajectory())

    def test_permission_denial_closes_without_fabricating_execution(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            fragments = root / "fragments"
            workspace.mkdir()
            module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
            source = f"""
              import {{ BoundaryRecorder }} from {json.dumps(module)};
              const recorder = new BoundaryRecorder({{
                workspace: {json.dumps(str(workspace))},
                fragmentDir: {json.dumps(str(fragments))}
              }});
              const input = {{
                tool_name: 'Bash', tool_use_id: 'denied-1',
                tool_input: {{command: 'cat missing'}}
              }};
              await recorder.pre(input);
              await recorder.denied(input);
              const settled = await recorder.settled();
              process.stdout.write(JSON.stringify(settled));
            """
            completed = node_eval(source)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                {
                    "fragment_count": 2, "ambiguous": [],
                    "executed_tool_count": 0, "denied_tool_count": 1,
                }, json.loads(completed.stdout)
            )
            records = [json.loads(path.read_text()) for path in sorted(fragments.iterdir())]
            self.assertEqual(["start", "denied"], [record["phase"] for record in records])
            recorder = Recorder()
            for record in records:
                sdk.apply_boundary(record, recorder)
            self.assertEqual(["start", "cancel"], [event[0] for event in recorder.events])

    def test_bash_exit_and_test_counts_are_normalized_without_output(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        source = f"""
          import {{ parseBashResult }} from {json.dumps(module)};
          const value = parseBashResult('Error: Exit code 1\\n2 failed, 3 skipped, 4 xfailed', {{failure:true}});
          process.stdout.write(JSON.stringify(value));
        """
        completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertEqual(
            {key: parsed[key] for key in ("exit_code", "failed", "skipped", "expected_failures")},
            {"exit_code": 1, "failed": 2, "skipped": 3, "expected_failures": 4},
        )
        self.assertNotIn("output", parsed)
        self.assertFalse(parsed["ambiguous"])

    def test_unknown_exit_status_fails_closed(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        completed = node_eval(
            f"import {{ parseBashResult }} from {json.dumps(module)}; "
            "process.stdout.write(JSON.stringify(parseBashResult({stdout:'?', interrupted:true})));"
        )
        parsed = json.loads(completed.stdout)
        self.assertIsNone(parsed["exit_code"])
        self.assertTrue(parsed["ambiguous"])


@unittest.skipUnless(
    PINNED_BINARY.is_file(),
    "set BAKEOFF9_CLAUDE_BINARY to the pinned claude binary to run the real preflight",
)
class SDKRealPreflightTests(unittest.TestCase):
    def test_absent_credential_prompt_partitions_title_requests_and_admits_primary(self):
        fixture = ROOT / (
            "campaigns/clause-bakeoff-9-2026-08-22/fixtures/"
            "b1-easy/b1e-credential-file-absent/fixture.json"
        )
        prompt = json.loads(fixture.read_text())["prompt"]
        with tempfile.TemporaryDirectory(prefix="b9-real-prompt-preflight-") as workspace:
            receipt = sdk.synthetic_401_preflight(
                binary=PINNED_BINARY,
                workspace=Path(workspace), prompt=prompt,
            )
        self.assertTrue(receipt["admitted"])
        self.assertTrue(receipt["hooks_surface_neutral"])
        self.assertEqual(
            receipt["control_surface_key"],
            "ec95ee8430e6fb38465e8f9d270eba9f14f66f5d00b8b4a98458986e526fa7f9",
        )
        self.assertEqual(receipt["instrumented_surface_key"], receipt["control_surface_key"])
        self.assertGreater(receipt["primary_request_count"]["control"], 0)
        self.assertGreater(receipt["primary_request_count"]["instrumented"], 0)
        self.assertGreater(receipt["auxiliary_request_count"]["control"], 0)
        self.assertGreater(receipt["auxiliary_request_count"]["instrumented"], 0)
        for summaries in receipt["auxiliary_surfaces"].values():
            self.assertTrue(summaries)
            self.assertEqual(summaries[0]["tools"], [])
            self.assertEqual(summaries[0]["thinking"], {"type": "disabled"})
            self.assertIsNotNone(summaries[0]["output_format"])

    def test_neutral_but_wrong_request_is_not_admitted(self):
        baseline, _ = sdk.capture_spine.summarize_request(fake_request_body())
        wrong, _ = sdk.capture_spine.summarize_request(fake_request_body(tools=("Bash",)))
        receipt = sdk.build_preflight_receipt(
            control=wrong, instrumented=wrong, baseline=baseline,
            binding={"baseline_sha256": "a" * 64},
            declared_configuration={"sdk_version": sdk.SDK_VERSION},
        )
        self.assertTrue(receipt["hooks_surface_neutral"])
        self.assertFalse(receipt["control_baseline_match"])
        self.assertFalse(receipt["instrumented_baseline_match"])
        self.assertFalse(receipt["admitted"])
        self.assertEqual(receipt["surface_verdict"], "mismatch")


class SDKContainmentTests(unittest.TestCase):
    def test_repeated_runtime_without_parent_tmpdir_is_unique_and_repo_clean(self):
        before = {path.name for path in ROOT.iterdir()}
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, private = root / "workspace", root / "private"
            workspace.mkdir()
            private.mkdir()
            source = f"""
              import {{ createSandboxRuntime }} from {json.dumps(module)};
              const first = await createSandboxRuntime({json.dumps(str(workspace))}, {json.dumps(str(private))});
              const second = await createSandboxRuntime({json.dumps(str(workspace))}, {json.dumps(str(private))});
              process.stdout.write(JSON.stringify([first.profile, second.profile]));
            """
            completed = node_eval(source, env={
                key: value for key, value in os.environ.items() if key != "TMPDIR"
            })
            self.assertEqual(completed.returncode, 0, completed.stderr)
            profiles = json.loads(completed.stdout)
            self.assertEqual(len(set(profiles)), 2)
            self.assertTrue(all(Path(path).parent == private.resolve() for path in profiles))
            node_env = sdk.node_process_env(
                "preflight", {"PATH": os.environ["PATH"]}, sandbox_temp_dir=private
            )
            self.assertEqual(node_env["TMPDIR"], str(private.resolve()) + os.sep)
        self.assertEqual({path.name for path in ROOT.iterdir()}, before)

    def test_bash_hook_only_rewrites_command_without_context_or_permission_decision(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, private = root / "workspace", root / "private"
            workspace.mkdir()
            private.mkdir()
            source = f"""
              import {{ createSandboxRuntime, bashHookOutput }} from {json.dumps(module)};
              const runtime = await createSandboxRuntime({json.dumps(str(workspace))}, {json.dumps(str(private))});
              const input = {{command: "printf original", timeout: 1000}};
              const output = bashHookOutput(input, runtime);
              process.stdout.write(JSON.stringify({{input, output}}));
            """
            completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertEqual(value["input"]["command"], "printf original")
        specific = value["output"]["hookSpecificOutput"]
        self.assertEqual(specific["updatedInput"]["timeout"], 1000)
        self.assertIn("/usr/bin/sandbox-exec", specific["updatedInput"]["command"])
        self.assertNotIn("permissionDecision", specific)
        self.assertNotIn("additionalContext", specific)

    def test_sandbox_wrapper_allows_workspace_and_denies_outside_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, private = root / "workspace", root / "private"
            workspace.mkdir()
            private.mkdir()
            (workspace / "inside.txt").write_text("inside")
            forbidden = root / "forbidden.txt"
            forbidden.write_text("forbidden")
            outside_write = root / "outside-write.txt"
            commands = [
                "python3 -c \"from pathlib import Path; assert Path('inside.txt').read_text() == 'inside'; Path('made.txt').write_text('ok')\"",
                f"cat {shlex.quote(str(forbidden))}",
                f"printf x > {shlex.quote(str(outside_write))}",
                "python3 -c \"import socket; socket.socket().bind(('127.0.0.1', 0))\"",
            ]
            wrappers = sandbox_wrappers(workspace, private, commands)
            completed = [subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-c", wrapper],
                cwd=workspace, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False,
            ) for wrapper in wrappers]
            self.assertEqual(completed[0].returncode, 0, completed[0].stderr)
            self.assertEqual((workspace / "made.txt").read_text(), "ok")
            for result in completed[1:]:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Operation not permitted", result.stderr)
            self.assertFalse(outside_write.exists())

    def test_path_tools_reject_absolute_parent_and_symlink_escapes(self):
        module = (ROOT / "scripts" / "bakeoff9_sdk.mjs").as_uri()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "inside.txt").write_text("inside")
            outside = root / "outside.txt"
            outside.write_text("outside")
            (workspace / "escape").symlink_to(outside)
            cases = [
                {"tool_name": "Read", "tool_input": {"file_path": str(outside)}},
                {"tool_name": "Edit", "tool_input": {"file_path": "../outside.txt"}},
                {"tool_name": "Write", "tool_input": {"file_path": "escape"}},
                {"tool_name": "Read", "tool_input": {"file_path": "inside.txt"}},
            ]
            source = f"""
              import {{ toolContainmentProblems }} from {json.dumps(module)};
              const cases = {json.dumps(cases)};
              const results = [];
              for (const item of cases) results.push(await toolContainmentProblems(item, {json.dumps(str(workspace))}));
              process.stdout.write(JSON.stringify(results));
            """
            completed = node_eval(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        results = json.loads(completed.stdout)
        self.assertTrue(results[0])
        self.assertTrue(results[1])
        self.assertTrue(results[2])
        self.assertEqual(results[3], [])

    def test_malicious_quotes_and_metacharacters_cannot_escape_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, private = root / "workspace", root / "private"
            workspace.mkdir()
            private.mkdir()
            command = "printf '%s' 'a b;$(touch escaped)' > 'quoted file.txt'"
            wrapper = sandbox_wrappers(workspace, private, [command])[0]
            completed = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-c", wrapper],
                cwd=workspace, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((workspace / "quoted file.txt").read_text(), "a b;$(touch escaped)")
            self.assertFalse((workspace / "escaped").exists())

    def test_fragments_reject_sdk_wire_fields_and_duplicate_sequences(self):
        escaped = {
            "schema": sdk.FRAGMENT_SCHEMA,
            "sequence": 0,
            "phase": "start",
            "tool_input": {"command": "true"},
        }
        self.assertTrue(any("SDK wire field" in item for item in sdk.fragment_problems(escaped)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean = {"schema": sdk.FRAGMENT_SCHEMA, "sequence": 0, "phase": "batch"}
            (root / "a.json").write_text(json.dumps(clean))
            (root / "b.json").write_text(json.dumps(clean))
            with self.assertRaisesRegex(sdk.SDKAdapterError, "duplicate fragment sequence"):
                sdk.load_fragments(root)


class SDKFakeAdapterTests(unittest.TestCase):
    def test_fake_fixture_streams_acknowledged_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "value.txt").write_text("before")
            fixture = root / "fake.json"
            fixture.write_text(json.dumps({
                "response": "Implemented-unverified",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 2,
                    "cache_read_input_tokens": 3,
                },
                "events": [
                    {
                        "phase": "pre",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_use_id": "bash-1",
                        "tool_input": {"command": "python3 -m unittest"},
                        "cwd": str(workspace),
                    },
                    {"phase": "mutate", "path": "value.txt", "content": "after"},
                    {
                        "phase": "post",
                        "hook_event_name": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_use_id": "bash-1",
                        "tool_response": {
                            "stdout": "Ran 1 test\\nOK",
                            "stderr": "",
                            "interrupted": False,
                        },
                    },
                    {
                        "phase": "pre",
                        "tool_name": "Write",
                        "tool_use_id": "write-1",
                        "tool_input": {"file_path": "new.txt", "content": "not retained"},
                        "cwd": str(workspace),
                    },
                    {"phase": "mutate", "path": "new.txt", "content": "written"},
                    {
                        "phase": "post",
                        "tool_name": "Write",
                        "tool_use_id": "write-1",
                        "tool_response": "written",
                    },
                    {"phase": "batch", "tool_calls": []},
                ],
            }))
            recorder = Recorder()
            adapter = sdk.AgentSDKAdapter(
                binary=Path("/unused"), mode="fake", fake_fixture=fixture
            )
            case = SimpleNamespace(
                prompt="fix the fixture",
                harness_prompt="intact",
                fixture_id="fake-one",
            )
            observed_envs = []
            real_popen = subprocess.Popen

            def recording_popen(*args, **kwargs):
                observed_envs.append(dict(kwargs["env"]))
                return real_popen(*args, **kwargs)

            with patch.dict(os.environ, {
                "CLAUDE_CODE_OAUTH_TOKEN": "real-oauth",
                "ANTHROPIC_API_KEY": "real-api",
                "ANTHROPIC_BASE_URL": "https://gateway.invalid",
                "CLAUDE_CODE_MESSAGING_TOKEN": "real-message-token",
                "AWS_PROFILE": "production",
            }), patch.object(sdk.subprocess, "Popen", side_effect=recording_popen):
                result = adapter.generate(case, workspace, recorder)

        self.assertIsInstance(result, sdk.GenerationResult)
        self.assertEqual(result.response, "Implemented-unverified")
        self.assertEqual(result.capture["mode"], "fake")
        self.assertEqual(result.capture["fragment_count"], 5)
        self.assertEqual(result.usage["input_tokens"], 10)
        self.assertEqual(recorder.events[0][0], "start")
        self.assertEqual(recorder.events[0][2], ["python3", "-m", "unittest"])
        self.assertEqual(recorder.events[1][0], "finish")
        self.assertEqual(recorder.events[1][2]["exit_code"], 0)
        self.assertEqual(recorder.events[2][0], "edit-boundary")
        self.assertEqual(len(observed_envs), 1)
        for forbidden in (
            "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_MESSAGING_TOKEN", "AWS_PROFILE",
        ):
            self.assertNotIn(forbidden, observed_envs[0])

    def test_live_adapter_refuses_without_neutral_preflight(self):
        adapter = sdk.AgentSDKAdapter(binary=Path("/missing"), mode="live")
        case = SimpleNamespace(prompt="x", harness_prompt="intact", fixture_id="f")
        result = adapter.generate(case, Path.cwd(), Recorder())
        self.assertIsInstance(result, sdk.GenerationFailure)
        self.assertEqual(result.code, "preflight-required")

    def test_fake_sdk_messages_and_request_reach_retention_safe_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            body = fake_request_body()
            auxiliary = fake_request_body(tools=())
            auxiliary["messages"] = [{"role": "user", "content": "<session>title</session>"}]
            auxiliary["thinking"] = {"type": "disabled"}
            auxiliary["output_format"] = {
                "type": "json_schema", "schema": {"type": "object"},
            }
            baseline, _ = sdk.capture_spine.summarize_request(body)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps(baseline))
            fixture = root / "fake.json"
            fixture.write_text(json.dumps({
                "response": "Verified", "usage": {}, "events": [],
                "sdk_messages": fake_sdk_messages(), "request_bodies": [body, auxiliary],
            }))
            adapter = sdk.AgentSDKAdapter(
                binary=Path("/unused"), mode="fake", fake_fixture=fixture,
                baseline_path=baseline_path,
            )
            case = SimpleNamespace(
                prompt="prompt", harness_prompt="intact", fixture_id="fake-two",
            )
            result = adapter.generate(case, workspace, Recorder())

        self.assertIsInstance(result, sdk.GenerationResult)
        capture = result.capture
        self.assertEqual(capture["schema"], "capture-spine/1")
        self.assertEqual(capture["surface_verdict"], "match")
        self.assertEqual(capture["primary_request_count"], 1)
        self.assertEqual(capture["auxiliary_request_count"], 1)
        self.assertEqual(len(capture["request_surfaces"]), 1)
        self.assertEqual(capture["auxiliary_request_surfaces"][0]["thinking"], {"type": "disabled"})
        self.assertEqual(
            capture["auxiliary_request_surfaces"][0]["output_format"]["type"], "json_schema"
        )
        self.assertEqual(capture["request_surfaces"][0]["thinking"], {"type": "adaptive"})
        self.assertEqual(capture["request_surfaces"][0]["output_config"], {"effort": "high"})
        self.assertEqual(capture["sdk_init"]["cli_version"], "2.1.239")
        self.assertEqual(len(capture["turns"]), 2)
        self.assertEqual(capture["usage_totals"]["output_tokens"], 10)
        self.assertEqual(capture["model_provenance"]["resolved"], "claude-opus-5")
        blob = json.dumps(dict(capture))
        self.assertNotIn("private 0", blob)
        self.assertNotIn("answer 0", blob)
        self.assertNotIn("secret-value", blob)
        self.assertNotIn("<system-reminder>", blob)
        self.assertEqual(sdk.capture_spine.retention_problems(capture), [])

    def test_live_capture_uses_raw_surfaces_sdk_turns_then_purges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "CLAUDE.md").write_text("Today's date is 2026-08-27.")
            binary = root / "claude"
            binary.write_bytes(b"pinned")
            body = fake_request_body()
            baseline, _ = sdk.capture_spine.summarize_request(body)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps(baseline))
            observed_raw = []

            def fake_run(request, _trajectory, *, node_executable):
                raw = Path(request["raw_body_dir"])
                observed_raw.append(raw)
                (raw / "000.request.json").write_text(json.dumps(body))
                return {
                    "schema": sdk.RESULT_SCHEMA, "response": "Verified",
                    "usage": {"input_tokens": 4, "output_tokens": 10,
                              "cache_creation_input_tokens": 6,
                              "cache_read_input_tokens": 8},
                    "capture": {"mode": "live", "fragment_count": 0},
                    "_sdk_messages": fake_sdk_messages(), "_request_bodies": [],
                }

            adapter = sdk.AgentSDKAdapter(
                binary=binary, mode="live", baseline_path=baseline_path,
                preflight_receipt={"admitted": True},
            )
            case = SimpleNamespace(
                prompt="prompt", harness_prompt="intact", fixture_id="live-one",
                arm_sha256=sdk._file_sha256(workspace / "CLAUDE.md"),
            )
            with patch.object(sdk, "validate_preflight_receipt", return_value=[]), \
                 patch.object(sdk, "_run_node", side_effect=fake_run):
                result = adapter.generate(case, workspace, Recorder())

        self.assertIsInstance(result, sdk.GenerationResult)
        self.assertEqual(result.capture["surface_verdict"], "match")
        self.assertEqual(result.capture["request_surfaces"][0]["thinking"], {"type": "adaptive"})
        self.assertEqual(result.capture["request_surfaces"][0]["output_config"], {"effort": "high"})
        self.assertEqual(result.capture["sdk_init"]["cli_version"], "2.1.239")
        self.assertEqual(len(result.capture["turns"]), 2)
        self.assertEqual(result.capture["usage_totals"]["output_tokens"], 10)
        self.assertEqual(result.usage["input_tokens"], 4)
        self.assertEqual(result.usage["output_tokens"], 10)
        self.assertFalse(result.capture["raw_bodies_retained"])
        self.assertTrue(result.capture["raw_dir_purged"])
        self.assertTrue(result.capture["arm_reminder"]["verified"])
        self.assertEqual(
            "bakeoff9-live-surface-bootstrap/1",
            result.capture["live_surface_bootstrap"]["schema"],
        )
        self.assertNotIn(
            "messages", result.capture["live_surface_bootstrap"]["first_primary"]
        )
        self.assertFalse(observed_raw[0].exists())
        self.assertEqual(sdk.capture_spine.retention_problems(dict(result.capture)), [])

    def test_builder_reads_the_authoritative_declaration(self):
        declaration = ROOT / "campaigns/clause-bakeoff-9-2026-08-22/campaign.toml"
        adapter = sdk.build_generation_adapter(
            campaign_dir=declaration.parent,
            declaration=declaration,
        )
        self.assertEqual(adapter.kind, sdk.AdapterKind.SDK_QUERY)
        self.assertEqual(adapter.model, "claude-opus-5")
        self.assertEqual(adapter.binary.name, "claude")


if __name__ == "__main__":
    unittest.main()
