"""Unit tests for the interactive-CLI generation arm (T-012).

`campaigns/clause-bakeoff-9-2026-08-22/probes/cli_drive.py`.

Three things are load-bearing and are tested as such: the admission gate,
because `probes/` exists to refuse a malformed prompt *before* a paid request;
the endpoint guard, because this driver is the one component that could spend
money; and the declared configuration, because a CLI arm that drifts from the
SDK arm's configuration turns the transfer test into a two-factor comparison.

No test here starts the CLI. The behaviour that needs a real binary is recorded
in `sources/2026-08-25-t012-cli-arm-instrument.md` with its n; these tests cover
the parts that must hold without one.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22" / "probes"))

import capture_spine as cs  # noqa: E402
import cli_drive as cd  # noqa: E402

SECRET = "sk-ant-api03-NOTAREALKEYbutlooksLikeOne0000"
REMINDER = "<system-reminder>\nToday's date is 2026-08-25.\n</system-reminder>"


def body(*, prompt="ping", cwd="/private/tmp/fixture-a", tools=("Bash", "Read")):
    """A request body shaped like the ones the loopback probe writes."""
    return {
        "path": "/v1/messages",
        "headers": {"user-agent": "claude-cli/2.1.239 (external, cli)",
                    "x-api-key": cd.DUMMY_KEY},
        "body": {
            "model": "claude-opus-5",
            "system": [
                {"type": "text", "text": "x-anthropic-billing-header: cc_entrypoint=cli;"},
                {"type": "text", "text": "You are Claude Code."},
                {"type": "text", "text": f"# Environment\n - Primary working directory: {cwd}\n"},
            ],
            "tools": [{"name": name, "description": name} for name in tools],
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": REMINDER},
                                             {"type": "text", "text": prompt}]},
                {"role": "system", "content": [{"type": "text", "text": "mid"}]},
            ],
            "output_config": {"effort": "high"},
        },
    }


def session_rows():
    """Two assistant turns in the session-JSONL shape the spine ingests."""
    rows = []
    for index in range(2):
        rows.append(json.dumps({
            "type": "assistant", "uuid": f"u{index}", "parentUuid": None,
            "requestId": f"req_{index}", "timestamp": "2026-08-25T12:00:00Z",
            "version": "2.1.239", "entrypoint": "cli", "cwd": "/private/tmp/fixture-a",
            "sessionId": "s-1", "gitBranch": "", "isSidechain": False,
            "message": {"id": f"m{index}", "model": "claude-opus-5",
                        "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": 10, "output_tokens": 3}},
            "effort": "high",
        }))
    return rows


class AdmissionGate(unittest.TestCase):
    def test_ordinary_prompt_is_admitted(self):
        self.assertEqual(cd.prompt_problems("List the files here."), [])
        self.assertEqual(cd.admit_prompt("List the files here."), "List the files here.")

    def test_newline_is_refused_because_the_tui_submits_on_enter(self):
        problems = cd.prompt_problems("first line\nsecond line")
        self.assertTrue(any("newline" in p for p in problems), problems)

    def test_tui_prefixes_are_refused(self):
        for prefix in ("!", "/", "#"):
            with self.subTest(prefix=prefix):
                problems = cd.prompt_problems(prefix + "echo hi")
                self.assertTrue(any("TUI prefix" in p for p in problems), problems)

    def test_a_prefix_character_inside_the_prompt_is_fine(self):
        self.assertEqual(cd.prompt_problems("run the ! command"), [])

    def test_control_characters_are_refused(self):
        problems = cd.prompt_problems("escape\x1b[2Jhere")
        self.assertTrue(any("control characters" in p for p in problems), problems)

    def test_empty_prompt_is_refused(self):
        self.assertTrue(cd.prompt_problems(""))
        self.assertTrue(cd.prompt_problems("   "))

    def test_over_length_prompt_is_refused(self):
        problems = cd.prompt_problems("a" * (cd.MAX_PROMPT_CHARS + 1))
        self.assertTrue(any("over the" in p for p in problems), problems)

    def test_a_prompt_at_the_limit_is_admitted(self):
        self.assertEqual(cd.prompt_problems("a" * cd.MAX_PROMPT_CHARS), [])

    def test_credential_shaped_prompt_is_refused(self):
        problems = cd.prompt_problems(f"use {SECRET} to authenticate")
        self.assertTrue(any("credential" in p for p in problems), problems)

    def test_admit_prompt_raises_with_every_reason(self):
        with self.assertRaises(cd.PromptRefused) as caught:
            cd.admit_prompt("!bad\nprompt")
        self.assertIn("newline", str(caught.exception))
        self.assertIn("TUI prefix", str(caught.exception))

    def test_run_trial_refuses_before_anything_starts(self):
        """The gate fires before a probe is bound or a process is forked."""
        def explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the driver started despite a refused prompt")

        original = cd.drive
        cd.drive = explode
        try:
            with self.assertRaises(cd.PromptRefused):
                cd.run_trial(binary="/bin/false", model="m", cwd="/tmp",
                             config_dir="/tmp/cfg", prompt="/help",
                             raw_dir="/tmp/t012-unit-raw", tty_log="/tmp/t012-unit.log")
        finally:
            cd.drive = original


class EndpointGuard(unittest.TestCase):
    def test_loopback_forms_are_recognised(self):
        for url in ("http://127.0.0.1:8080", "http://127.0.0.1", "http://localhost:1",
                    "http://[::1]:9"):
            with self.subTest(url=url):
                self.assertTrue(cd.is_loopback(url))

    def test_lookalike_hosts_are_not_loopback(self):
        for url in ("https://api.anthropic.com", "http://127.0.0.1.example.com:80",
                    "http://localhost.evil.test", "", "http://127.0.0.2"):
            with self.subTest(url=url):
                self.assertFalse(cd.is_loopback(url))

    def test_loopback_needs_no_authorization(self):
        cd.check_endpoint("http://127.0.0.1:9", authorization=None, receipt=None)

    def test_paid_endpoint_without_authorization_is_refused(self):
        with self.assertRaises(cd.NotAuthorized):
            cd.check_endpoint("https://api.anthropic.com", authorization=None, receipt=None)

    def test_paid_endpoint_without_a_receipt_is_refused(self):
        with self.assertRaises(cd.NotAuthorized):
            cd.check_endpoint("https://api.anthropic.com", authorization="james 2026-08-25",
                              receipt=None)

    def test_paid_endpoint_with_a_failed_receipt_is_refused(self):
        receipt = {"admitted": False, "declared_configuration": cd.declared_configuration()}
        with self.assertRaises(cd.NotAuthorized):
            cd.check_endpoint("https://api.anthropic.com", authorization="james",
                              receipt=receipt)

    def test_paid_endpoint_with_a_receipt_from_another_configuration_is_refused(self):
        other = dict(cd.declared_configuration(), tool_surface=["Bash"])
        with self.assertRaises(cd.NotAuthorized):
            cd.check_endpoint("https://api.anthropic.com", authorization="james",
                              receipt={"admitted": True, "declared_configuration": other})

    def test_paid_endpoint_with_a_matching_receipt_passes(self):
        receipt = {"admitted": True, "declared_configuration": cd.declared_configuration()}
        cd.check_endpoint("https://api.anthropic.com", authorization="james", receipt=receipt)

    def test_run_trial_refuses_a_paid_endpoint_before_starting(self):
        def explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the driver started against a paid endpoint")

        original = cd.drive
        cd.drive = explode
        try:
            with self.assertRaises(cd.NotAuthorized):
                cd.run_trial(binary="/bin/false", model="m", cwd="/tmp",
                             config_dir="/tmp/cfg", prompt="ping",
                             raw_dir="/tmp/t012-unit-raw", tty_log="/tmp/t012-unit.log",
                             base_url="https://api.anthropic.com")
        finally:
            cd.drive = original


class DeclaredConfiguration(unittest.TestCase):
    def test_argv_carries_the_three_declared_options(self):
        argv = cd.declared_argv("/bin/claude", "claude-opus-5")
        self.assertEqual(argv[0], "/bin/claude")
        for flag, value in (("--setting-sources", "project"),
                            ("--settings", '{"autoMemoryEnabled":false}'),
                            ("--tools", "Bash,Read,Edit,Write,Grep,Glob")):
            with self.subTest(flag=flag):
                self.assertIn(flag, argv)
                self.assertEqual(argv[argv.index(flag) + 1], value)

    def test_settings_argument_is_the_exact_json_the_sdk_arm_passes(self):
        self.assertEqual(cd.settings_argument(), '{"autoMemoryEnabled":false}')

    def test_the_tool_surface_option_is_tools_not_allowed_tools(self):
        """`allowedTools` is a permission list, not the tool surface (sdk.d.ts:1397)."""
        argv = cd.declared_argv("/bin/claude", "m")
        self.assertEqual(cd.TOOL_SURFACE_OPTION, "--tools")
        self.assertNotIn("--allowedTools", argv)
        self.assertNotIn("--allowed-tools", argv)

    def test_the_arm_is_interactive_not_print(self):
        """`--print` reports cc_entrypoint=sdk-cli, which is a different host."""
        argv = cd.declared_argv("/bin/claude", "m")
        self.assertNotIn("--print", argv)
        self.assertNotIn("-p", argv)

    def test_extra_arguments_come_after_the_declared_ones(self):
        argv = cd.declared_argv("/bin/claude", "m", ("--permission-mode", "acceptEdits"))
        self.assertEqual(argv[-2:], ["--permission-mode", "acceptEdits"])
        self.assertIn("--tools", argv[:-2])

    def test_declared_configuration_reports_the_six_tool_surface(self):
        declared = cd.declared_configuration()
        self.assertEqual(declared["setting_sources"], ["project"])
        self.assertEqual(declared["declared_settings"], {"autoMemoryEnabled": False})
        self.assertEqual(sorted(declared["tool_surface"]),
                         ["Bash", "Edit", "Glob", "Grep", "Read", "Write"])


class ChildEnvironment(unittest.TestCase):
    parent = {
        "PATH": "/usr/bin", "HOME": "/Users/x", "SHELL": "/bin/zsh",
        "CLAUDE_CODE_OAUTH_TOKEN": SECRET,
        "CLAUDE_CODE_MESSAGING_TOKEN": SECRET,
        "CLAUDE_CODE_CHILD_SESSION": "1",
        "CLAUDE_CODE_SESSION_ID": "abc",
        "CLAUDECODE": "1",
        "ANTHROPIC_MODEL": "claude-something-else",
        "AWS_SECRET_ACCESS_KEY": SECRET,
        "SOME_UNRELATED_VAR": "keep-me-out",
    }

    def env(self, **kwargs):
        return cd.child_env(self.parent, base_url="http://127.0.0.1:9",
                            config_dir="/tmp/cfg", **kwargs)

    def test_only_allowlisted_parent_variables_survive(self):
        env = self.env()
        inherited = set(env) & set(self.parent)
        self.assertEqual(inherited, {"PATH", "HOME", "SHELL"})
        self.assertNotIn("SOME_UNRELATED_VAR", env)

    def test_no_auth_bearing_variable_reaches_the_child(self):
        env = self.env()
        for name in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_MESSAGING_TOKEN",
                     "AWS_SECRET_ACCESS_KEY", "CLAUDE_CODE_SESSION_ID"):
            with self.subTest(name=name):
                self.assertNotIn(name, env)
        self.assertNotIn(SECRET, "\n".join(f"{k}={v}" for k, v in env.items()))

    def test_child_session_marker_is_dropped(self):
        """It makes the child skip its session JSONL, which is half the spine."""
        self.assertNotIn("CLAUDE_CODE_CHILD_SESSION", self.env())

    def test_a_parent_model_pin_cannot_leak_in(self):
        self.assertNotIn("ANTHROPIC_MODEL", self.env())

    def test_telemetry_stays_disabled(self):
        self.assertEqual(self.env()["DISABLE_TELEMETRY"], "1")

    def test_raw_body_capture_is_additive_only(self):
        env = self.env(raw_bodies_dir="/tmp/raw")
        self.assertEqual(env["DISABLE_TELEMETRY"], "1")
        self.assertEqual(env["CLAUDE_CODE_ENABLE_TELEMETRY"], "1")
        self.assertEqual(env["OTEL_LOG_RAW_API_BODIES"], "file:/tmp/raw")

    def test_no_otel_variables_without_raw_body_capture(self):
        env = self.env()
        for name in ("CLAUDE_CODE_ENABLE_TELEMETRY", "OTEL_LOG_RAW_API_BODIES",
                     "OTEL_LOGS_EXPORTER"):
            with self.subTest(name=name):
                self.assertNotIn(name, env)

    def test_the_loopback_key_is_the_dummy(self):
        self.assertEqual(self.env()["ANTHROPIC_API_KEY"], cd.DUMMY_KEY)

    def test_no_api_key_variable_at_all_under_subscription_auth(self):
        self.assertNotIn("ANTHROPIC_API_KEY", self.env(api_key=None))

    def test_a_real_api_key_is_refused(self):
        with self.assertRaises(ValueError):
            self.env(api_key=SECRET)

    def test_geometry_reaches_the_child(self):
        env = self.env(rows=24, cols=80, term="dumb")
        self.assertEqual((env["LINES"], env["COLUMNS"], env["TERM"]), ("24", "80", "dumb"))

    def test_model_roles_must_be_model_role_variables(self):
        env = self.env(model_roles={"ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5"})
        self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "claude-opus-5")
        with self.assertRaises(ValueError):
            self.env(model_roles={"ANTHROPIC_AUTH_TOKEN": SECRET})

    def test_env_problems_names_what_escaped(self):
        self.assertEqual(cd.env_problems({"PATH": "/usr/bin"}), [])
        self.assertTrue(cd.env_problems({"GITHUB_TOKEN": "x"}))
        self.assertTrue(cd.env_problems({"ANTHROPIC_API_KEY": SECRET}))


class RawTier(unittest.TestCase):
    def test_a_path_inside_the_repository_is_refused(self):
        for candidate in (ROOT / "sources" / "raw", ROOT, ROOT / "campaigns" / "x"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    cd.raw_tier_path(candidate)

    def test_a_path_outside_the_repository_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cd.raw_tier_path(tmp), Path(tmp).resolve())

    def test_the_probe_refuses_an_in_repository_raw_directory(self):
        with self.assertRaises(ValueError):
            cd.LoopbackProbe(ROOT / "sources" / "raw-bodies")


class PromptFidelity(unittest.TestCase):
    def test_the_reminder_block_is_stripped_from_the_echo(self):
        self.assertEqual(cd.prompt_echo(body(prompt="list the files")), "list the files")

    def test_a_string_content_message_is_handled(self):
        raw = body()
        raw["body"]["messages"][0]["content"] = REMINDER + "\nping"
        self.assertEqual(cd.prompt_echo(raw), "ping")

    def test_a_bare_body_without_the_probe_wrapper_is_handled(self):
        self.assertEqual(cd.prompt_echo(body(prompt="hi")["body"]), "hi")

    def test_exact_when_the_typed_prompt_arrived_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "req-001.json").write_text(json.dumps(body(prompt="ping")))
            result = cd.prompt_fidelity(tmp, "ping")
        self.assertEqual(result["verdict"], "exact")
        self.assertEqual(result["expected_sha256"], result["observed_sha256"])

    def test_mismatch_when_a_character_was_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "req-001.json").write_text(json.dumps(body(prompt="pin")))
            result = cd.prompt_fidelity(tmp, "ping")
        self.assertEqual(result["verdict"], "mismatch")
        self.assertEqual((result["expected_chars"], result["observed_chars"]), (4, 3))

    def test_unrecorded_when_no_body_was_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cd.prompt_fidelity(tmp, "ping")["verdict"], "unrecorded")

    def test_the_prompt_text_is_never_in_the_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "req-001.json").write_text(json.dumps(body(prompt="a secret plan")))
            result = cd.prompt_fidelity(tmp, "a secret plan")
        self.assertNotIn("secret", json.dumps(result))


def title_body():
    """The session-title request the CLI issues beside a long-prompt turn."""
    raw = body()
    raw["body"]["tools"] = []
    raw["body"]["messages"] = [{"role": "user", "content": [
        {"type": "text", "text": "<session>\nsome prompt\n</session>\n\nWrite the title."}]}]
    raw["body"]["thinking"] = {"type": "disabled"}
    raw["body"]["output_config"] = {"effort": "high", "format": {"type": "json_schema"}}
    return raw


class AuxiliaryRequests(unittest.TestCase):
    def test_a_declared_turn_is_not_auxiliary(self):
        self.assertFalse(cd.is_auxiliary(body()))

    def test_the_session_title_request_is_auxiliary(self):
        self.assertTrue(cd.is_auxiliary(title_body()))

    def test_a_toolless_request_carrying_the_reminder_is_still_a_turn(self):
        raw = body()
        raw["body"]["tools"] = []
        self.assertFalse(cd.is_auxiliary(raw))

    def test_partitioning_leaves_the_spine_seeing_only_the_trials_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(title_body()))
            (raw / "req-002.json").write_text(json.dumps(body()))
            (raw / "req-003.json").write_text(json.dumps(title_body()))
            moved = cd.partition_auxiliary(raw)
            remaining = [p.name for p in cs.raw_body_paths(raw)]
            kept = sorted(p.name for p in (raw / cd.AUXILIARY_DIR).iterdir())
        self.assertEqual(moved, 2)
        self.assertEqual(remaining, ["req-002.json"])
        self.assertEqual(kept, ["req-001.json", "req-003.json"])

    def test_nothing_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(title_body()))
            cd.partition_auxiliary(raw)
            total = len(list((raw / cd.AUXILIARY_DIR).iterdir())) + len(cs.raw_body_paths(raw))
        self.assertEqual(total, 1)

    def test_an_auxiliary_request_would_otherwise_fail_the_trial(self):
        """Why the partition exists: two surface groups grade the trial mismatch."""
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(title_body()))
            (raw / "req-002.json").write_text(json.dumps(body()))
            baseline, _ = cs.summarize_request(body())
            before = cd.grade_preflight({"trial_id": "t", "raw_dir": str(raw)}, baseline)
            cd.partition_auxiliary(raw)
            after = cd.grade_preflight({"trial_id": "t", "raw_dir": str(raw)}, baseline)
        self.assertEqual((before["surface_verdict"], before["distinct_surfaces"]),
                         ("mismatch", 2))
        self.assertEqual((after["surface_verdict"], after["distinct_surfaces"]),
                         ("match", 1))

    def test_a_missing_raw_directory_is_zero_not_an_error(self):
        self.assertEqual(cd.partition_auxiliary("/private/tmp/t012-does-not-exist"), 0)


class Probe(unittest.TestCase):
    def post(self, probe, payload):
        request = urllib.request.Request(
            probe.base_url + "/v1/messages", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "x-api-key": cd.DUMMY_KEY})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.addCleanup(caught.exception.close)
        return caught.exception

    def test_it_answers_a_synthetic_401_and_records_the_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            with cd.LoopbackProbe(Path(tmp) / "raw") as probe:
                error = self.post(probe, {"model": "claude-opus-5", "messages": []})
                self.assertEqual(error.code, 401)
                self.assertEqual(json.loads(error.read())["error"]["type"],
                                 "authentication_error")
                self.assertEqual(probe.count, 1)
                written = json.loads((probe.raw_dir / "req-001.json").read_text())
        self.assertEqual(written["path"], "/v1/messages")
        self.assertEqual(written["body"]["model"], "claude-opus-5")
        self.assertIn("x-api-key", {k.lower() for k in written["headers"]})

    def test_every_turn_is_recorded_not_only_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            with cd.LoopbackProbe(Path(tmp) / "raw") as probe:
                for _ in range(3):
                    self.post(probe, {"model": "m", "messages": []})
                self.assertEqual(probe.count, 3)
                names = sorted(p.name for p in probe.raw_dir.iterdir())
        self.assertEqual(names, ["req-001.json", "req-002.json", "req-003.json"])

    def test_capture_spine_can_read_what_the_probe_wrote(self):
        with tempfile.TemporaryDirectory() as tmp:
            with cd.LoopbackProbe(Path(tmp) / "raw") as probe:
                self.post(probe, body()["body"])
            paths = cs.raw_body_paths(probe.raw_dir)
            summary, _ = cs.summarize_request(json.loads(paths[0].read_text()))
        self.assertEqual(summary["entrypoint"], "cli")
        self.assertEqual(summary["tools"], ["Bash", "Read"])


class Grading(unittest.TestCase):
    def entry(self, tmp, raw):
        return {"trial_id": "t1", "raw_dir": str(raw),
                "driver": {"pty": {"rows": 40, "cols": 120}},
                "prompt_fidelity": {"verdict": "exact"}}

    def baseline(self, **kwargs):
        summary, _ = cs.summarize_request(body(**kwargs))
        return summary

    def test_match_when_the_surfaces_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(body()))
            receipt = cd.grade_preflight(self.entry(tmp, raw), self.baseline())
        self.assertEqual(receipt["surface_verdict"], "match")
        self.assertTrue(receipt["admitted"])
        self.assertEqual(receipt["differing_surfaces"], [])

    def test_mismatch_names_the_surface_that_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(body(tools=("Bash",))))
            receipt = cd.grade_preflight(self.entry(tmp, raw), self.baseline())
        self.assertEqual(receipt["surface_verdict"], "mismatch")
        self.assertEqual(receipt["differing_surfaces"], ["tools"])
        self.assertFalse(receipt["admitted"])

    def test_a_working_directory_change_alone_does_not_move_the_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(body(cwd="/private/tmp/fixture-b")))
            receipt = cd.grade_preflight(self.entry(tmp, raw), self.baseline())
        self.assertEqual(receipt["surface_verdict"], "match")

    def test_no_bodies_is_unrecorded_never_a_silent_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            receipt = cd.grade_preflight(self.entry(tmp, raw), self.baseline())
        self.assertEqual(receipt["surface_verdict"], "unrecorded")
        self.assertFalse(receipt["admitted"])

    def test_two_prompts_share_an_arm_baseline(self):
        """T-012 recorded this failing; T-016 fixed it, so it is now asserted.

        `capture_spine.summarize_request` used to digest `messages[0]` over the
        message's whole joined text, so the reminder digest carried the user
        prompt with it -- the campaign's "310 characters" is a 306-character
        reminder plus a four-character `ping`. Every T-001 and T-002 capture used
        the same prompt, so it never showed, and one arm baseline could not grade
        trials at different fixtures. See
        `sources/2026-08-25-t012-cli-arm-instrument.md` for the finding and
        `sources/2026-08-26-t016-prompt-stable-surfaces.md` for the fix.
        """
        one, _ = cs.summarize_request(body(prompt="ping"))
        two, _ = cs.summarize_request(body(prompt="a different fixture prompt"))
        self.assertNotEqual(one["system_reminder"]["date_normalized_sha256"],
                            two["system_reminder"]["date_normalized_sha256"])
        self.assertEqual(one["system_reminder"]["payload_sha256"],
                         two["system_reminder"]["payload_sha256"])
        self.assertEqual(one["tools_sha256"], two["tools_sha256"])
        self.assertEqual(cs.surface_diff(two, one), [])

    def test_the_receipt_carries_the_configuration_it_was_taken_under(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.mkdir()
            (raw / "req-001.json").write_text(json.dumps(body()))
            receipt = cd.grade_preflight(self.entry(tmp, raw), self.baseline())
        self.assertEqual(receipt["declared_configuration"], cd.declared_configuration())
        cd.check_endpoint("https://api.anthropic.com", authorization="james", receipt=receipt)


class Spine(unittest.TestCase):
    """The arm feeds `capture-spine/1`; it does not define a schema of its own."""

    def test_the_module_declares_no_manifest_schema(self):
        source = (ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22" / "probes"
                  / "cli_drive.py").read_text()
        self.assertNotIn("MANIFEST_SCHEMA_VERSION =", source)
        self.assertNotIn("capture-spine/2", source)

    def test_environment_block_extends_the_free_form_pins_additively(self):
        block = cd.environment_block(binary="/bin/claude", binary_version="2.1.239",
                                     binary_sha256="ab" * 32, model="claude-opus-5",
                                     pty_factors={"rows": 40, "cols": 120},
                                     inference_purchased=False)
        self.assertNotIn("schema", block)
        self.assertEqual(block["generator"], cd.GENERATOR)
        self.assertEqual(block["tool_surface_option"], "--tools")
        self.assertEqual(block["pty"], {"rows": 40, "cols": 120})
        self.assertIs(block["inference_purchased"], False)

    def test_a_trial_entry_carries_the_keys_build_manifest_reads(self):
        entry = cd.trial_entry(trial_id="t1", arm="cli", fixture_id="b1e-x",
                               stratum="b1-easy", cwd="/private/tmp/fixture-a",
                               raw_dir="/private/tmp/raw", session="/private/tmp/s.jsonl")
        for key in ("trial_id", "arm", "fixture_id", "stratum", "cwd", "raw_dir", "session"):
            with self.subTest(key=key):
                self.assertIn(key, entry)

    def test_the_emitted_spec_builds_a_clean_capture_spine_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw = base / "raw" / "t1"
            raw.mkdir(parents=True)
            (raw / "req-001.json").write_text(json.dumps(body()))
            (base / "session.jsonl").write_text("\n".join(session_rows()))
            summary, _ = cs.summarize_request(body())
            (base / "baseline.json").write_text(json.dumps(summary))

            entry = cd.trial_entry(trial_id="t1", arm="cli", fixture_id="b1e-x",
                                   stratum="b1-easy", cwd="/private/tmp/fixture-a",
                                   raw_dir=raw, session=base / "session.jsonl",
                                   driver={"status": "complete", "inference_purchased": False},
                                   fidelity={"verdict": "exact"})
            spec = cd.build_spec(
                [entry], campaign="clause-bakeoff-9-2026-08-22", run_id="t012-unit",
                baselines={"cli": "baseline.json"},
                environment=cd.environment_block(
                    binary="/bin/claude", model="claude-opus-5",
                    pty_factors={"rows": 40, "cols": 120, "term": "xterm-256color"},
                    inference_purchased=False))
            manifest = cs.build_manifest(spec, base)

        self.assertEqual(manifest["schema"], cs.MANIFEST_SCHEMA_VERSION)
        self.assertEqual(cs.validate_manifest(manifest), [])
        trial = manifest["trials"][0]
        self.assertEqual(trial["surface_verdict"], "match")
        self.assertEqual(len(trial["turns"]), 2)
        self.assertEqual(trial["usage_totals"]["input_tokens"], 20)
        self.assertEqual(manifest["environment"]["generator"], cd.GENERATOR)
        self.assertEqual(manifest["environment"]["pty"]["cols"], 120)

    def test_a_trial_entry_passes_the_retention_scan(self):
        entry = cd.trial_entry(trial_id="t1", arm="cli", fixture_id="b1e-x",
                               stratum="b1-easy", cwd="/private/tmp/fixture-a",
                               raw_dir="/private/tmp/raw",
                               driver={"status": "complete"},
                               fidelity={"verdict": "exact"})
        self.assertEqual(cs.retention_problems(entry), [])
        with tempfile.TemporaryDirectory() as tmp:
            cs.write_record(Path(tmp) / "trial.json", entry)


class SessionDiscovery(unittest.TestCase):
    def test_the_project_slug_matches_claude_codes_own(self):
        self.assertEqual(cd.session_slug("/private/tmp/ccap9/emptyproj"),
                         "-private-tmp-ccap9-emptyproj")

    def test_no_session_directory_is_an_empty_list_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cd.session_files(tmp, "/private/tmp/nowhere"), [])

    def test_sessions_come_back_newest_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / cd.session_slug("/private/tmp/x")
            project.mkdir(parents=True)
            for index, name in enumerate(("a.jsonl", "b.jsonl")):
                path = project / name
                path.write_text("{}")
                os.utime(path, (1000 + index, 1000 + index))
            found = cd.session_files(tmp, "/private/tmp/x")
        self.assertEqual([p.name for p in found], ["a.jsonl", "b.jsonl"])


class ConfigStub(unittest.TestCase):
    def test_the_trial_directory_is_pre_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            cd.ensure_config(Path(tmp) / "cfg", "/private/tmp/fixture-a")
            config = json.loads((Path(tmp) / "cfg" / ".claude.json").read_text())
        self.assertTrue(config["hasCompletedOnboarding"])
        self.assertTrue(config["projects"]["/private/tmp/fixture-a"]["hasTrustDialogAccepted"])

    def test_no_api_key_response_unless_the_loopback_dummy_is_in_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            cd.ensure_config(Path(tmp) / "cfg", "/private/tmp/fixture-a")
            config = json.loads((Path(tmp) / "cfg" / ".claude.json").read_text())
        self.assertNotIn("customApiKeyResponses", config)

    def test_the_only_key_it_can_approve_is_the_dummy(self):
        with tempfile.TemporaryDirectory() as tmp:
            cd.ensure_config(Path(tmp) / "cfg", "/private/tmp/fixture-a",
                             approve_dummy_key=True)
            config = json.loads((Path(tmp) / "cfg" / ".claude.json").read_text())
        self.assertEqual(config["customApiKeyResponses"]["approved"], [cd.DUMMY_KEY[-20:]])

    def test_a_second_trial_directory_is_added_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            cd.ensure_config(Path(tmp) / "cfg", "/private/tmp/fixture-a")
            cd.ensure_config(Path(tmp) / "cfg", "/private/tmp/fixture-b")
            config = json.loads((Path(tmp) / "cfg" / ".claude.json").read_text())
        self.assertEqual(sorted(config["projects"]),
                         ["/private/tmp/fixture-a", "/private/tmp/fixture-b"])


class CommandLine(unittest.TestCase):
    def test_spec_assembles_trial_entries_into_an_ingest_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entry = cd.trial_entry(trial_id="t1", arm="cli", fixture_id="b1e-x",
                                   stratum="b1-easy", cwd="/private/tmp/fixture-a",
                                   raw_dir="/private/tmp/raw",
                                   driver={"inference_purchased": False})
            (base / "trial-1.json").write_text(json.dumps(entry))
            with contextlib.redirect_stdout(io.StringIO()):
                code = cd.main(["spec", str(base / "trial-1.json"),
                                "--out", str(base / "spec.json"),
                                "--run-id", "t012-unit", "--binary", "/bin/claude",
                                "--baseline", "cli=baseline.json"])
            spec = json.loads((base / "spec.json").read_text())
        self.assertEqual(code, 0)
        self.assertEqual(spec["baselines"], {"cli": "baseline.json"})
        self.assertEqual(spec["campaign"], "clause-bakeoff-9-2026-08-22")
        self.assertEqual(len(spec["trials"]), 1)
        self.assertIs(spec["environment"]["inference_purchased"], False)


if __name__ == "__main__":
    unittest.main()
