"""Executable contract for the blind judge transports, on fake binaries."""

from __future__ import annotations

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
import clause_judge as cj  # noqa: E402

SMOKE = ROOT / "campaigns" / "clause-shipper-smoke"


def executable(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def claude_stream(judgment: dict, model: str = "claude-sonnet-5") -> str:
    events = [
        {"type": "system", "subtype": "init", "model": model},
        {"type": "assistant", "message": {"model": model, "content": []}},
        {"type": "result", "result": json.dumps(judgment), "stop_reason": "end_turn"},
    ]
    return "\n".join(json.dumps(e) for e in events) + "\n"


def codex_stream(judgment: dict) -> str:
    events = [
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(judgment)}},
        {"type": "turn.completed", "usage": {}},
    ]
    return "\n".join(json.dumps(e) for e in events) + "\n"


class JudgeTransports(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.run_dir = base / "run"
        cc.ClauseCampaign.load(SMOKE / "campaign.toml").exercise(self.run_dir)
        self.bin = base / "bin"
        self.bin.mkdir()
        self.out = base / "judge"
        self.home = base / "home"
        (self.home / ".codex").mkdir(parents=True)
        (self.home / ".codex" / "auth.json").write_text("{}")
        self._home_patch = unittest.mock.patch.object(Path, "home", return_value=self.home)
        self._home_patch.start()

    def tearDown(self):
        self._home_patch.stop()
        self.temporary.cleanup()

    def fake_claude(self, judgment: dict, model: str = "claude-sonnet-5") -> Path:
        (self.bin / "claude.jsonl").write_text(claude_stream(judgment, model))
        return executable(self.bin / "claude", (
            'if [ "$1" = "--version" ]; then echo "9.9.9 (Fake)"; exit 0; fi\n'
            f'echo "$@" >> "{self.bin}/claude.argv"\n'
            f'cat "{self.bin}/claude.jsonl"\n'
        ))

    def fake_codex(self, judgment: dict, model: str = "gpt-5.6-sol", rollout_extra: str = "") -> Path:
        (self.bin / "codex.jsonl").write_text(codex_stream(judgment))
        # Codex 0.147.0 writes its built-in instructions into session_meta; the
        # phrase "basic confirmations" is what the capture spine's word-keyed
        # sanitizer mistakes for a Basic authorization value.
        meta = {"type": "session_meta", "payload": {"instructions":
                "Usually skip visuals for single facts, one-step actions, simple edits, basic confirmations, or information already clear." + rollout_extra}}
        rollout = json.dumps(meta) + "\n" + json.dumps({"type": "turn_context", "payload": {"model": model}}) + "\n"
        (self.bin / "rollout.jsonl").write_text(rollout)
        return executable(self.bin / "codex", (
            'if [ "$1" = "--version" ]; then echo "codex-cli 0.0.0"; exit 0; fi\n'
            f'echo "$@" >> "{self.bin}/codex.argv"\n'
            'mkdir -p "$CODEX_HOME/sessions/2026"\n'
            f'cp "{self.bin}/rollout.jsonl" "$CODEX_HOME/sessions/2026/rollout-1.jsonl"\n'
            f'cat "{self.bin}/codex.jsonl"\n'
        ))

    def test_claude_judge_records_and_verifies_every_task(self):
        binary = self.fake_claude({"label": "yes", "excerpts": [], "reason": "clear"})
        manifest = cj.run(self.run_dir, self.out, "claude", binary, workers=2)
        self.assertEqual(manifest["judged"], 4)
        self.assertEqual(manifest["errors"], [])
        argv = (self.bin / "claude.argv").read_text()
        self.assertIn("--model claude-sonnet-5 --effort high --tools  --setting-sources project", argv)
        self.assertIn("--json-schema", argv)
        report = cj.verify(self.run_dir, self.out, "claude")
        self.assertEqual(report["verified"], 4)
        self.assertEqual(report["missing"], [])
        self.assertEqual(set(report["labels"].values()), {"yes"})
        record = json.loads(next((self.out / "claude").glob("*.json")).read_text())
        if "task_sha256" in record:
            self.assertNotIn("variant_id", record)
            self.assertNotIn("trial_id", record)

    def test_codex_judge_retains_rollout_and_checks_its_model(self):
        binary = self.fake_codex({"label": "present", "excerpts": ["a dial worth turning"], "reason": "r"})
        manifest = cj.run(self.run_dir, self.out, "codex", binary, workers=1, limit=1)
        self.assertEqual(manifest["judged"], 1)
        self.assertIn("-m gpt-5.6-sol -c model_reasoning_effort=\"high\" --json --output-schema", (self.bin / "codex.argv").read_text())
        self.assertEqual(len(list((self.out / "codex").glob("*.rollout.jsonl"))), 1)
        report = cj.verify(self.run_dir, self.out, "codex")
        self.assertEqual(report["verified"], 1)
        self.assertEqual(len(report["missing"]), 3)

        wrong = self.fake_codex({"label": "none", "excerpts": [], "reason": "r"}, model="gpt-other")
        shutil.rmtree(self.out / "codex")
        manifest = cj.run(self.run_dir, self.out, "codex", wrong, workers=1, limit=1)
        self.assertEqual(manifest["judged"], 0)
        self.assertIn("not 'gpt-5.6-sol'", manifest["errors"][0])

    def test_rerun_reuses_records_and_tampering_is_caught(self):
        binary = self.fake_claude({"label": "yes", "excerpts": [], "reason": "clear"})
        cj.run(self.run_dir, self.out, "claude", binary, workers=1)
        calls = len((self.bin / "claude.argv").read_text().splitlines())
        cj.run(self.run_dir, self.out, "claude", binary, workers=1)
        self.assertEqual(len((self.bin / "claude.argv").read_text().splitlines()), calls)
        raw = next((self.out / "claude").glob("*.stdout.jsonl"))
        raw.write_text(raw.read_text().replace("yes", "nope"))
        with self.assertRaisesRegex(ValueError, "raw stream does not match"):
            cj.verify(self.run_dir, self.out, "claude")

    def test_rollout_with_a_credential_shape_is_refused(self):
        leaky = self.fake_codex({"label": "none", "excerpts": [], "reason": "r"},
                                rollout_extra=" Authorization: Bearer AbCdEfGhIjKlMnOpQrStUvWxYz012345")
        manifest = cj.run(self.run_dir, self.out, "codex", leaky, workers=1, limit=1)
        self.assertEqual(manifest["judged"], 0)
        self.assertIn("codex rollout carries a credential shape", manifest["errors"][0])
        self.assertEqual(sorted(p.name for p in (self.out / "codex").iterdir()), ["manifest.json"])

    def test_judge_child_environment_is_allow_listed(self):
        binary = self.fake_claude({"label": "yes", "excerpts": [], "reason": "clear"})
        binary.write_text(binary.read_text().replace(
            'cat "', f'env | cut -d= -f1 | sort | tr "\\n" " " >> "{self.bin}/env.txt"; echo >> "{self.bin}/env.txt"\ncat "', 1))
        shell_only = {"CLAUDE_CODE_OAUTH_TOKEN": "stale", "CLAUDE_CODE_MESSAGING_TOKEN": "tok",
                      "SSH_AUTH_SOCK": "/tmp/s", "ANTHROPIC_API_KEY": "sk-ant-api03-stale"}
        with unittest.mock.patch.dict(os.environ, shell_only):
            manifest = cj.run(self.run_dir, self.out, "claude", binary, workers=1, limit=1)
            expected = {name for name in cc.CHILD_ENV_ALLOWLIST if name in os.environ} | set(cc.CHILD_ENV_FIXED)
        self.assertEqual(manifest["judged"], 1)
        received = set((self.bin / "env.txt").read_text().split()) - {"PWD", "SHLVL", "_", "OLDPWD"}
        self.assertEqual(received, expected)

    def test_first_authentication_failure_stops_the_pass(self):
        binary = executable(self.bin / "claude", (
            'if [ "$1" = "--version" ]; then echo "9.9.9 (Fake)"; exit 0; fi\n'
            f'echo CALL >> "{self.bin}/claude.argv"\n'
            'echo "Not logged in. Please run /login" >&2\nexit 1\n'
        ))
        manifest = cj.run(self.run_dir, self.out, "claude", binary, workers=1)
        self.assertEqual(manifest["judged"], 0)
        self.assertTrue(manifest["stop_reason"].startswith("authentication"))
        self.assertEqual(len(manifest["errors"]), 1)
        self.assertEqual(manifest["not_attempted"], 3)
        self.assertEqual(len((self.bin / "claude.argv").read_text().splitlines()), 1)
        self.assertEqual(cj.main(["run", str(self.run_dir), "--judge", "claude", "--out", str(self.out),
                                  "--binary", str(binary), "--workers", "1"]), 1)

        # Any other transport error stays a per-task record and the pass continues.
        binary = executable(self.bin / "claude", (
            'if [ "$1" = "--version" ]; then echo "9.9.9 (Fake)"; exit 0; fi\necho "boom" >&2\nexit 1\n'
        ))
        manifest = cj.run(self.run_dir, self.out, "claude", binary, workers=1)
        self.assertIsNone(manifest["stop_reason"])
        self.assertEqual(len(manifest["errors"]), 4)
        self.assertEqual(manifest["not_attempted"], 0)

    def test_prompt_carries_question_rubric_prompt_and_response_only(self):
        _, tasks = cj.load_tasks(self.run_dir)
        text = cj.judge_prompt(tasks[0])
        for key in ("question", "rubric", "prompt", "response"):
            self.assertIn(tasks[0][key], text)
        self.assertNotIn("control", text)
        self.assertNotIn("treatment", text)


class FinalResultCheck(unittest.TestCase):
    def test_only_the_final_result_event_decides(self):
        retry_then_success = (
            '{"type":"user","message":{"content":[{"type":"tool_result","is_error":true,"content":"Output does not match required schema"}]}}\n'
            '{"type":"result","subtype":"success","is_error":false,"result":"{}"}\n'
        )
        self.assertFalse(cj._final_result_is_error(retry_then_success))
        self.assertTrue(cj._final_result_is_error('{"type":"result","subtype":"success","is_error":true,"api_error_status":401}\n'))
        self.assertTrue(cj._final_result_is_error(""))
        self.assertTrue(cj._final_result_is_error('{"type":"system","subtype":"init"}\n'))


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
