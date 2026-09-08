"""Unit tests for scripts/capture_spine.py.

Two things are load-bearing here and are tested as such: the sanitizer, because
B1 fixtures include absent-credential cases and a leak is permanent; and the
record shape, because T-005, T-006 and T-012 all code against it.
"""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capture_spine as cs  # noqa: E402

SECRET = "sk-ant-api03-NOTAREALKEYbutlooksLikeOne0000"
TEXT_SIDECAR = (Path(__file__).resolve().parents[1]
                / "sources/2026-08-24-t001-surface-sdk-declared.text.json")
PRIVATE_ARTIFACTS = "requires private lab artifacts that are not included in the public release"


def request_body(*, system=("alpha", "bravo"), tools=("Bash", "Read"),
                 reminder="<system-reminder>\nToday's date is 2026-08-24.\n</system-reminder>",
                 user="ping", mid="<total_tokens>15000000 tokens left</total_tokens>",
                 cwd="/private/tmp/fixture-a", cc_version=None):
    """A request body shaped like the ones the probe and OTEL actually write.

    `cc_version` prepends the billing block real captures carry as system block
    0; its fourth component tracks the user prompt (T-016).
    """
    blocks = list(system)
    if cc_version is not None:
        blocks.insert(0, f"x-anthropic-billing-header: cc_version={cc_version}; cc_entrypoint=cli")
    blocks[-1] = blocks[-1] + f"\n# Environment\n - Primary working directory: {cwd}\n - Is a git repository: false"
    messages = [{"role": "user", "content": [{"type": "text", "text": reminder},
                                             {"type": "text", "text": user}]}]
    if mid is not None:
        messages.append({"role": "system", "content": mid})
    return {
        "model": "claude-opus-5",
        "max_tokens": 64000,
        "system": [{"type": "text", "text": t} for t in blocks],
        "tools": [{"name": n, "description": f"{n} does things",
                   "input_schema": {"type": "object", "properties": {}}} for n in tools],
        "messages": messages,
        "metadata": {"user_id": '{"device_id":"abc","account_uuid":""}'},
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
        "stream": True,
    }


def session_row(*, request_id="req_1", uuid="u1", tool_input=None, stop_reason="end_turn",
                thinking="pondering", text="answer"):
    content = [{"type": "thinking", "thinking": thinking, "signature": "sig"},
               {"type": "text", "text": text}]
    if tool_input is not None:
        content.append({"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": tool_input})
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": "p1",
        "requestId": request_id,
        "timestamp": "2026-08-25T00:00:00.000Z",
        "version": "2.1.239",
        "entrypoint": "sdk-ts",
        "effort": "high",
        "cwd": "/private/tmp/fixture-a",
        "gitBranch": "main",
        "isSidechain": False,
        "sessionId": "497b288f-8a77-48a8-a8c3-3ebddf7e0f03",
        "message": {
            "id": "msg_1",
            "model": "claude-opus-5",
            "role": "assistant",
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "content": content,
            "usage": {
                "input_tokens": 2,
                "output_tokens": 419,
                "cache_creation_input_tokens": 26419,
                "cache_read_input_tokens": 11,
                "output_tokens_details": {"thinking_tokens": 210},
                "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 26419},
                "service_tier": "standard",
            },
        },
    }


def sdk_messages():
    init = {
        "type": "system", "subtype": "init", "claude_code_version": "2.1.239",
        "cwd": "/private/tmp/fixture-a", "model": "claude-opus-5",
        "apiKeySource": "oauth", "permissionMode": "default",
        "tools": ["Bash", "Read", "Edit", "Write", "Grep", "Glob"],
    }
    turns = []
    for index in range(2):
        row = session_row(
            request_id=f"req_{index}", uuid=f"u{index}",
            thinking=f"private reasoning {index}",
            text=f"visible answer {index} <system-reminder>hidden</system-reminder>",
            tool_input={"command": f"ANTHROPIC_API_KEY={SECRET} python3 -m unittest"},
        )
        turns.append({
            "type": "assistant", "uuid": row["uuid"],
            "request_id": row["requestId"], "timestamp": row["timestamp"],
            "session_id": row["sessionId"], "parent_tool_use_id": None,
            "effort": "high", "message": row["message"],
        })
    return [init, *turns]


class Canonicalization(unittest.TestCase):
    def test_canonical_form_is_sorted_default_separators(self):
        self.assertEqual(cs.canonical({"b": 1, "a": 2}), '{"a": 2, "b": 1}')

    def test_structural_digest_matches_hand_computed_sha256(self):
        form = '{"a": 2, "b": 1}'
        self.assertEqual(cs.structural_digest({"b": 1, "a": 2}),
                         {"chars": len(form), "sha256": hashlib.sha256(form.encode()).hexdigest()})

    def test_text_and_structural_rules_are_different(self):
        self.assertNotEqual(cs.sha256_text("x"), cs.sha256_structural("x"))


class Sanitizer(unittest.TestCase):
    def test_redacts_anthropic_key(self):
        self.assertNotIn(SECRET, cs.redact(f"export ANTHROPIC_API_KEY={SECRET}"))

    def test_redacts_bearer_and_github_token(self):
        self.assertNotIn("abc123", cs.redact("Authorization: Bearer abc123"))
        self.assertNotIn("ghp_" + "a" * 20, cs.redact("token ghp_" + "a" * 20))

    def test_leaves_ordinary_text_alone(self):
        text = "python3 -m unittest discover -s tests"
        self.assertEqual(cs.redact(text), text)

    def test_auth_shaped_key_detection(self):
        for name in ("api_key", "ANTHROPIC_API_KEY", "authToken", "x-api-key", "client.secret", "password"):
            self.assertTrue(cs.is_auth_shaped_key(name), name)
        for name in ("command", "file_path", "description", "offset", "pattern"):
            self.assertFalse(cs.is_auth_shaped_key(name), name)

    def test_auth_shaped_argument_is_withheld_not_hashed(self):
        summary = cs.summarize_arguments({"api_key": SECRET, "command": "ls"})
        by_key = {entry["key"]: entry for entry in summary}
        self.assertEqual(by_key["api_key"], {"key": "api_key", "withheld": True})
        self.assertNotIn("sha256", by_key["api_key"])
        self.assertIn("sha256", by_key["command"])

    def test_secret_inside_an_argument_value_is_redacted_before_hashing(self):
        a = cs.summarize_arguments({"command": f"ANTHROPIC_API_KEY={SECRET} ./run.sh"})[0]
        b = cs.summarize_arguments({"command": "ANTHROPIC_API_KEY=sk-ant-api03-DIFFERENT ./run.sh"})[0]
        self.assertTrue(a["redacted"])
        self.assertEqual(a["sha256"], b["sha256"],
                         "two commands differing only inside the credential must not be distinguishable")

    def test_campaign_token_assignments_are_redacted_before_hashing(self):
        for name in ("REGISTRY_TOKEN", "REPORTS_API_TOKEN"):
            with self.subTest(name=name):
                a = cs.sanitized_digest(f"{name}=hunter2")
                b = cs.sanitized_digest(f"{name}=different")
                self.assertTrue(a["redacted"])
                self.assertEqual(a["sha256"], b["sha256"])

    def test_named_credential_assignment_suffixes_are_redacted(self):
        for suffix in ("TOKEN", "KEY", "SECRET", "PASSWORD"):
            with self.subTest(suffix=suffix):
                self.assertEqual(cs.redact(f"SERVICE_{suffix}=hunter2"),
                                 f"SERVICE_{suffix}=<redacted>")

    def test_cli_style_credential_flags_are_redacted(self):
        self.assertEqual(cs.redact("--password hunter2"), "--password <redacted>")
        self.assertEqual(cs.redact("--reports-api-token hunter2"), "--reports-api-token <redacted>")
        a = cs.sanitized_digest("--password hunter2")
        b = cs.sanitized_digest("--password different")
        self.assertTrue(a["redacted"])
        self.assertEqual(a["sha256"], b["sha256"])

    def test_credential_vocabulary_without_an_assignment_is_not_redacted(self):
        text = "Dual-use credential testing requires clear authorization context."
        self.assertEqual(cs.redact(text), text)

    def test_clean_argument_is_not_marked_redacted(self):
        entry = cs.summarize_arguments({"command": "ls -la"})[0]
        self.assertFalse(entry["redacted"])
        self.assertEqual(entry["chars"], len("ls -la"))


class RetentionBoundary(unittest.TestCase):
    def test_clean_record_has_no_problems(self):
        record = {"sha256": "a" * 64, "chars": 310, "cwd": "/private/tmp/fixture-a"}
        self.assertEqual(cs.retention_problems(record), [])

    def test_flags_reminder_payload(self):
        problems = cs.retention_problems({"messages": [{"text": "<system-reminder>secret ambient state</system-reminder>"}]})
        self.assertTrue(any("system-reminder" in p for p in problems))

    def test_flags_credential_text_anywhere_in_the_tree(self):
        problems = cs.retention_problems({"trials": [{"turns": [{"note": f"key {SECRET}"}]}]})
        self.assertTrue(any("credential-shaped" in p for p in problems))

    def test_flags_authorization_shaped_key_carrying_a_value(self):
        problems = cs.retention_problems({"api_key": "anything"})
        self.assertTrue(any("authorization-shaped" in p for p in problems))

    def test_withheld_marker_is_accepted_under_an_auth_shaped_key(self):
        self.assertEqual(cs.retention_problems({"api_key": cs.WITHHELD}), [])

    def test_flags_free_text_past_the_record_limit(self):
        problems = cs.retention_problems({"blob": "x" * (cs.MAX_RECORD_STRING + 1)})
        self.assertTrue(any("exceeds the record limit" in p for p in problems))

    def test_write_record_refuses_a_dirty_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.json"
            with self.assertRaises(ValueError):
                cs.write_record(target, {"note": f"key {SECRET}"})
            self.assertFalse(target.exists())

    def test_write_record_writes_a_clean_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sub" / "out.json"
            cs.write_record(target, {"sha256": "b" * 64})
            self.assertEqual(json.loads(target.read_text()), {"sha256": "b" * 64})

    @unittest.skipUnless(TEXT_SIDECAR.exists(), PRIVATE_ARTIFACTS)
    def test_committed_system_prompt_sidecar_passes_its_text_policy(self):
        repo = Path(cs.__file__).resolve().parent.parent
        sidecar = json.loads(
            (repo / "sources/2026-08-24-t001-surface-sdk-declared.text.json").read_text()
        )
        self.assertGreater(max(map(len, sidecar["system_blocks"])), cs.MAX_RECORD_STRING)
        self.assertEqual(cs.text_retention_problems(sidecar), [])

    @unittest.skipUnless(TEXT_SIDECAR.exists(), PRIVATE_ARTIFACTS)
    def test_text_sidecar_writer_writes_the_committed_system_prompt(self):
        repo = Path(cs.__file__).resolve().parent.parent
        sidecar = json.loads(
            (repo / "sources/2026-08-24-t001-surface-sdk-declared.text.json").read_text()
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "capture.text.json"
            cs.write_text_record(target, sidecar)
            self.assertEqual(json.loads(target.read_text()), sidecar)

    def test_text_sidecar_writer_refuses_an_actual_credential(self):
        sidecar = {
            "system_blocks": ["REPORTS_API_TOKEN=hunter2"],
            "mid_turn_system": None,
            "note": cs.TEXT_SIDECAR_NOTE,
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "capture.text.json"
            with self.assertRaises(ValueError):
                cs.write_text_record(target, sidecar)
            self.assertFalse(target.exists())

    def test_text_sidecar_writer_refuses_reminder_payloads(self):
        sidecar = {
            "system_blocks": ["system prompt"],
            "mid_turn_system": None,
            "note": cs.TEXT_SIDECAR_NOTE,
        }
        reminder = "<system-reminder>secret ambient state</system-reminder>"
        for field in ("system_blocks", "mid_turn_system", "note"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                candidate = dict(sidecar)
                candidate[field] = [reminder] if field == "system_blocks" else reminder
                target = Path(tmp) / "capture.text.json"
                with self.assertRaisesRegex(ValueError, "system-reminder"):
                    cs.write_text_record(target, candidate)
                self.assertFalse(target.exists())

    def test_text_sidecar_writer_refuses_an_arbitrary_note(self):
        sidecar = {
            "system_blocks": ["system prompt"],
            "mid_turn_system": None,
            "note": "x" * 5000,
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "capture.text.json"
            with self.assertRaisesRegex(ValueError, "policy declaration"):
                cs.write_text_record(target, sidecar)
            self.assertFalse(target.exists())

    def test_purge_raw_refuses_a_directory_inside_the_repository(self):
        repo = Path(cs.__file__).resolve().parent.parent
        with self.assertRaises(ValueError):
            cs.purge_raw(repo / "sources")

    def test_purge_raw_deletes_a_transient_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "body.json").write_text("{}")
            self.assertTrue(cs.purge_raw(raw))
            self.assertFalse(raw.exists())


class RequestSurface(unittest.TestCase):
    def test_summarizes_a_bare_body_and_a_probe_wrapper_identically(self):
        body = request_body()
        bare, _ = cs.summarize_request(body)
        wrapped, _ = cs.summarize_request({"path": "/v1/messages", "headers": {}, "body": body})
        self.assertEqual(cs.surface_key(bare), cs.surface_key(wrapped))

    def test_drops_credential_headers_and_metadata(self):
        summary, _ = cs.summarize_request(
            {"headers": {"x-api-key": SECRET, "User-Agent": "claude-cli/2.1.239",
                         "X-Claude-Code-Session-Id": "s1"},
             "body": request_body()})
        self.assertEqual(set(summary["headers"]), {"user-agent"})
        self.assertEqual(summary["dropped_body_keys"], ["metadata"])
        self.assertEqual(cs.retention_problems(summary), [])

    def test_records_reminder_by_presence_count_and_hash_only(self):
        summary, _ = cs.summarize_request(request_body())
        reminder = summary["system_reminder"]
        self.assertEqual((reminder["present"], reminder["count"]), (True, 1))
        self.assertEqual(set(reminder) & {"text", "payload", "content"}, set())

    def test_reminder_date_normalized_hash_is_stable_across_days(self):
        a, _ = cs.summarize_request(request_body(reminder="<system-reminder>date 2026-08-24</system-reminder>"))
        b, _ = cs.summarize_request(request_body(reminder="<system-reminder>date 2026-08-25</system-reminder>"))
        self.assertNotEqual(a["system_reminder"]["sha256"], b["system_reminder"]["sha256"])
        self.assertEqual(a["system_reminder"]["date_normalized_sha256"],
                         b["system_reminder"]["date_normalized_sha256"])

    def test_system_normalized_hash_is_stable_across_working_directories(self):
        a, _ = cs.summarize_request(request_body(cwd="/private/tmp/fixture-a"))
        b, _ = cs.summarize_request(request_body(cwd="/private/tmp/fixture-bbbb"))
        self.assertNotEqual(a["system_joined_sha256"], b["system_joined_sha256"])
        self.assertEqual(a["system_joined_normalized_sha256"], b["system_joined_normalized_sha256"])
        self.assertEqual(cs.surface_diff(a, b), [])

    def test_surface_diff_names_each_changed_surface(self):
        base, _ = cs.summarize_request(request_body())
        self.assertEqual(cs.surface_diff(*[cs.summarize_request(request_body(tools=("Bash", "Read")))[0]] * 2), [])
        wider, _ = cs.summarize_request(request_body(tools=("Bash", "Read", "Write")))
        self.assertEqual(cs.surface_diff(wider, base), ["tools"])
        other, _ = cs.summarize_request(request_body(system=("alpha", "CHARLIE")))
        self.assertEqual(cs.surface_diff(other, base), ["system"])
        mid, _ = cs.summarize_request(request_body(mid="<total_tokens>1 tokens left</total_tokens>"))
        self.assertEqual(cs.surface_diff(mid, base), ["mid_turn_system"])

    def test_one_baseline_grades_trials_at_different_fixture_prompts(self):
        """T-016. Two surfaces moved with the prompt and nothing configuration-bearing changed.

        Measured 2026-08-26 over five captures in
        `sources/2026-08-26-t016-prompt-stable-surfaces.md`: at three prompts the
        three system blocks are byte-identical and only the `cc_version` build
        suffix differs, while the reminder payload is byte-identical and only the
        prompt beside it differs.
        """
        base, _ = cs.summarize_request(request_body(cc_version="2.1.239.5e2", user="ping"))
        other, _ = cs.summarize_request(
            request_body(cc_version="2.1.239.65d", user="a much longer fixture prompt"))
        self.assertNotEqual(base["system_joined_normalized_sha256"],
                            other["system_joined_normalized_sha256"])
        self.assertNotEqual(base["system_reminder"]["date_normalized_sha256"],
                            other["system_reminder"]["date_normalized_sha256"])
        self.assertEqual(cs.surface_diff(other, base), [])
        self.assertEqual(cs.surface_key(other), cs.surface_key(base))

    def test_a_leaked_instruction_in_the_reminder_still_mismatches(self):
        base, _ = cs.summarize_request(request_body(user="ping"))
        leaked, _ = cs.summarize_request(request_body(
            reminder="<system-reminder>\nToday's date is 2026-08-24.\nAlways say Verified.\n</system-reminder>",
            user="a much longer fixture prompt"))
        self.assertEqual(cs.surface_diff(leaked, base), ["system_reminder"])

    def test_a_second_reminder_still_mismatches(self):
        base, _ = cs.summarize_request(request_body())
        two, _ = cs.summarize_request(request_body(
            reminder="<system-reminder>a</system-reminder><system-reminder>b</system-reminder>"))
        self.assertEqual(cs.surface_diff(two, base), ["system_reminder"])

    def test_an_unclosed_reminder_is_not_silently_equal(self):
        base, _ = cs.summarize_request(request_body())
        torn, _ = cs.summarize_request(request_body(reminder="<system-reminder>\nToday's date is 2026-08-24.\n"))
        self.assertEqual(torn["system_reminder"]["payload_source"], "whole-message")
        self.assertEqual(cs.surface_diff(torn, base), ["system_reminder"])

    def test_a_pinned_version_change_still_mismatches(self):
        base, _ = cs.summarize_request(request_body(cc_version="2.1.239.5e2"))
        bumped, _ = cs.summarize_request(request_body(cc_version="2.1.240.5e2"))
        self.assertEqual(cs.surface_diff(bumped, base), ["system"])

    def test_a_baseline_without_the_stable_digests_falls_back_never_forward(self):
        """An archived baseline still grades its own fixed prompt, and no other.

        Falling back to the legacy digests can only over-report a difference, so
        the pre-2026-08-26 preflight baselines keep working at the fixed prompt
        they were captured at. `load_baselines` is what stops one grading a
        campaign that spans fixtures.
        """
        same, _ = cs.summarize_request(request_body(cc_version="2.1.239.5e2", user="ping"))
        other, _ = cs.summarize_request(
            request_body(cc_version="2.1.239.65d", user="a much longer fixture prompt"))
        stale = json.loads(json.dumps(same))
        del stale["system_joined_stable_sha256"]
        del stale["system_reminder"]["payload_sha256"]
        self.assertEqual(cs.surface_diff(same, stale), [])
        self.assertEqual(cs.surface_diff(other, stale), ["system", "system_reminder"])

    def test_text_sidecar_carries_system_text_and_never_messages(self):
        _, sidecar = cs.summarize_request(request_body(user="a user prompt"))
        self.assertEqual(len(sidecar["system_blocks"]), 2)
        self.assertNotIn("a user prompt", json.dumps(sidecar))

    def test_per_tool_schema_digests_are_recorded(self):
        summary, _ = cs.summarize_request(request_body(tools=("Bash", "Read")))
        self.assertEqual(sorted(summary["tool_schemas"]), ["Bash", "Read"])
        self.assertIn("sha256", summary["tool_schemas"]["Bash"])


class TurnRecord(unittest.TestCase):
    def test_carries_every_field_the_ticket_names(self):
        record = cs.turn_record(session_row(), 0)
        for key in ("version", "effort", "model", "request_id", "cwd", "stop_reason", "usage"):
            self.assertIn(key, record)
        self.assertEqual(record["usage"]["thinking_tokens"], 210)
        self.assertEqual(record["usage"]["cache_creation_input_tokens"], 26419)
        self.assertEqual(record["usage"]["cache_read_input_tokens"], 11)
        self.assertEqual(record["usage"]["cache_creation_1h_input_tokens"], 26419)

    def test_session_identifier_is_hashed_not_retained(self):
        record = cs.turn_record(session_row(), 0)
        self.assertNotIn("session_id", record)
        self.assertEqual(record["session_sha256"],
                         cs.sha256_text("497b288f-8a77-48a8-a8c3-3ebddf7e0f03"))

    def test_thinking_and_text_are_counted_never_stored(self):
        record = cs.turn_record(session_row(thinking="private reasoning", text="visible answer"), 0)
        self.assertEqual(record["content"]["thinking_blocks"], 1)
        self.assertEqual(record["content"]["thinking_chars"], len("private reasoning"))
        self.assertNotIn("private reasoning", json.dumps(record))
        self.assertNotIn("visible answer", json.dumps(record))

    def test_tool_call_with_an_absent_credential_leaves_no_secret(self):
        row = session_row(tool_input={"command": f"ANTHROPIC_API_KEY={SECRET} python3 scripts/check_auth.py",
                                      "api_key": SECRET})
        record = cs.turn_record(row, 0)
        blob = json.dumps(record)
        self.assertNotIn(SECRET, blob)
        self.assertEqual(cs.retention_problems(record), [])
        arguments = {a["key"]: a for a in record["content"]["tool_uses"][0]["arguments"]}
        self.assertTrue(arguments["api_key"]["withheld"])
        self.assertTrue(arguments["command"]["redacted"])

    def test_turn_records_keeps_assistant_rows_in_order_and_skips_the_rest(self):
        lines = [
            json.dumps({"type": "user", "message": {"role": "user"}}),
            json.dumps(session_row(uuid="a", request_id="req_a")),
            "",
            "not json",
            json.dumps({"type": "assistant"}),
            json.dumps(session_row(uuid="b", request_id="req_b")),
        ]
        records = cs.turn_records(lines)
        self.assertEqual([r["request_id"] for r in records], ["req_a", "req_b"])
        self.assertEqual([r["turn_index"] for r in records], [0, 1])

    def test_transport_error_rows_are_marked_and_not_summed(self):
        row = session_row()
        row["isApiErrorMessage"] = True
        row["message"]["model"] = "<synthetic>"
        records = cs.turn_records([json.dumps(session_row()), json.dumps(row)])
        self.assertEqual([r["api_error"] for r in records], [False, True])
        totals = cs.usage_totals(records)
        self.assertEqual(totals["turns"], 1)
        self.assertEqual(totals["api_error_turns"], 1)
        self.assertEqual(totals["output_tokens"], 419)

    def test_usage_totals_sum_across_turns(self):
        totals = cs.usage_totals(cs.turn_records([json.dumps(session_row()), json.dumps(session_row())]))
        self.assertEqual(totals["turns"], 2)
        self.assertEqual(totals["api_error_turns"], 0)
        self.assertEqual(totals["thinking_tokens"], 420)
        self.assertEqual(totals["output_tokens"], 838)


class SDKStreamCapture(unittest.TestCase):
    def test_frozen_legacy_baseline_can_gain_verified_prompt_stable_companions(self):
        reference, _ = cs.summarize_request(request_body(
            user="ping", cc_version="2.1.239.basebuild"
        ))
        frozen = json.loads(json.dumps(reference))
        frozen.pop("system_joined_stable_sha256")
        for key in ("payload_chars", "payload_sha256", "payload_source"):
            frozen["system_reminder"].pop(key)
        enriched = cs.prompt_stable_baseline(frozen, reference)
        changed, _ = cs.summarize_request(request_body(
            user="a different fixture prompt", cwd="/private/tmp/other-fixture",
            cc_version="2.1.239.otherbuild",
        ))
        self.assertEqual(cs.surface_diff(changed, enriched), [])

    def test_arm_reference_may_replace_only_the_generic_reminder(self):
        reference, _ = cs.summarize_request(request_body(user="ping"))
        frozen = json.loads(json.dumps(reference))
        frozen["system_reminder"]["payload_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "system_reminder"):
            cs.prompt_stable_baseline(frozen, reference)

        enriched = cs.prompt_stable_baseline(
            frozen, reference, allowed_reference_differences=("system_reminder",)
        )
        self.assertEqual(
            reference["system_reminder"]["payload_sha256"],
            enriched["system_reminder"]["payload_sha256"],
        )
        wrong_system = json.loads(json.dumps(reference))
        wrong_system["system_joined_stable_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "system"):
            cs.prompt_stable_baseline(
                frozen, wrong_system,
                allowed_reference_differences=("system_reminder",),
            )

    def test_auxiliary_classification_matches_cli_rule_and_partitions(self):
        primary = request_body()
        auxiliary = request_body(tools=(), reminder="", user="<session>title me</session>")
        auxiliary["thinking"] = {"type": "disabled"}
        auxiliary["output_format"] = {"type": "json_schema", "schema": {"type": "object"}}
        malformed_primary = request_body(tools=())
        self.assertFalse(cs.is_auxiliary_request(primary))
        self.assertTrue(cs.is_auxiliary_request(auxiliary))
        self.assertFalse(cs.is_auxiliary_request(malformed_primary))
        main, helper = cs.partition_request_records(
            [primary, auxiliary, malformed_primary]
        )
        self.assertEqual(main, [primary, malformed_primary])
        self.assertEqual(helper, [auxiliary])
        summary = cs.observed_surface_records(helper, None)[0]
        self.assertEqual(summary["thinking"], {"type": "disabled"})
        self.assertEqual(summary["output_format"]["type"], "json_schema")

    def test_init_and_two_assistant_turns_use_the_existing_sanitized_shape(self):
        record = cs.sdk_capture_record(sdk_messages())
        self.assertEqual(record["init"]["cli_version"], "2.1.239")
        self.assertEqual(record["init"]["model"], "claude-opus-5")
        self.assertEqual(record["init"]["account_source"], "oauth")
        self.assertEqual(len(record["turns"]), 2)
        self.assertEqual(record["turns"][0]["effort"], "high")
        self.assertEqual(record["turns"][0]["usage"]["thinking_tokens"], 210)
        self.assertEqual(record["usage_totals"]["output_tokens"], 838)
        self.assertEqual(record["cli_versions"]["observed"], ["2.1.239"])
        blob = json.dumps(record)
        self.assertNotIn("private reasoning", blob)
        self.assertNotIn("visible answer", blob)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("<system-reminder>", blob)
        self.assertEqual(cs.retention_problems(record), [])

    def test_in_memory_request_surfaces_keep_thinking_and_output_config(self):
        body = request_body()
        baseline, _ = cs.summarize_request(body)
        surfaces = cs.observed_surface_records([body, body], baseline)
        self.assertEqual(len(surfaces), 1)
        self.assertEqual(surfaces[0]["count"], 2)
        self.assertEqual(surfaces[0]["thinking"], {"type": "adaptive"})
        self.assertEqual(surfaces[0]["output_config"], {"effort": "high"})
        self.assertTrue(surfaces[0]["matches_baseline"])


class Manifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        baseline, _ = cs.summarize_request(request_body())
        (self.base / "baseline.json").write_text(json.dumps(baseline))
        (self.base / "session.jsonl").write_text(json.dumps(session_row()) + "\n")

    def write_raw(self, name, body):
        raw_dir = self.base / name
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / "0.request.json").write_text(json.dumps(body))
        return name

    def spec(self, trials):
        return {"campaign": "clause-bakeoff-9-2026-08-22", "run_id": "demo",
                "environment": {"model": "claude-opus-5"},
                "baselines": {"control": "baseline.json"}, "trials": trials}

    def test_matching_trial_validates_clean(self):
        raw = self.write_raw("raw-ok", request_body(cwd="/private/tmp/fixture-z"))
        manifest = cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "session": "session.jsonl", "raw_dir": raw}]), self.base)
        self.assertEqual(manifest["schema"], cs.MANIFEST_SCHEMA_VERSION)
        self.assertEqual(manifest["trials"][0]["surface_verdict"], "match")
        self.assertEqual(manifest["totals"], {"trials": 1, "turns": 1, "surface_match": 1,
                                              "surface_mismatch": 0, "surface_unrecorded": 0})
        self.assertEqual(cs.validate_manifest(manifest), [])

    def test_trials_at_different_fixture_prompts_all_validate(self):
        """T-016: the case a real campaign is made of, and the one that failed."""
        for name, user in (("raw-f1", "ping"), ("raw-f2", "a much longer fixture prompt")):
            self.write_raw(name, request_body(user=user, cwd=f"/private/tmp/{name}"))
        manifest = cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "session": "session.jsonl", "raw_dir": "raw-f1"},
            {"trial_id": "t2", "arm": "control", "session": "session.jsonl", "raw_dir": "raw-f2"}]), self.base)
        self.assertEqual([t["surface_verdict"] for t in manifest["trials"]], ["match", "match"])
        self.assertEqual(cs.validate_manifest(manifest), [])

    def test_a_baseline_predating_the_stable_digests_is_named_not_graded(self):
        stale, _ = cs.summarize_request(request_body())
        del stale["system_joined_stable_sha256"]
        (self.base / "stale.json").write_text(json.dumps(stale))
        spec = self.spec([])
        spec["baselines"] = {"control": "stale.json"}
        with self.assertRaises(ValueError) as caught:
            cs.load_baselines(spec, self.base)
        self.assertIn("control", str(caught.exception))
        self.assertIn("Re-capture", str(caught.exception))

    def test_wrong_prompt_surface_is_reported_as_a_mismatch(self):
        raw = self.write_raw("raw-bad", request_body(system=("alpha", "ABLATED")))
        manifest = cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "session": "session.jsonl", "raw_dir": raw}]), self.base)
        self.assertEqual(manifest["trials"][0]["surface_verdict"], "mismatch")
        self.assertEqual(manifest["trials"][0]["request_surfaces"][0]["differing_surfaces"], ["system"])
        self.assertTrue(any("does not match its arm baseline" in p for p in cs.validate_manifest(manifest)))

    def test_mid_trial_surface_drift_shows_as_two_groups(self):
        raw_dir = self.base / "raw-drift"
        raw_dir.mkdir()
        (raw_dir / "0.request.json").write_text(json.dumps(request_body()))
        (raw_dir / "1.request.json").write_text(json.dumps(request_body()))
        (raw_dir / "2.request.json").write_text(json.dumps(request_body(tools=("Bash",))))
        manifest = cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "session": "session.jsonl", "raw_dir": "raw-drift"}]), self.base)
        trial = manifest["trials"][0]
        self.assertEqual(trial["distinct_surfaces"], 2)
        self.assertEqual([s["count"] for s in trial["request_surfaces"]], [2, 1])
        self.assertEqual(trial["surface_verdict"], "mismatch")

    def test_trial_without_raw_bodies_is_unrecorded_not_silently_passed(self):
        manifest = cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "session": "session.jsonl"}]), self.base)
        self.assertEqual(manifest["trials"][0]["surface_verdict"], "unrecorded")
        self.assertTrue(any("request surface was not recorded" in problem
                            for problem in cs.validate_manifest(manifest)))

    def test_trial_without_turns_is_not_auditable(self):
        raw = self.write_raw("raw-no-turns", request_body())
        manifest = cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "raw_dir": raw}]), self.base)
        self.assertEqual(manifest["trials"][0]["surface_verdict"], "match")
        self.assertTrue(any("has no turns" in problem
                            for problem in cs.validate_manifest(manifest)))

    def test_manifest_declares_that_raw_bodies_are_not_retained(self):
        manifest = cs.build_manifest(self.spec([]), self.base)
        self.assertIs(manifest["retention"]["raw_bodies_retained"], False)
        self.assertEqual(manifest["retention"]["policy"], cs.RETENTION_POLICY)

    def test_purge_raw_removes_the_transient_directory_after_ingest(self):
        raw = self.write_raw("raw-purge", request_body())
        cs.build_manifest(self.spec([
            {"trial_id": "t1", "arm": "control", "raw_dir": raw}]), self.base, purge=True)
        self.assertFalse((self.base / raw).exists())

    def test_validate_rejects_a_foreign_schema_version(self):
        manifest = cs.build_manifest(self.spec([]), self.base)
        manifest["schema"] = "capture-spine/0"
        self.assertTrue(any("schema is" in p for p in cs.validate_manifest(manifest)))

    def test_validate_rejects_a_manifest_carrying_a_secret(self):
        manifest = cs.build_manifest(self.spec([]), self.base)
        manifest["environment"]["note"] = f"used {SECRET}"
        self.assertTrue(any("credential-shaped" in p for p in cs.validate_manifest(manifest)))


class CommandLine(unittest.TestCase):
    def test_admit_accepts_a_matching_capture_and_refuses_a_changed_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            baseline, _ = cs.summarize_request(request_body())
            (base / "baseline.json").write_text(json.dumps(baseline))
            (base / "ok.json").write_text(json.dumps(request_body(cwd="/private/tmp/other")))
            (base / "bad.json").write_text(json.dumps(request_body(tools=("Bash",))))
            with contextlib.redirect_stdout(io.StringIO()):
                ok = cs.main(["admit", str(base / "ok.json"), "--baseline", str(base / "baseline.json")])
                bad = cs.main(["admit", str(base / "bad.json"), "--baseline", str(base / "baseline.json")])
            self.assertEqual((ok, bad), (0, 1))

    def test_summarize_writes_a_summary_and_a_text_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "raw.json").write_text(json.dumps(request_body()))
            with contextlib.redirect_stdout(io.StringIO()):
                code = cs.main(["summarize", str(base / "raw.json"), "--out", str(base / "s.json"),
                                "--text-out", str(base / "s.text.json"), "--label", "demo"])
            self.assertEqual(code, 0)
            summary = json.loads((base / "s.json").read_text())
            self.assertEqual(summary["label"], "demo")
            self.assertEqual(summary["system_text_ref"], "s.text.json")
            self.assertTrue((base / "s.text.json").is_file())


if __name__ == "__main__":
    unittest.main()


class CliVersionReportTests(unittest.TestCase):
    """Version is a per-run observation; a mid-run change is reported, not rejected."""

    def _trial(self, trial_id, versions):
        return {"trial_id": trial_id, "turns": [{"version": v} for v in versions]}

    def test_single_version_is_not_flagged(self):
        report = cs.cli_version_report(
            [self._trial("t1", ["2.1.239"]), self._trial("t2", ["2.1.239"])]
        )
        self.assertEqual(report["observed"], ["2.1.239"])
        self.assertFalse(report["changed_mid_run"])

    def test_mid_run_change_is_reported_with_the_affected_trials(self):
        report = cs.cli_version_report(
            [self._trial("t1", ["2.1.239"]), self._trial("t2", ["2.1.241"])]
        )
        self.assertEqual(report["observed"], ["2.1.239", "2.1.241"])
        self.assertTrue(report["changed_mid_run"])
        self.assertEqual(report["trials_by_version"]["2.1.241"], ["t2"])
        self.assertIn("Pooling across versions", report["note"])

    def test_a_trial_spanning_two_versions_appears_under_both(self):
        report = cs.cli_version_report([self._trial("t1", ["2.1.239", "2.1.241"])])
        self.assertTrue(report["changed_mid_run"])
        self.assertEqual(report["trials_by_version"]["2.1.239"], ["t1"])
        self.assertEqual(report["trials_by_version"]["2.1.241"], ["t1"])

    def test_turns_without_a_version_are_ignored(self):
        report = cs.cli_version_report(
            [{"trial_id": "t1", "turns": [{"version": None}, {}, {"version": "2.1.239"}]}]
        )
        self.assertEqual(report["observed"], ["2.1.239"])
        self.assertFalse(report["changed_mid_run"])
