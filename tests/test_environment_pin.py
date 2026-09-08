"""Unit tests for scripts/environment_pin.py.

Two things are load-bearing and are tested as such: the checksum gate, because
an unverified binary silently invalidates every hash the campaign records; and
the additive-extension boundary, because T-005 must not fork `capture-spine/1`.

No test touches the network. Direct `acquire()` tests supply its injectable
fetcher. CLI tests without one use manifests that validation rejects before a
network request.
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
import environment_pin as ep  # noqa: E402

# The real 2.1.239 darwin-arm64 values, cross-checked 2026-08-25 against
# Anthropic's release manifest and against the local pin. Used as realistic
# shapes; no test downloads anything.
VERSION = "2.1.239"
PLATFORM = "darwin-arm64"
PINNED_SHA = "2b4f7aafdaa65bcc2335f56a4b276317837203f2c5587b1f2a17ca78ad14e36f"
BASE = "https://downloads.claude.ai/claude-code-releases"

INSTALL_SCRIPT = """#!/bin/sh
set -e
DOWNLOAD_BASE_URL="https://downloads.claude.ai/claude-code-releases"
DOWNLOAD_DIR="$HOME/.claude/downloads"
"""

PAYLOAD = b"#!/usr/bin/env pretend-binary\n"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


def release_manifest(checksum=PAYLOAD_SHA, platform=PLATFORM):
    return json.dumps({
        "version": VERSION,
        "commit": "deadbeef",
        "platforms": {platform: {"checksum": checksum, "size": len(PAYLOAD)}},
    }).encode()


def fetcher(*, script=INSTALL_SCRIPT, manifest=None, payload=PAYLOAD, calls=None):
    """A fetch stub. `calls` collects the URLs asked for, in order."""
    manifest = release_manifest() if manifest is None else manifest

    def fetch(url, timeout=60.0):
        if calls is not None:
            calls.append(url)
        if url == ep.INSTALL_SCRIPT_URL:
            return script.encode()
        if url.endswith("/manifest.json"):
            if manifest is FileNotFoundError:
                raise FileNotFoundError(url)
            return manifest
        if url.endswith("/claude"):
            return payload
        raise AssertionError(f"unexpected fetch: {url}")

    return fetch


class ChunkedResponse:
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def pin_block(**overrides):
    block = ep.build_environment_pin(
        version=VERSION,
        platform_key=PLATFORM,
        binary_sha256=PINNED_SHA,
        base_url=BASE,
        model_roles={"ANTHROPIC_MODEL": "claude-opus-5"},
    )
    env = {"binary_version": VERSION, "binary_sha256": PINNED_SHA, **block}
    env.update(overrides)
    return env


class TestDownloadBaseResolution(unittest.TestCase):
    def test_reads_the_base_url_out_of_the_install_script(self):
        self.assertEqual(ep.resolve_download_base(INSTALL_SCRIPT), BASE)

    def test_trailing_slash_is_normalized(self):
        script = INSTALL_SCRIPT.replace(BASE, BASE + "/")
        self.assertEqual(ep.resolve_download_base(script), BASE)

    def test_refuses_to_guess_when_the_script_defines_none(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.resolve_download_base("#!/bin/sh\necho hello\n")

    def test_a_commented_assignment_is_not_taken(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.resolve_download_base('# DOWNLOAD_BASE_URL="https://evil.example"\n')


class TestPlatformDetection(unittest.TestCase):
    def test_known_platforms(self):
        self.assertEqual(ep.detect_platform("Darwin", "arm64"), "darwin-arm64")
        self.assertEqual(ep.detect_platform("Darwin", "x86_64"), "darwin-x64")
        self.assertEqual(ep.detect_platform("Linux", "aarch64").split("-")[:2], ["linux", "arm64"])

    def test_every_detectable_key_is_a_known_platform(self):
        for system, machine in (("Darwin", "arm64"), ("Darwin", "x86_64"),
                                ("Linux", "x86_64"), ("Linux", "aarch64")):
            self.assertIn(ep.detect_platform(system, machine), ep.PLATFORMS)

    def test_unsupported_inputs_are_refused(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.detect_platform("Darwin", "mips")
        with self.assertRaises(ep.AcquisitionError):
            ep.detect_platform("Plan9", "arm64")


class TestUrlsAndReleaseManifest(unittest.TestCase):
    def test_urls_follow_the_install_script_layout(self):
        self.assertEqual(ep.binary_url(BASE, VERSION, PLATFORM),
                         f"{BASE}/{VERSION}/{PLATFORM}/claude")
        self.assertEqual(ep.release_manifest_url(BASE, VERSION),
                         f"{BASE}/{VERSION}/manifest.json")

    def test_platform_entry_extracts_the_checksum(self):
        entry = ep.platform_entry(json.loads(release_manifest()), PLATFORM)
        self.assertEqual(entry["checksum"], PAYLOAD_SHA)
        self.assertEqual(entry["size"], len(PAYLOAD))

    def test_absent_platform_is_refused(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.platform_entry(json.loads(release_manifest()), "linux-x64")

    def test_a_non_sha256_checksum_is_refused(self):
        bad = json.loads(release_manifest(checksum="not-a-digest"))
        with self.assertRaises(ep.AcquisitionError):
            ep.platform_entry(bad, PLATFORM)


class TestVerifyFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "claude"
        self.path.write_bytes(PAYLOAD)

    def tearDown(self):
        self.tmp.cleanup()

    def test_matching_digest_passes(self):
        self.assertEqual(ep.verify_file(self.path, PAYLOAD_SHA), PAYLOAD_SHA)

    def test_uppercase_expectation_is_accepted(self):
        self.assertEqual(ep.verify_file(self.path, PAYLOAD_SHA.upper()), PAYLOAD_SHA)

    def test_one_flipped_byte_fails(self):
        self.path.write_bytes(PAYLOAD + b"x")
        with self.assertRaises(ep.AcquisitionError) as ctx:
            ep.verify_file(self.path, PAYLOAD_SHA)
        self.assertIn("checksum verification failed", str(ctx.exception))

    def test_a_malformed_expectation_is_refused_before_hashing(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.verify_file(self.path, "")

    def test_streaming_hash_matches_hashlib_over_a_multi_chunk_file(self):
        blob = b"\x00\xff" * (ep.CHUNK)  # two chunks
        self.path.write_bytes(blob)
        self.assertEqual(ep.sha256_file(self.path), hashlib.sha256(blob).hexdigest())


class TestAcquire(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "pins" / "claude"

    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_download_is_installed_and_executable(self):
        calls = []
        result = ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA,
                            platform_key=PLATFORM, fetch=fetcher(calls=calls))
        self.assertTrue(self.dest.is_file())
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertTrue(self.dest.stat().st_mode & 0o111)
        self.assertEqual(result["checksum"], PAYLOAD_SHA)
        self.assertTrue(result["checksum_confirmed_by_release_manifest"])
        self.assertEqual(calls[0], ep.INSTALL_SCRIPT_URL)
        self.assertEqual(calls[-1], f"{BASE}/{VERSION}/{PLATFORM}/claude")

    def test_download_is_written_from_multiple_chunks(self):
        payload = b"x" * (ep.CHUNK + 17)
        checksum = hashlib.sha256(payload).hexdigest()
        response = ChunkedResponse(payload)

        def fetch(url, timeout=60.0):
            if url == ep.INSTALL_SCRIPT_URL:
                return INSTALL_SCRIPT.encode()
            if url.endswith("/manifest.json"):
                return release_manifest(checksum=checksum)
            if url.endswith("/claude"):
                return response
            raise AssertionError(f"unexpected fetch: {url}")

        ep.acquire(VERSION, self.dest, expected_sha256=checksum,
                   platform_key=PLATFORM, fetch=fetch)

        self.assertEqual(self.dest.read_bytes(), payload)
        self.assertEqual(response.read_sizes, [ep.CHUNK, ep.CHUNK, ep.CHUNK])

    def test_base_url_override_skips_install_script_resolution(self):
        calls = []
        ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA, platform_key=PLATFORM,
                   base_url=BASE, fetch=fetcher(calls=calls))
        self.assertNotIn(ep.INSTALL_SCRIPT_URL, calls)

    def test_a_corrupted_download_is_refused_and_leaves_nothing_behind(self):
        with self.assertRaises(ep.AcquisitionError) as ctx:
            ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA, platform_key=PLATFORM,
                       fetch=fetcher(payload=PAYLOAD + b"tampered"))
        self.assertIn("checksum verification failed", str(ctx.exception))
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.dest.with_name(self.dest.name + ".partial").exists())

    def test_a_refused_download_does_not_overwrite_an_existing_binary(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.write_bytes(b"the binary already here")
        with self.assertRaises(ep.AcquisitionError):
            ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA, platform_key=PLATFORM,
                       fetch=fetcher(payload=b"something else"))
        self.assertEqual(self.dest.read_bytes(), b"the binary already here")

    def test_release_manifest_disagreeing_with_the_pin_refuses_both(self):
        """Served checksum wins nothing: the campaign manifest is the authority."""
        other = hashlib.sha256(b"a different build").hexdigest()
        with self.assertRaises(ep.AcquisitionError) as ctx:
            ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA, platform_key=PLATFORM,
                       fetch=fetcher(manifest=release_manifest(checksum=other)))
        self.assertIn("refusing to install either", str(ctx.exception))
        self.assertFalse(self.dest.exists())

    def test_a_withdrawn_release_manifest_still_allows_the_pin_to_govern(self):
        result = ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA, platform_key=PLATFORM,
                            fetch=fetcher(manifest=FileNotFoundError))
        self.assertFalse(result["checksum_confirmed_by_release_manifest"])
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_a_missing_platform_is_refused_even_when_the_manifest_loads(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA, platform_key=PLATFORM,
                       fetch=fetcher(manifest=release_manifest(platform="linux-x64")))
        self.assertFalse(self.dest.exists())

    def test_a_pin_without_a_checksum_is_refused_before_any_fetch(self):
        calls = []
        with self.assertRaises(ep.AcquisitionError):
            ep.acquire(VERSION, self.dest, expected_sha256="", platform_key=PLATFORM,
                       fetch=fetcher(calls=calls))
        self.assertEqual(calls, [])

    def test_an_unknown_platform_key_is_refused(self):
        with self.assertRaises(ep.AcquisitionError):
            ep.acquire(VERSION, self.dest, expected_sha256=PAYLOAD_SHA,
                       platform_key="sunos-sparc", fetch=fetcher())


class TestEnvironmentBlock(unittest.TestCase):
    def test_a_built_block_validates(self):
        self.assertEqual(ep.environment_problems(pin_block()), [])

    def test_it_carries_both_ablation_flags(self):
        flags = pin_block()["system_prompt_flags"]
        self.assertEqual(flags["replace"], "--system-prompt")
        self.assertEqual(flags["append"], "--append-system-prompt")

    def test_the_urls_address_the_pinned_version_and_platform(self):
        acq = pin_block()["acquisition"]
        self.assertEqual(acq["binary_url"], f"{BASE}/{VERSION}/{PLATFORM}/claude")
        self.assertEqual(acq["checksum"], PINNED_SHA)
        self.assertEqual(acq["checksum_algorithm"], "sha256")

    def test_a_manifest_without_the_extension_is_left_alone(self):
        self.assertEqual(ep.environment_problems({"binary_version": VERSION}), [])
        self.assertEqual(ep.environment_problems(None), [])

    def test_an_extension_without_binary_version_is_a_problem(self):
        env = pin_block()
        del env["binary_version"]
        self.assertIn("environment: missing binary_version", ep.environment_problems(env))

    def test_an_extension_without_binary_sha256_is_a_problem(self):
        env = pin_block()
        del env["binary_sha256"]
        self.assertIn("environment: missing binary_sha256", ep.environment_problems(env))

    def test_checksum_disagreeing_with_binary_sha256_is_a_problem(self):
        env = pin_block(binary_sha256=hashlib.sha256(b"other").hexdigest())
        self.assertIn("checksum disagrees with environment.binary_sha256",
                      " ".join(ep.environment_problems(env)))

    def test_a_url_pointing_at_another_version_is_a_problem(self):
        env = pin_block()
        env["acquisition"]["binary_url"] = f"{BASE}/2.1.170/{PLATFORM}/claude"
        self.assertIn("binary_url does not address", " ".join(ep.environment_problems(env)))

    def test_a_release_manifest_url_pointing_elsewhere_is_a_problem(self):
        env = pin_block()
        env["acquisition"]["release_manifest_url"] = f"{BASE}/latest/manifest.json"
        self.assertIn("release_manifest_url does not address", " ".join(ep.environment_problems(env)))

    def test_a_malformed_checksum_is_a_problem(self):
        env = pin_block()
        env["acquisition"]["checksum"] = "2B4F7AAF"
        self.assertIn("not a lowercase sha256 hex digest", " ".join(ep.environment_problems(env)))

    def test_an_unknown_platform_is_a_problem(self):
        env = pin_block()
        env["acquisition"]["platform"] = "sunos-sparc"
        self.assertIn("unknown platform", " ".join(ep.environment_problems(env)))

    def test_a_missing_acquisition_block_is_a_problem(self):
        env = pin_block()
        del env["acquisition"]
        self.assertIn("environment.acquisition is missing", ep.environment_problems(env))

    def test_a_variable_that_is_not_a_model_role_is_a_problem(self):
        env = pin_block()
        env["model_roles"]["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:1"
        self.assertIn("is not a model-role variable", " ".join(ep.environment_problems(env)))

    def test_an_empty_model_role_is_a_problem(self):
        env = pin_block()
        env["model_roles"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] = "  "
        self.assertIn("has no value", " ".join(ep.environment_problems(env)))

    def test_all_five_named_role_variables_are_accepted(self):
        env = pin_block()
        env["model_roles"] = {name: "claude-opus-5" for name in (
            "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")}
        self.assertEqual(ep.environment_problems(env), [])

    def test_swapping_an_ablation_flag_is_a_problem(self):
        env = pin_block()
        env["system_prompt_flags"] = {"replace": "--append-system-prompt",
                                      "append": "--append-system-prompt"}
        self.assertIn("system_prompt_flags must be", " ".join(ep.environment_problems(env)))

    def test_a_wrong_extension_marker_is_a_problem(self):
        env = pin_block(pin_extension="environment-pin/2")
        self.assertIn("pin_extension is", " ".join(ep.environment_problems(env)))


class TestAdditiveToCaptureSpine(unittest.TestCase):
    """The extension must not fork `capture-spine/1`."""

    def setUp(self):
        base = Path(__file__).resolve().parents[1]
        self.manifest = json.loads((base / "sources" / "2026-08-24-t002-example-manifest.json").read_text())

    def test_the_module_declares_no_manifest_schema_of_its_own(self):
        self.assertFalse(hasattr(ep, "MANIFEST_SCHEMA_VERSION"))
        self.assertEqual(cs.MANIFEST_SCHEMA_VERSION, "capture-spine/1")

    def test_merging_the_block_leaves_the_schema_and_existing_pins_intact(self):
        env = dict(self.manifest["environment"])
        before = dict(env)
        env.update(ep.build_environment_pin(
            version=env["binary_version"], platform_key=PLATFORM,
            binary_sha256=env["binary_sha256"], base_url=BASE,
            model_roles={"ANTHROPIC_MODEL": env["model"]}))
        for key, value in before.items():
            self.assertEqual(env[key], value, f"{key} was overwritten")
        merged = {**self.manifest, "environment": env}
        self.assertEqual(merged["schema"], cs.MANIFEST_SCHEMA_VERSION)
        self.assertEqual(ep.environment_problems(env), [])

    def test_the_merged_manifest_still_passes_the_capture_spine_retention_scan(self):
        env = dict(self.manifest["environment"])
        env.update(ep.build_environment_pin(
            version=env["binary_version"], platform_key=PLATFORM,
            binary_sha256=env["binary_sha256"], base_url=BASE,
            model_roles={"ANTHROPIC_MODEL": env["model"]}))
        self.assertEqual(cs.retention_problems({"environment": env}), [])

    def test_capture_spine_validation_of_the_merged_manifest_is_unchanged(self):
        env = dict(self.manifest["environment"])
        env.update(ep.build_environment_pin(
            version=env["binary_version"], platform_key=PLATFORM,
            binary_sha256=env["binary_sha256"], base_url=BASE,
            model_roles={"ANTHROPIC_MODEL": env["model"]}))
        merged = {**self.manifest, "environment": env}
        self.assertEqual(cs.validate_manifest(merged), cs.validate_manifest(self.manifest))


class TestWorkedInstance(unittest.TestCase):
    """`sources/2026-08-25-t005-environment-pin.json` is the shipped example."""

    def setUp(self):
        base = Path(__file__).resolve().parents[1]
        self.path = base / "sources" / "2026-08-25-t005-environment-pin.json"

    def test_it_exists_and_validates(self):
        env = json.loads(self.path.read_text())["environment"]
        self.assertEqual(ep.environment_problems(env), [])

    def test_it_pins_the_campaign_binary(self):
        env = json.loads(self.path.read_text())["environment"]
        self.assertEqual(env["binary_version"], VERSION)
        self.assertEqual(env["binary_sha256"], PINNED_SHA)
        self.assertEqual(env["acquisition"]["checksum"], PINNED_SHA)

    def test_it_names_the_capture_spine_schema_and_not_a_new_one(self):
        doc = json.loads(self.path.read_text())
        self.assertEqual(doc["schema"], cs.MANIFEST_SCHEMA_VERSION)

    def test_it_carries_no_credential_shaped_material(self):
        doc = json.loads(self.path.read_text())
        self.assertEqual(cs.retention_problems(doc), [])


class TestCli(unittest.TestCase):
    """The CLI is the reader-facing surface, so its exit codes are the contract."""

    @staticmethod
    @contextlib.contextmanager
    def quiet():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            yield buf

    def test_verify_accepts_a_matching_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude"
            path.write_bytes(PAYLOAD)
            with self.quiet():
                self.assertEqual(ep.main(["verify", str(path), "--checksum", PAYLOAD_SHA]), 0)

    def test_verify_rejects_a_mismatched_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude"
            path.write_bytes(PAYLOAD + b"!")
            with self.quiet() as out:
                self.assertEqual(ep.main(["verify", str(path), "--checksum", PAYLOAD_SHA]), 1)
            self.assertIn("checksum verification failed", out.getvalue())

    def test_check_passes_the_worked_instance(self):
        base = Path(__file__).resolve().parents[1]
        path = base / "sources" / "2026-08-25-t005-environment-pin.json"
        with self.quiet():
            self.assertEqual(ep.main(["check", str(path)]), 0)

    def test_check_rejects_a_manifest_whose_checksum_was_edited(self):
        base = Path(__file__).resolve().parents[1]
        doc = json.loads((base / "sources" / "2026-08-25-t005-environment-pin.json").read_text())
        doc["environment"]["acquisition"]["checksum"] = hashlib.sha256(b"nope").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps(doc))
            with self.quiet() as out:
                self.assertEqual(ep.main(["check", str(path)]), 1)
            self.assertIn("checksum disagrees", out.getvalue())

    def test_check_reports_an_extensionless_manifest_without_claiming_the_extension(self):
        manifest = {"environment": {"binary_version": VERSION}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps(manifest))
            with self.quiet() as out:
                self.assertEqual(ep.main(["check", str(path)]), 0)
            self.assertIn("environment ok", out.getvalue())
            self.assertNotIn(f"{ep.PIN_EXTENSION} ok", out.getvalue())

    def test_acquire_rejects_a_manifest_missing_binary_version_before_indexing_it(self):
        base = Path(__file__).resolve().parents[1]
        doc = json.loads((base / "sources" / "2026-08-25-t005-environment-pin.json").read_text())
        del doc["environment"]["binary_version"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps(doc))
            with self.quiet() as out:
                self.assertEqual(ep.main(["acquire", str(path), "--dest", str(Path(tmp) / "claude")]), 1)
            self.assertIn("missing binary_version", out.getvalue())

    def test_acquire_refuses_an_extensionless_manifest_without_raising(self):
        manifest = {"environment": {"binary_version": VERSION}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps(manifest))
            with self.quiet() as out:
                self.assertEqual(ep.main(["acquire", str(path), "--dest", str(Path(tmp) / "claude")]), 1)
            self.assertIn("has no t005-environment-pin/1 extension", out.getvalue())


if __name__ == "__main__":
    unittest.main()
