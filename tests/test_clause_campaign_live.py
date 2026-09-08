"""Executable contract for the claude-code/1 live adapter, on a fake binary.

No test here reaches a network or a real Claude Code binary. The "binary" is a
shell script that prints a canned stream-json transcript, so every rule the
adapter enforces (authorization, pin, version, model identity, immutability,
resume, stop conditions) is exercised without a paid call.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402

SMOKE = ROOT / "campaigns" / "clause-shipper-smoke"
VERSION = "9.9.9 (Fake Claude Code)"


def stream(text: str, model: str = "claude-opus-5") -> str:
    events = [
        {"type": "system", "subtype": "init", "model": model, "tools": [], "permissionMode": "dontAsk"},
        {"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": text}]}},
        {"type": "result", "subtype": "success", "result": text, "stop_reason": "end_turn",
         "num_turns": 1, "total_cost_usd": 0.01,
         "usage": {"input_tokens": 1, "output_tokens": 2}},
    ]
    return "\n".join(json.dumps(event) for event in events) + "\n"


def fake_binary(directory: Path, script_body: str) -> Path:
    binary = directory / "claude"
    binary.write_text("#!/bin/sh\n" + script_body)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def echo_binary(directory: Path, text: str = "Answered. Twice.", model: str = "claude-opus-5") -> Path:
    payload = stream(text, model)
    (directory / "stream.jsonl").write_text(payload)
    return fake_binary(directory, (
        f'if [ "$1" = "--version" ]; then echo "{VERSION}"; exit 0; fi\n'
        f'echo "$PWD" >> "{directory}/cwds.txt"\n'
        f'echo "$@" >> "{directory}/argv.txt"\n'
        f'cat "{directory}/stream.jsonl"\n'
    ))


class LiveCampaign(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.campaign_dir = base / "campaign"
        shutil.copytree(SMOKE, self.campaign_dir)
        self.bin_dir = base / "bin"
        self.bin_dir.mkdir()
        self.run_dir = base / "run"

    def tearDown(self):
        self.temporary.cleanup()

    def declare(self, binary: Path, **overrides) -> Path:
        sha = hashlib.sha256(binary.read_bytes()).hexdigest()
        text = (self.campaign_dir / "campaign.toml").read_text()
        head, _, tail = text.partition("[[variants]]")
        head = head[: head.index("[execution]")]
        fields = {
            "adapter": f'"{cc.LIVE_ADAPTER}"', "network": "true", "model": '"claude-opus-5"',
            "effort": '"high"', "binary": f'"{binary}"', "binary_version": f'"{VERSION}"',
            "binary_sha256": f'"{sha}"', "timeout_seconds": "30", "workers": "2",
        }
        fields.update({key: json.dumps(value) if isinstance(value, str) else str(value).lower()
                       if isinstance(value, bool) else str(value)
                       for key, value in overrides.items()})
        execution = "[execution]\n" + "".join(f"{key} = {value}\n" for key, value in fields.items())
        declaration = self.campaign_dir / "campaign.toml"
        declaration.write_text(head + execution + "\n[[variants]]" + tail)
        return declaration

    def authorize(self, plan: dict, plan_sha: str | None = None) -> Path:
        grant = {
            "schema": cc.AUTHORIZATION_SCHEMA,
            "plan_sha256": plan_sha or plan["plan_sha256"],
            "authorized_by": "Test Owner",
            "authorized_on": "2026-09-01",
            "statement": "test authorization",
        }
        path = Path(self.temporary.name) / "authorization.json"
        path.write_bytes(cc._pretty(grant))
        return path

    def test_live_declaration_plans_without_synthetic_responses(self):
        binary = echo_binary(self.bin_dir)
        probe = self.campaign_dir / "probes" / "report-status"
        before = cc._tree_digest(probe)
        shutil.rmtree(probe / "synthetic")
        declaration = self.declare(binary)
        declaration.write_text(declaration.read_text().replace(before, cc._tree_digest(probe)))
        campaign = cc.ClauseCampaign.load(declaration)
        plan = campaign.plan()
        self.assertEqual(plan["execution"]["adapter"], cc.LIVE_ADAPTER)
        self.assertIs(plan["execution"]["network"], True)
        self.assertEqual(plan["execution"]["binary_version"], VERSION)
        self.assertEqual(len(plan["cases"]), 4)
        self.assertNotIn("synthetic_response_sha256", plan["cases"][0])

    def test_pin_and_effort_are_checked_at_load(self):
        binary = echo_binary(self.bin_dir)
        declaration = self.declare(binary, binary_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "does not match the pinned binary"):
            cc.ClauseCampaign.load(declaration)
        declaration = self.declare(binary, effort="turbo")
        with self.assertRaisesRegex(ValueError, "execution.effort"):
            cc.ClauseCampaign.load(declaration)
        declaration = self.declare(binary, network=False)
        with self.assertRaisesRegex(ValueError, "network must be true"):
            cc.ClauseCampaign.load(declaration)

    def test_dispatch_refuses_without_an_authorization_naming_this_plan(self):
        binary = echo_binary(self.bin_dir)
        campaign = cc.ClauseCampaign.load(self.declare(binary))
        with self.assertRaisesRegex(ValueError, "needs --authorization"):
            campaign.exercise(self.run_dir)
        self.assertEqual(list(self.run_dir.iterdir()), [])
        wrong = self.authorize(campaign.plan(), plan_sha="1" * 64)
        with self.assertRaisesRegex(ValueError, "not this plan"):
            campaign.exercise(self.run_dir, wrong)
        self.assertEqual(list(self.run_dir.iterdir()), [])
        self.assertFalse((self.bin_dir / "argv.txt").exists())

    def test_authorized_run_records_every_trial_and_verifies(self):
        binary = echo_binary(self.bin_dir)
        campaign = cc.ClauseCampaign.load(self.declare(binary))
        grant = self.authorize(campaign.plan())

        summary = campaign.exercise(self.run_dir, grant)

        self.assertEqual(summary["trial_count"], 4)
        self.assertEqual(summary["evidence_scope"], "synthetic-integration-only")
        files = {path.relative_to(self.run_dir).as_posix()
                 for path in self.run_dir.rglob("*") if path.is_file()}
        self.assertIn("authorization.json", files)
        self.assertEqual(sum(name.endswith(".stdout.jsonl") for name in files), 4)
        trial = json.loads(next((self.run_dir / "trials").glob("*--r001--*.json")).read_text())
        self.assertEqual(trial["generation"]["answer_models"], ["claude-opus-5"])
        self.assertEqual(trial["generation"]["binary_version"], VERSION)
        self.assertEqual(trial["output"]["text"], "Answered. Twice.")
        self.assertEqual(
            trial["generation"]["raw_stdout_sha256"],
            hashlib.sha256((self.run_dir / "trials" / f"{trial['trial_id']}.stdout.jsonl").read_bytes()).hexdigest(),
        )
        argv = (self.bin_dir / "argv.txt").read_text()
        self.assertIn("--tools  --setting-sources project", argv)
        self.assertIn('--settings {"autoMemoryEnabled":false}', argv)
        self.assertIn("--model claude-opus-5 --effort high", argv)
        cwds = (self.bin_dir / "cwds.txt").read_text().splitlines()
        self.assertEqual(len(cwds), 4)
        for cwd in cwds:
            self.assertFalse(Path(cwd).exists(), "workspace must be discarded after the trial")
            self.assertNotIn(str(Path.home()), cwd)
        self.assertEqual(cc.ClauseCampaign.verify(self.run_dir), summary)

    def test_rerun_resumes_without_redispatching(self):
        binary = echo_binary(self.bin_dir)
        campaign = cc.ClauseCampaign.load(self.declare(binary))
        grant = self.authorize(campaign.plan())
        first = campaign.exercise(self.run_dir, grant)
        calls = len((self.bin_dir / "argv.txt").read_text().splitlines())
        second = campaign.exercise(self.run_dir, grant)
        self.assertEqual(first, second)
        self.assertEqual(len((self.bin_dir / "argv.txt").read_text().splitlines()), calls)

    def test_model_mismatch_stops_the_run_and_records_the_failure(self):
        binary = echo_binary(self.bin_dir, model="claude-sonnet-5")
        campaign = cc.ClauseCampaign.load(self.declare(binary, workers=1))
        grant = self.authorize(campaign.plan())
        with self.assertRaisesRegex(ValueError, "run stopped: model"):
            campaign.exercise(self.run_dir, grant)
        failures = list((self.run_dir / "failures").glob("*.json"))
        self.assertEqual(len(failures), 1)
        record = json.loads(failures[0].read_text())
        self.assertEqual(record["kind"], "model")
        self.assertFalse((self.run_dir / "trials").exists())
        self.assertFalse((self.run_dir / "grades.json").exists())

    def test_version_drift_stops_before_dispatch(self):
        binary = echo_binary(self.bin_dir)
        campaign = cc.ClauseCampaign.load(self.declare(binary, binary_version="8.8.8 (Other)", workers=1))
        grant = self.authorize(campaign.plan())
        with self.assertRaisesRegex(ValueError, "run stopped: version"):
            campaign.exercise(self.run_dir, grant)
        self.assertFalse((self.bin_dir / "argv.txt").exists())

    def test_authentication_failure_stops_the_run(self):
        binary = fake_binary(self.bin_dir, (
            f'if [ "$1" = "--version" ]; then echo "{VERSION}"; exit 0; fi\n'
            'echo "Not logged in. Please run /login" >&2\nexit 1\n'
        ))
        campaign = cc.ClauseCampaign.load(self.declare(binary, workers=1))
        grant = self.authorize(campaign.plan())
        with self.assertRaisesRegex(ValueError, "run stopped: authentication"):
            campaign.exercise(self.run_dir, grant)

        # The shape attempt 2 of bakeoff 10 produced: exit 1 with a 401 result event.
        result = json.dumps({"type": "result", "subtype": "success", "is_error": True,
                             "api_error_status": 401,
                             "result": "Failed to authenticate. API Error: 401 Invalid bearer token"})
        (self.bin_dir / "stream.jsonl").write_text(result + "\n")
        binary = fake_binary(self.bin_dir, (
            f'if [ "$1" = "--version" ]; then echo "{VERSION}"; exit 0; fi\n'
            f'cat "{self.bin_dir}/stream.jsonl"\nexit 1\n'
        ))
        campaign = cc.ClauseCampaign.load(self.declare(binary, workers=1))
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "run stopped: authentication"):
                campaign.exercise(run_dir, self.authorize(campaign.plan()))
            self.assertEqual(len(list((run_dir / "failures").glob("*.json"))), 1)

    def test_credential_and_routing_variables_never_reach_the_binary(self):
        (self.bin_dir / "stream.jsonl").write_text(stream("Answered. Twice."))
        binary = fake_binary(self.bin_dir, (
            f'if [ "$1" = "--version" ]; then echo "{VERSION}"; exit 0; fi\n'
            'echo "KEY=${ANTHROPIC_API_KEY-unset} URL=${ANTHROPIC_BASE_URL-unset} '
            f'TOK=${{ANTHROPIC_AUTH_TOKEN-unset}}" >> "{self.bin_dir}/env.txt"\n'
            f'cat "{self.bin_dir}/stream.jsonl"\n'
        ))
        campaign = cc.ClauseCampaign.load(self.declare(binary, workers=1))
        grant = self.authorize(campaign.plan())
        with unittest.mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-stale",
                                                   "ANTHROPIC_BASE_URL": "http://127.0.0.1:1"}):
            campaign.exercise(self.run_dir, grant)
        self.assertEqual(set((self.bin_dir / "env.txt").read_text().splitlines()),
                         {"KEY=unset URL=unset TOK=unset"})
        trial = json.loads(next((self.run_dir / "trials").glob("*--r001--*.json")).read_text())
        stripped = set(trial["generation"]["stripped_env"])
        # The test shell may itself carry a session token; names only, never values.
        self.assertTrue({"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"} <= stripped <= set(cc.STRIPPED_ENV))

    def test_error_results_and_credential_shaped_prose_are_handled_before_the_guard(self):
        stream_text = stream("Set password: hunter2 then restart. Done.")
        (self.bin_dir / "stream.jsonl").write_text(stream_text)
        binary = fake_binary(self.bin_dir, (
            f'if [ "$1" = "--version" ]; then echo "{VERSION}"; exit 0; fi\n'
            f'cat "{self.bin_dir}/stream.jsonl"\n'
        ))
        campaign = cc.ClauseCampaign.load(self.declare(binary, workers=1))
        summary = campaign.exercise(self.run_dir, self.authorize(campaign.plan()))
        self.assertEqual(summary["trial_count"], 4)
        trial = json.loads(next((self.run_dir / "trials").glob("*--r001--*.json")).read_text())
        self.assertEqual(trial["output"]["text"], "Set password: hunter2 then restart. Done.")
        self.assertEqual(cc.ClauseCampaign.verify(self.run_dir), summary)

        (self.bin_dir / "stream.jsonl").write_text(stream("Use sk-ant-api03-abcdefghijklmnop to call it."))
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "run stopped|failed and are recorded"):
                campaign.exercise(run_dir, self.authorize(campaign.plan()))
            record = json.loads(next((run_dir / "failures").glob("*.json")).read_text())
        self.assertEqual(record["kind"], "environment")
        self.assertIn("carries a credential", record["detail"])
        self.assertNotIn("abcdefghijklmnop", record["stderr_tail"])

        error_stream = stream("x").replace('"subtype": "success"', '"subtype": "error_during_execution", "is_error": true')
        (self.bin_dir / "stream.jsonl").write_text(error_stream.replace('"is_error": false, ', ""))
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "run stopped|failed and are recorded"):
                campaign.exercise(run_dir, self.authorize(campaign.plan()))
            record = json.loads(next((run_dir / "failures").glob("*.json")).read_text())
        self.assertEqual(record["kind"], "error")
        self.assertIn("error_during_execution", record["detail"])
        self.assertIn("--- stdout ---", record["stderr_tail"])

    def test_verify_rejects_a_tampered_raw_stream_or_authorization(self):
        binary = echo_binary(self.bin_dir)
        campaign = cc.ClauseCampaign.load(self.declare(binary))
        campaign.exercise(self.run_dir, self.authorize(campaign.plan()))
        raw = next((self.run_dir / "trials").glob("*.stdout.jsonl"))
        raw.write_text(raw.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "raw stream does not match"):
            cc.ClauseCampaign.verify(self.run_dir)

        # A forged record re-sealed with the harness's own function must not
        # pass either: the stream, not the record, is the evidence.
        raw.write_text(raw.read_text()[:-1])
        cc.ClauseCampaign.verify(self.run_dir)
        plan = json.loads((self.run_dir / "plan.json").read_text())
        trial_path = self.run_dir / "trials" / f"{raw.name[:-len('.stdout.jsonl')]}.json"
        trial = json.loads(trial_path.read_text())
        case = next(c for c in plan["cases"] if c["trial_id"] == trial["trial_id"])
        forged = cc._make_trial(plan, case, "Forged. Once.", trial["generation"])
        trial_path.write_bytes(cc._pretty(forged))
        trials = cc._load_trials(self.run_dir, plan)
        grades, judgments = cc._grade_artifacts(plan, trials)
        (self.run_dir / "grades.json").write_bytes(cc._pretty(grades))
        (self.run_dir / "judgments.json").write_bytes(cc._pretty(judgments))
        (self.run_dir / "summary.json").write_bytes(cc._pretty(cc._make_summary(plan, trials, grades, judgments)))
        with self.assertRaisesRegex(ValueError, "output text does not match its stream"):
            cc.ClauseCampaign.verify(self.run_dir)

    def test_synthetic_campaign_is_unchanged_by_the_live_adapter(self):
        campaign = cc.ClauseCampaign.load(SMOKE / "campaign.toml")
        plan = campaign.plan()
        self.assertEqual(plan["execution"]["adapter"], cc.SYNTHETIC_ADAPTER)
        self.assertIn("synthetic_response_sha256", plan["cases"][0])
        summary = campaign.exercise(self.run_dir)
        self.assertEqual(summary["trial_count"], 4)
        self.assertFalse((self.run_dir / "authorization.json").exists())


if __name__ == "__main__":
    unittest.main()
