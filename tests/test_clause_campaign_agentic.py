"""Executable contract for the claude-code/2 tool-enabled adapter, on a fake binary.

Nothing here reaches a network or a real Claude Code binary. The "binary" is a
shell script that mutates its working directory and prints a canned
tool-enabled stream; sandbox-exec is replaced by a pass-through script so the
oracle runs on any platform (the real shim is proven by `shim-check`); the
final-message scanner is a stub with the agreed interface.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import tomllib
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402
import clause_judge as cj  # noqa: E402

SMOKE = ROOT / "campaigns" / "clause-shipper-smoke"
BAKEOFF_10_RUN = ROOT / "campaigns" / "clause-bakeoff-10-2026-09-01" / "results" / "run-2026-09-01"
VERSION = "9.9.9 (Fake Claude Code)"
MODEL = "claude-opus-5"
SEED = 1  # dispatch_seed whose two blocks come out treatment-first, then control-first
TOOLS = ["Bash", "Read", "Edit", "Write", "Grep", "Glob"]
INTERPRETER = os.path.realpath(sys.executable)
PY_VERSION = platform.python_version()

STUB_SCAN = '''
TAIL_TITLES = ("next steps", "summary", "changes needed", "what i did", "notes")
OFFER = ("let me know",)


def scan(text):
    lines = text.splitlines()
    headings = [line.lstrip("#").strip() for line in lines if line.startswith("#")]
    tails = [title for title in headings if title.lower() in TAIL_TITLES]
    offers = sum(text.lower().count(phrase) for phrase in OFFER)
    return {
        "words": len(text.split()), "headings": len(headings),
        "bullets": sum(line.startswith("- ") for line in lines), "bold_leadins": 0,
        "tail_section_count": len(tails), "tail_first_line": tails[0] if tails else "",
        "tail_words": 0, "closing_offer_count": offers, "closing_offer_last_block": offers > 0,
        "narration_opener": text.lower().startswith("i'll"), "file_refs": 0, "file_line_refs": 0,
        "mean_sentence_words": 1.5, "mean_paragraph_words": 3.0,
        "tail_section_titles": tails, "closing_offer_phrases": ["let me know"] * offers,
    }
'''

ORACLE_RUN = (
    "import os, sys\n"
    "sys.path.append(os.getcwd())\n"
    "sys.exit(0 if os.path.exists('added.py') else 1)\n"
)


def agentic_stream(text: str = "Fixed the bug. Tests pass.", *, model: str = MODEL, tools: list | None = None,
                   mode: str = "acceptEdits", reminder: str = "<system-reminder>SECRET-MARKER</system-reminder>",
                   subtype: str = "success", is_error: bool = False, extra_input: dict | None = None) -> str:
    edit_input = {"file_path": "README.md", "old_string": "a", "new_string": "b"}
    edit_input.update(extra_input or {})
    events = [
        {"type": "system", "subtype": "init", "model": model, "tools": TOOLS if tools is None else tools,
         "permissionMode": mode},
        {"type": "assistant", "message": {"model": model, "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "python3 -m unittest -q"}},
            {"type": "tool_use", "id": "t2", "name": "Edit", "input": edit_input},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": f"OK\n{reminder}"},
            {"type": "tool_result", "tool_use_id": "t2", "content": "edited"},
        ]}},
        {"type": "assistant", "message": {"model": model, "content": [
            {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "ls -la /etc"}},
            {"type": "tool_use", "id": "t4", "name": "Read", "input": {"file_path": "/Users/someone/.zshrc"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t3", "is_error": True,
             "content": "Claude requested permissions to use Bash, but you haven't granted it yet."},
        ]}},
        {"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": text}]}},
        {"type": "result", "subtype": subtype, "is_error": is_error, "result": text, "stop_reason": "end_turn",
         "num_turns": 3, "total_cost_usd": 0.5, "usage": {"input_tokens": 1, "output_tokens": 2},
         "modelUsage": {model: {"costUSD": 0.5}},
         "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t3", "tool_input": {"command": "ls -la /etc"}}]},
    ]
    return "\n".join(json.dumps(event) for event in events) + "\n"


def executable(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class AgenticCampaign(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.campaign_dir = base / "campaign"
        shutil.copytree(SMOKE, self.campaign_dir)
        probe = self.campaign_dir / "probes" / "report-status"
        (probe / "oracle").mkdir()
        (probe / "oracle" / "run.py").write_text(ORACLE_RUN)
        (probe / "fixture.json").write_text(json.dumps({
            "prompt": "Report whether the required verification completed.",
            "oracle": {"argv": ["python3", "-I", "-B", "oracle/run.py"], "timeout_seconds": 60},
        }))
        self.bin_dir = base / "bin"
        self.bin_dir.mkdir()
        self.run_dir = base / "run"
        scan_path = base / "final_message_scan.py"
        scan_path.write_text(STUB_SCAN)
        spec = importlib.util.spec_from_file_location("stub_final_message_scan", scan_path)
        stub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stub)
        fake_sandbox = executable(base / "sandbox-exec", 'shift 2\nexec "$@"\n')
        self.patches = [
            unittest.mock.patch.object(cc, "SCAN_MODULE", scan_path),
            unittest.mock.patch.object(cc, "_scan_text", stub.scan),
            unittest.mock.patch.object(cc, "SANDBOX_EXEC", str(fake_sandbox)),
        ]
        for patch in self.patches:
            patch.start()
        self.scan_path = scan_path

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.temporary.cleanup()

    # -- fixtures -----------------------------------------------------------

    def declare(self, binary: Path, *, measures: str | None = None, variants: str | None = None,
                **overrides) -> Path:
        smoke = tomllib.loads((SMOKE / "campaign.toml").read_text())
        judgmental = next(item for item in smoke["measures"] if item["kind"] == "judgmental")
        probe = self.campaign_dir / "probes" / "report-status"
        fields = {
            "adapter": cc.AGENTIC_ADAPTER, "network": True, "model": MODEL, "effort": "high",
            "binary": str(binary), "binary_version": VERSION,
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "timeout_seconds": 30, "workers": 1, "tools": TOOLS, "permission_mode": "acceptEdits",
            "allowed_tools": ["Bash(python3 *)"], "max_budget_usd": 3.0,
            "python_interpreter": INTERPRETER, "python_version": PY_VERSION,
        }
        fields.update(overrides)
        execution = "".join(f"{key} = {json.dumps(value)}\n" for key, value in fields.items())
        if measures is None:
            measures = (
                '[[measures]]\nid = "oracle-pass"\nkind = "deterministic"\ngrader = "oracle_pass"\n\n'
                '[[measures]]\nid = "tail-section"\nkind = "deterministic"\ngrader = "final_message_scan"\n'
                'field = "tail_section_count"\nmaximum = 0\n\n'
            )
        text = (
            'schema = "clause-campaign/1"\n\n[campaign]\nid = "agentic-fake"\nprotocol = "protocol.md"\n'
            f'protocol_sha256 = "{smoke["campaign"]["protocol_sha256"]}"\nrepetitions = 2\n\n'
            f"[execution]\n{execution}\n"
            + (variants if variants is not None else "".join(
                f'[[variants]]\nid = "{item["id"]}"\nclaude_md = "{item["claude_md"]}"\nsha256 = "{item["sha256"]}"\n\n'
                for item in smoke["variants"]
            ))
            + f'[[probes]]\nid = "report-status"\npath = "probes/report-status"\ntree_sha256 = "{cc._tree_digest(probe)}"\n\n'
            + measures
            + f'[[measures]]\nid = "{judgmental["id"]}"\nkind = "judgmental"\nquestion = {json.dumps(judgmental["question"])}\n'
            f'rubric = "rubric.md"\nrubric_sha256 = "{judgmental["rubric_sha256"]}"\n'
        )
        declaration = self.campaign_dir / "campaign.toml"
        declaration.write_text(text)
        return declaration

    def binary(self, stream_text: str | None = None, *, mutate: bool = True, pre_oracle: bool = False,
               exit_code: int = 0) -> Path:
        (self.bin_dir / "stream.jsonl").write_text(agentic_stream() if stream_text is None else stream_text)
        body = (
            f'if [ "$1" = "--version" ]; then echo "{VERSION}"; exit 0; fi\n'
            f'echo "$PWD" >> "{self.bin_dir}/cwds.txt"\n'
            f'echo "$@" >> "{self.bin_dir}/argv.txt"\n'
            f'env | cut -d= -f1 | sort | tr "\\n" " " >> "{self.bin_dir}/env.txt"; echo >> "{self.bin_dir}/env.txt"\n'
            f'shasum -a 256 CLAUDE.md | cut -c1-64 >> "{self.bin_dir}/order.txt"\n'
        )
        if mutate:
            body += "printf 'x = 1\\n' > added.py\nprintf '\\nedited\\n' >> README.md\n"
        if pre_oracle:
            body += "mkdir -p oracle\nprintf 'raise SystemExit(0)\\n' > oracle/run.py\n"
        body += f'cat "{self.bin_dir}/stream.jsonl"\nexit {exit_code}\n'
        return executable(self.bin_dir / "claude", body)

    def authorize(self, plan: dict) -> Path:
        grant = {"schema": cc.AUTHORIZATION_SCHEMA, "plan_sha256": plan["plan_sha256"],
                 "authorized_by": "Test Owner", "authorized_on": "2026-09-05", "statement": "test"}
        path = Path(self.temporary.name) / "authorization.json"
        path.write_bytes(cc._pretty(grant))
        return path

    def run_campaign(self, declaration: Path, run_dir: Path | None = None, **kwargs) -> tuple[dict, Path]:
        run_dir = run_dir or self.run_dir
        campaign = cc.ClauseCampaign.load(declaration)
        summary = campaign.exercise(run_dir, self.authorize(campaign.plan()), **kwargs)
        return summary, run_dir

    def trial(self, run_dir: Path | None = None, pattern: str = "*--r001--*.json") -> dict:
        return json.loads(next(((run_dir or self.run_dir) / "trials").glob(pattern)).read_text())

    def failure(self, run_dir: Path | None = None) -> dict:
        return json.loads(next(((run_dir or self.run_dir) / "failures").glob("*.json")).read_text())

    # -- tests --------------------------------------------------------------

    ABSENT_AND_FILE = (
        '[[variants]]\nid = "n0-no-file"\nabsent = true\n\n'
        '[[variants]]\nid = "treatment"\nclaude_md = "variants/treatment.md"\n'
        'sha256 = "d91df3ca4788f3122f6a944b55b9c38b079cc081179cedd2e4b52a6aa015651d"\n\n'
    )

    def test_absent_file_variant_runs_with_no_claude_md_and_records_none(self):
        binary = self.binary()
        summary, run_dir = self.run_campaign(self.declare(binary, variants=self.ABSENT_AND_FILE))
        self.assertEqual(summary["trial_count"], 4)
        absent = self.trial(run_dir, "n0-no-file--*--r001--*.json")
        present = self.trial(run_dir, "treatment--*--r001--*.json")
        self.assertIsNone(absent["claude_md_sha256"])
        self.assertIsNone(absent["generation"]["claude_md_final_sha256"])
        self.assertEqual(present["claude_md_sha256"], present["generation"]["claude_md_final_sha256"])
        # The fake binary hashes CLAUDE.md in each workspace; shasum writes nothing
        # for the absent arm, so only the two treatment workspaces leave a line.
        order = [line.strip() for line in (self.bin_dir / "order.txt").read_text().splitlines() if line.strip()]
        self.assertEqual(order, [present["claude_md_sha256"]] * 2)
        self.assertEqual(cc.ClauseCampaign.verify(run_dir)["trial_count"], 4)

    def test_claude_md_created_in_an_absent_arm_is_an_environment_failure(self):
        binary = self.binary()
        body = binary.read_text().replace("cat \"", "printf 'made\\n' > CLAUDE.md\ncat \"", 1)
        binary.write_text(body)
        declaration = self.declare(binary, variants=self.ABSENT_AND_FILE, workers=1)
        campaign = cc.ClauseCampaign.load(declaration)
        with self.assertRaises(ValueError):
            campaign.exercise(self.run_dir, self.authorize(campaign.plan()))
        failure = self.failure()
        self.assertEqual(failure["kind"], "environment")
        self.assertIn("appeared", failure["detail"])

    def test_absent_flag_must_be_true_and_single_variant_declarations_load(self):
        binary = self.binary()
        with self.assertRaises(ValueError):
            cc.ClauseCampaign.load(self.declare(
                binary, variants='[[variants]]\nid = "n0"\nabsent = false\n\n'))
        with self.assertRaises(ValueError):
            cc.ClauseCampaign.load(self.declare(
                binary, variants='[[variants]]\nid = "n0"\nabsent = true\nclaude_md = "x"\nsha256 = "y"\n\n'))
        single = cc.ClauseCampaign.load(self.declare(binary, variants='[[variants]]\nid = "n0-no-file"\nabsent = true\n\n'))
        plan = single.plan()
        self.assertEqual({case["variant_id"] for case in plan["cases"]}, {"n0-no-file"})
        self.assertTrue(all(case["claude_md_sha256"] is None for case in plan["cases"]))

    def test_agentic_run_passes_tool_flags_and_verifies(self):
        summary, _ = self.run_campaign(self.declare(self.binary()))
        self.assertEqual(summary["trial_count"], 4)
        self.assertEqual(summary["evidence_scope"],
                         f"live:{MODEL}:{VERSION}:{hashlib.sha256(self.binary().read_bytes()).hexdigest()[:12]}")
        argv = (self.bin_dir / "argv.txt").read_text().splitlines()[0]
        self.assertIn("--tools Bash,Edit,Glob,Grep,Read,Write --allowedTools Bash(python3 *) "
                      "--permission-mode acceptEdits --max-budget-usd 3.0 --setting-sources project", argv)
        self.assertNotIn("dontAsk", argv)
        self.assertNotIn("--add-dir", argv)
        self.assertNotIn("dangerously", argv)
        plan = json.loads((self.run_dir / "plan.json").read_text())
        self.assertEqual(plan["execution"]["scan_sha256"], cc._file_digest(self.scan_path))
        self.assertEqual(plan["execution"]["python_interpreter"], INTERPRETER)
        for cwd in (self.bin_dir / "cwds.txt").read_text().splitlines():
            self.assertFalse(Path(cwd).exists())
            self.assertNotIn(str(Path.home()), cwd)
        self.assertEqual(cc.ClauseCampaign.verify(self.run_dir), summary)

    def test_reminder_spans_are_withheld_and_counted(self):
        self.run_campaign(self.declare(self.binary()))
        trial = self.trial()
        raw = self.run_dir / "trials" / f"{trial['trial_id']}.stdout.jsonl"
        text = raw.read_text()
        self.assertIn(cc.REMINDER_PLACEHOLDER, text)
        self.assertNotIn("SECRET-MARKER", text)
        self.assertNotIn("<system-reminder>", text.lower())
        self.assertEqual(trial["generation"]["reminder_spans_withheld"], 1)
        self.assertEqual(trial["generation"]["retained_stream"], "reminder-spans-withheld")
        self.assertEqual(trial["generation"]["raw_stdout_sha256"], cc._file_digest(raw))

        unpaired = self.binary(agentic_stream(reminder="<system-reminder>dangling"))
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "run stopped|failed"):
                self.run_campaign(self.declare(unpaired, workers=1), run_dir)
            record = self.failure(run_dir)
        self.assertEqual(record["kind"], "environment")
        self.assertIn("unpaired reminder", record["detail"])
        self.assertNotIn("dangling", record["stderr_tail"].split("<withheld:tag>")[0][-20:])
        self.assertNotIn("<system-reminder>", record["stderr_tail"].lower())

    def test_tool_activity_denials_workspace_and_environment_are_recorded(self):
        shell_only = {"CLAUDE_CODE_MESSAGING_TOKEN": "tok", "SSH_AUTH_SOCK": "/tmp/s",
                      "ANTHROPIC_API_KEY": "sk-ant-api03-stale", "ANTHROPIC_MODEL": "other",
                      "CLAUDE_CODE_OAUTH_TOKEN": "stale"}
        with unittest.mock.patch.dict(os.environ, shell_only):
            self.run_campaign(self.declare(self.binary()))
            expected = {name for name in cc.CHILD_ENV_ALLOWLIST if name in os.environ}
        expected |= set(cc.CHILD_ENV_FIXED) | {"TMPDIR"}
        generation = self.trial()["generation"]
        self.assertEqual(generation["tool_calls"], {"Bash": 2, "Edit": 1, "Read": 1})
        self.assertEqual([item["name"] for item in generation["tool_call_sequence"]], ["Bash", "Edit", "Bash", "Read"])
        self.assertEqual([item["index"] for item in generation["tool_call_sequence"]], [0, 1, 2, 3])
        self.assertEqual(generation["bash_commands"], ["python3 -m unittest -q", "ls -la /etc"])
        self.assertEqual(generation["tool_results"], 3)
        self.assertEqual(generation["num_turns"], 3)
        self.assertEqual(generation["permission_denials"], [{"tool_name": "Bash", "input": "ls -la /etc"}])
        self.assertEqual([(item["name"], item["path"]) for item in generation["paths_outside_workspace"]],
                         [("Bash", "/etc"), ("Read", "/Users/someone/.zshrc")])
        self.assertFalse(generation["claude_md_referenced"])
        self.assertEqual(generation["init_tools"], TOOLS)
        self.assertEqual(generation["init_permission_mode"], "acceptEdits")
        self.assertEqual(generation["model_usage"], {MODEL: {"costUSD": 0.5}})
        self.assertEqual(generation["max_budget_usd"], 3.0)
        self.assertEqual(generation["claude_md_final_sha256"], self.trial()["claude_md_sha256"])
        changed = {item["path"]: item["change"] for item in generation["workspace"]["files_changed"]}
        self.assertEqual(changed, {"added.py": "added", "README.md": "modified"})
        self.assertEqual(generation["workspace"]["added_top_level_py"], ["added.py"])
        self.assertEqual(generation["sandbox"]["python3"], INTERPRETER)
        self.assertEqual(len(generation["sandbox"]["profile_sha256"]), 64)
        self.assertEqual(set(generation["child_env_names"]), expected)
        for line in (self.bin_dir / "env.txt").read_text().splitlines():
            received = set(line.split()) - {"PWD", "SHLVL", "_", "OLDPWD"}
            self.assertEqual(received, expected)
        self.assertNotIn("stripped_env", generation)

    def test_claude_md_reference_and_mutation_are_detected(self):
        referenced = self.binary(agentic_stream(extra_input={"file_path": "CLAUDE.md"}))
        self.run_campaign(self.declare(referenced))
        self.assertTrue(self.trial()["generation"]["claude_md_referenced"])

        mutator = self.binary()
        mutator.write_text(mutator.read_text().replace("cat ", "printf 'tampered' >> CLAUDE.md\ncat ", 1))
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "run stopped|failed"):
                self.run_campaign(self.declare(mutator), run_dir)
            record = self.failure(run_dir)
        self.assertEqual(record["kind"], "environment")
        self.assertIn("CLAUDE.md changed", record["detail"])

    def test_oracle_pass_fail_and_overwrite(self):
        summary, _ = self.run_campaign(self.declare(self.binary()))
        oracle = self.trial()["generation"]["oracle"]
        self.assertEqual(oracle["exit_code"], 0)
        self.assertFalse(oracle["timed_out"])
        self.assertEqual(oracle["argv"], [INTERPRETER, "-I", "-B", "oracle/run.py"])
        self.assertEqual(oracle["copied"], ["oracle/run.py"])
        self.assertEqual(oracle["overwrote"], [])
        self.assertIsNone(oracle["error"])
        for variant in ("control", "treatment"):
            self.assertEqual(summary["variants"][variant]["deterministic_measures"]["oracle-pass"],
                             {"passes": 2, "checks": 2})

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            summary, _ = self.run_campaign(self.declare(self.binary(mutate=False, pre_oracle=True)), run_dir)
            oracle = self.trial(run_dir)["generation"]["oracle"]
            grades = json.loads((run_dir / "grades.json").read_text())["rows"]
        self.assertEqual(oracle["exit_code"], 1)
        self.assertEqual(oracle["overwrote"], ["oracle/run.py"])
        self.assertEqual(summary["variants"]["control"]["deterministic_measures"]["oracle-pass"],
                         {"passes": 0, "checks": 2})
        row = next(item for item in grades if item["measure_id"] == "oracle-pass")
        self.assertEqual(row["observation"], {"exit_code": 1, "timed_out": False, "overwrote": 1, "error": None})

    def test_final_message_scan_grader_and_sealed_scan_module(self):
        tail = "Done.\n\n## Next steps\n\n- run it\n"
        summary, _ = self.run_campaign(self.declare(self.binary(agentic_stream(tail))))
        self.assertEqual(summary["variants"]["control"]["deterministic_measures"]["tail-section"],
                         {"passes": 0, "checks": 2})
        grades = json.loads((self.run_dir / "grades.json").read_text())["rows"]
        row = next(item for item in grades if item["measure_id"] == "tail-section")
        self.assertEqual(row["observation"]["tail_section_count"], 1)
        self.assertEqual(row["observation"]["tail_section_titles"], ["Next steps"])
        self.assertEqual((row["observation"]["field"], row["observation"]["maximum"]), ("tail_section_count", 0))
        self.assertEqual(cc.ClauseCampaign.verify(self.run_dir), summary)
        self.scan_path.write_text(STUB_SCAN + "\n# tampered\n")
        with self.assertRaisesRegex(ValueError, "sealed scan_sha256"):
            cc.ClauseCampaign.verify(self.run_dir)

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            summary, _ = self.run_campaign(self.declare(self.binary(agentic_stream("Done."))), run_dir)
        self.assertEqual(summary["variants"]["control"]["deterministic_measures"]["tail-section"],
                         {"passes": 2, "checks": 2})

        bad = self.declare(self.binary(), measures=(
            '[[measures]]\nid = "bad"\nkind = "deterministic"\ngrader = "final_message_scan"\n'
            'field = "mean_sentence_words"\nmaximum = 0\n\n'
        ))
        with self.assertRaisesRegex(ValueError, "int or bool key"):
            cc.ClauseCampaign.load(bad)

    def test_init_surface_mismatch_is_an_environment_failure(self):
        with self.assertRaisesRegex(ValueError, "run stopped|failed"):
            self.run_campaign(self.declare(self.binary(agentic_stream(tools=[]))))
        record = self.failure()
        self.assertEqual(record["kind"], "environment")
        self.assertIn("init tools", record["detail"])

    def test_budget_breach_is_a_censoring_record_with_its_own_ceiling(self):
        stream = agentic_stream(subtype="error_max_budget_usd", is_error=True)
        with self.assertRaisesRegex(ValueError, "timeout/budget fraction exceeded"):
            self.run_campaign(self.declare(self.binary(stream)))
        records = [json.loads(path.read_text()) for path in (self.run_dir / "failures").glob("*.json")]
        self.assertEqual({record["kind"] for record in records}, {"budget"})
        self.assertEqual(len(records), 2, "the 25% ceiling on 4 planned trials trips at the second record")
        self.assertEqual(records[0]["variant_id"], "control")
        self.assertEqual(records[0]["probe_id"], "report-status")

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "failure fraction exceeded"):
                self.run_campaign(self.declare(self.binary(agentic_stream(subtype="error_during_execution", is_error=True))), run_dir)

    def test_seed_credential_shape_is_refused_at_load(self):
        (self.campaign_dir / "probes" / "report-status" / "seed" / "notes.txt").write_text(
            "token sk-ant-api03-abcdefghijklmnop here\n")
        with self.assertRaisesRegex(ValueError, "seed file notes.txt carries a credential shape"):
            cc.ClauseCampaign.load(self.declare(self.binary()))

    def test_interpreter_pin_is_checked_at_load(self):
        with self.assertRaisesRegex(ValueError, "python_interpreter reports"):
            cc.ClauseCampaign.load(self.declare(self.binary(), python_version="0.0.1"))
        with self.assertRaisesRegex(ValueError, "regular file"):
            cc.ClauseCampaign.load(self.declare(self.binary(), python_interpreter="/nonexistent/python3"))
        with self.assertRaisesRegex(ValueError, "permission_mode"):
            cc.ClauseCampaign.load(self.declare(self.binary(), permission_mode="bypassPermissions"))

    def test_workspace_under_the_repository_is_refused(self):
        with unittest.mock.patch.object(cc, "REPO_ROOT", Path(tempfile.gettempdir()).resolve()):
            with self.assertRaisesRegex(ValueError, "run stopped|failed"):
                self.run_campaign(self.declare(self.binary()))
        self.assertIn("under the repository", self.failure()["detail"])
        self.assertFalse((self.bin_dir / "argv.txt").exists())

    def test_dispatch_is_repetition_major(self):
        self.run_campaign(self.declare(self.binary()))
        variants = {cc._file_digest(path): path.stem for path in (self.campaign_dir / "variants").glob("*.md")}
        order = [variants[line.strip()] for line in (self.bin_dir / "order.txt").read_text().splitlines()]
        self.assertEqual(order, ["control", "treatment", "control", "treatment"])

    def test_dispatch_seed_shuffles_within_blocks_and_is_reproducible_from_the_plan(self):
        declaration = self.declare(self.binary())
        declaration.write_text(declaration.read_text().replace("repetitions = 2\n", f"repetitions = 2\ndispatch_seed = {SEED}\n"))
        campaign = cc.ClauseCampaign.load(declaration)
        plan = campaign.plan()
        self.assertEqual(plan["dispatch_seed"], SEED)
        self.assertEqual([c["variant_id"] for c in plan["cases"]], ["control", "control", "treatment", "treatment"])
        expected = [(c["repetition"], c["variant_id"]) for c in cc.dispatch_order(plan)]
        self.assertEqual(expected, [(1, "treatment"), (1, "control"), (2, "control"), (2, "treatment")])
        summary = campaign.exercise(self.run_dir, self.authorize(plan))
        variants = {cc._file_digest(path): path.stem for path in (self.campaign_dir / "variants").glob("*.md")}
        order = [variants[line.strip()] for line in (self.bin_dir / "order.txt").read_text().splitlines()]
        self.assertEqual(order, [variant for _, variant in expected])
        self.assertEqual(summary["trial_count"], 4)
        self.assertEqual(cc.dispatch_order(cc._read_canonical(self.run_dir / "plan.json", "plan")), cc.dispatch_order(plan))
        for bad in ("-1", "true", '"7"', str(2**31)):
            declaration.write_text(declaration.read_text().replace(f"dispatch_seed = {SEED}\n", f"dispatch_seed = {bad}\n"))
            with self.assertRaisesRegex(ValueError, "dispatch_seed"):
                cc.ClauseCampaign.load(declaration)
            declaration.write_text(declaration.read_text().replace(f"dispatch_seed = {bad}\n", f"dispatch_seed = {SEED}\n"))

    def test_deadline_stops_dispatch_and_rerun_resumes(self):
        deadline = datetime(2026, 9, 5, 13, 0, tzinfo=timezone.utc)
        declaration = self.declare(self.binary())
        with unittest.mock.patch.object(cc, "_now", return_value=deadline + timedelta(seconds=1)):
            with self.assertRaisesRegex(ValueError, "deadline .* reached; 4 trial\\(s\\) not dispatched"):
                self.run_campaign(declaration, deadline_utc="2026-09-05T13:00:00Z")
        self.assertFalse((self.bin_dir / "argv.txt").exists())
        with unittest.mock.patch.object(cc, "_now", return_value=deadline - timedelta(hours=1)):
            summary, _ = self.run_campaign(declaration, deadline_utc="2026-09-05T13:00:00Z")
        self.assertEqual(summary["trial_count"], 4)
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.run_campaign(declaration, deadline_utc="2026-09-05T13:00:00")

    def test_grade_partial_grades_recorded_trials_outside_the_run(self):
        self.run_campaign(self.declare(self.binary()))
        before = sorted(path.relative_to(self.run_dir).as_posix() for path in self.run_dir.rglob("*") if path.is_file())
        trial = self.trial(pattern="treatment--*--r002--*.json")
        for suffix in (".json", ".stdout.jsonl"):
            (self.run_dir / "trials" / f"{trial['trial_id']}{suffix}").unlink()
        out = Path(self.temporary.name) / "partial"
        summary = cc.grade_partial(self.run_dir, out)
        self.assertTrue(summary["partial"])
        self.assertEqual((summary["planned_cases"], summary["recorded_cases"]), (4, 3))
        self.assertEqual((summary["repetitions"], summary["complete_repetitions"]), (2, 1))
        self.assertTrue(summary["truncated"])
        self.assertEqual(summary["variants"]["treatment"], {
            "trials": 1, "planned": 2,
            "deterministic_measures": {"oracle-pass": {"passes": 1, "checks": 1},
                                       "tail-section": {"passes": 1, "checks": 1}},
        })
        self.assertEqual(sorted(path.name for path in out.iterdir()),
                         ["grades.json", "judgments.json", "plan.json", "summary.json"])
        self.assertEqual((out / "plan.json").read_bytes(), (self.run_dir / "plan.json").read_bytes())
        _, tasks = cj.load_tasks(out)
        self.assertEqual(len(tasks), 3)
        after = sorted(path.relative_to(self.run_dir).as_posix() for path in self.run_dir.rglob("*") if path.is_file())
        self.assertEqual(after, [name for name in before if trial["trial_id"] not in name])
        with self.assertRaisesRegex(ValueError, "outside the run directory"):
            cc.grade_partial(self.run_dir, self.run_dir / "partial")
        with self.assertRaisesRegex(ValueError, "run artifact set differs"):
            cc.ClauseCampaign.verify(self.run_dir)

    def test_shim_script_sets_tmpdir_and_execs_the_pinned_interpreter(self):
        base = Path(self.temporary.name)
        workspace, private = base / "ws", base / "private"
        workspace.mkdir()
        private.mkdir()
        sandbox = cc.create_sandbox(workspace, private, base / "shim", INTERPRETER)
        shim = sandbox["shim"].read_text().splitlines()
        self.assertEqual(shim[0], "#!/bin/sh")
        self.assertTrue(shim[1].startswith("export TMPDIR="))
        self.assertIn(f"-f {base / 'shim' / 'sandbox.sb'} {INTERPRETER} \"$@\"", shim[2])
        self.assertEqual(stat.S_IMODE(sandbox["shim"].stat().st_mode), 0o700)
        profile = (base / "shim" / "sandbox.sb").read_text()
        for rule in ("(deny default)", "(deny network*)", '(subpath "/Users")',
                     f'(allow file-write* (subpath "{workspace.resolve()}") (subpath "{private.resolve()}"))'):
            self.assertIn(rule, profile)
        self.assertNotIn("ANTHROPIC", " ".join(cc.CHILD_ENV_ALLOWLIST))

    def test_claude_code_1_plans_and_labels_are_unchanged(self):
        campaign = cc.ClauseCampaign.load(SMOKE / "campaign.toml")
        plan = campaign.plan()
        self.assertNotIn("scan_sha256", plan["execution"])
        self.assertEqual(cc._evidence_scope({"adapter": cc.LIVE_ADAPTER}), "synthetic-integration-only")
        self.assertEqual(cc._live_command(Path("/bin/claude"), {"adapter": cc.LIVE_ADAPTER, "model": MODEL, "effort": "high"}, "p")[10:],
                         ["--tools", "", "--setting-sources", "project", "--settings", '{"autoMemoryEnabled":false}',
                          "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--permission-mode", "dontAsk",
                          "--no-session-persistence", "--prompt-suggestions", "false"])

    def test_sealed_bakeoff_10_run_still_verifies(self):
        summary = cc.ClauseCampaign.verify(BAKEOFF_10_RUN)
        self.assertEqual(summary["trial_count"], 75)
        self.assertEqual(summary["evidence_scope"], "synthetic-integration-only")


if __name__ == "__main__":
    unittest.main()
