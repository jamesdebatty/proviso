from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PREREGISTRATION = ROOT / "notes" / "preregistration-2026-08-04.md"
PRIVATE_ARTIFACTS = "requires private lab artifacts that are not included in the public release"


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


run_eval = load_script("run_eval")
score_eval = load_script("score_eval")
judge_eval = load_script("judge_eval")
human_review = load_script("human_review")


class HarnessTests(unittest.TestCase):
    @unittest.skipUnless(PREREGISTRATION.exists(), PRIVATE_ARTIFACTS)
    def test_legacy_frozen_input_set_does_not_include_the_execution_router(self):
        with tempfile.TemporaryDirectory() as temp:
            hashes = run_eval.freeze_inputs(Path(temp))

        self.assertNotIn("execution.py", hashes)

    def test_prompt_suite_is_unique_and_complete(self):
        prompts = run_eval.load_prompts()
        self.assertEqual(10, len(prompts))
        self.assertEqual(len(prompts), len({item["id"] for item in prompts}))
        self.assertTrue(all(item["must_cover"] for item in prompts))

    def test_campaign_is_balanced_and_counterbalanced(self):
        trials = run_eval.planned_trials(run_eval.load_prompts(), 3)
        self.assertEqual(60, len(trials))
        counts = {}
        first_positions = {"control": 0, "ste": 0}
        for item in trials:
            key = (item["prompt_id"], item["repetition"], item["arm"])
            counts[key] = counts.get(key, 0) + 1
            if item["position"] == 1:
                first_positions[item["arm"]] += 1
        self.assertTrue(all(value == 1 for value in counts.values()))
        self.assertEqual(first_positions["control"], first_positions["ste"])

    def test_only_treatment_gets_claude_md(self):
        arms = run_eval.load_arms()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            control = run_eval.materialize(base / "control", "control", arms)
            ste = run_eval.materialize(base / "ste", "ste", arms)
            self.assertEqual([], control["files_before"])
            self.assertEqual(["CLAUDE.md"], ste["files_before"])
            self.assertIsNone(control["claude_md_sha256"])
            self.assertEqual(run_eval.sha256(ROOT / "treatment" / "CLAUDE.md"), ste["claude_md_sha256"])

    def test_command_fixes_model_effort_and_isolation(self):
        command = run_eval.claude_args("opus", "high", "hello")
        self.assertEqual("opus", command[command.index("--model") + 1])
        self.assertEqual("high", command[command.index("--effort") + 1])
        self.assertEqual("project", command[command.index("--setting-sources") + 1])
        self.assertIn("--strict-mcp-config", command)
        self.assertIn("--no-session-persistence", command)
        self.assertEqual("false", command[command.index("--prompt-suggestions") + 1])
        self.assertEqual("", command[command.index("--tools") + 1])

    def test_primary_model_verification_uses_explicit_assistant_model(self):
        payload = {
            "_answer_models": ["claude-opus-5"],
            "modelUsage": {
                "claude-haiku-4-5": {"canonicalModel": "claude-haiku-4-5", "outputTokens": 10},
                "claude-opus-5": {"canonicalModel": "claude-opus-5", "outputTokens": 100},
            }
        }
        self.assertTrue(run_eval.verifies_opus_5(payload))
        self.assertFalse(
            run_eval.verifies_opus_5(
                {"_answer_models": ["claude-sonnet-5"], "modelUsage": {
                    "claude-opus-5": {"canonicalModel": "claude-opus-5", "outputTokens": 5},
                    "claude-sonnet-5": {"canonicalModel": "claude-sonnet-5", "outputTokens": 100},
                }}
            )
        )

    def test_timeout_byte_output_is_decoded(self):
        self.assertEqual("bad�", run_eval.text_output(b"bad\xff"))

    def test_isolation_removes_additional_instruction_directories(self):
        name = "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"
        previous = os.environ.get(name)
        os.environ[name] = "/tmp/ambient"
        try:
            self.assertNotIn(name, run_eval.isolated_env())
            self.assertNotIn(name, judge_eval.isolated_environment())
        finally:
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous

    def test_failure_threshold_matches_preregistration(self):
        self.assertFalse(run_eval.failure_threshold_exceeded(6, 60))
        self.assertTrue(run_eval.failure_threshold_exceeded(7, 60))
        self.assertTrue(run_eval.failure_threshold_exceeded(1, 2))

    def test_cli_drift_is_detected_before_next_trial(self):
        self.assertFalse(run_eval.cli_version_changed("2.1.221", "2.1.221"))
        self.assertTrue(run_eval.cli_version_changed("2.1.221", "2.1.222"))
        self.assertFalse(judge_eval.cli_version_changed("2.1.221", "2.1.221"))
        self.assertTrue(judge_eval.cli_version_changed("2.1.221", "2.1.222"))

    def test_stream_records_explicit_answer_model(self):
        raw = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5"}),
                json.dumps({"type": "assistant", "message": {"model": "claude-opus-5"}}),
                json.dumps({"type": "result", "result": "OK", "modelUsage": {}}),
            ]
        )
        payload = run_eval.parse_stream_json(raw)
        self.assertEqual("claude-opus-5", run_eval.answer_model(payload))
        self.assertTrue(run_eval.verifies_opus_5(payload))

    def test_stream_rejects_valid_json_that_is_not_an_object(self):
        for value in (None, [], "text", 7):
            raw = "\n".join((json.dumps(value), json.dumps({"type": "result"})))
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "object"):
                run_eval.parse_stream_json(raw)

    def test_terminal_failure_kinds_stop_immediately(self):
        self.assertEqual(
            "stopped_on_authentication_failure",
            run_eval.stop_status({"failure_kind": "authentication"}, 1, 60),
        )
        self.assertEqual(
            "stopped_on_model_mismatch",
            run_eval.stop_status({"failure_kind": "model_mismatch"}, 1, 60),
        )
        self.assertIsNone(run_eval.stop_status({"failure_kind": "trial_error"}, 6, 60))
        self.assertEqual(
            "stopped_on_failure_threshold",
            run_eval.stop_status({"failure_kind": "trial_error"}, 7, 60),
        )

    def test_authentication_failure_in_stdout_stops_trial(self):
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(model="opus", effort="high", timeout=10)
            trial = {
                "prompt_id": "sample",
                "category": "test",
                "repetition": 1,
                "position": 1,
                "arm": "control",
            }
            proc = SimpleNamespace(returncode=1, stdout="Error: not logged in", stderr="")
            with mock.patch.object(run_eval.subprocess, "run", return_value=proc):
                record = run_eval.run_trial(
                    Path(temp), trial, {"prompt": "hello"}, run_eval.load_arms(), args, "2.1.221"
                )
            self.assertEqual("authentication", record["failure_kind"])
            self.assertEqual(
                "stopped_on_authentication_failure",
                run_eval.stop_status(record, 1, 60),
            )

    def test_response_artifact_must_match_raw_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            trial_dir = run_dir / "trials" / "sample-r1-1-control"
            trial_dir.mkdir(parents=True)
            raw = "\n".join(
                [
                    json.dumps({"type": "assistant", "message": {"model": "claude-opus-5"}}),
                    json.dumps({"type": "result", "result": "original"}),
                ]
            )
            raw_path = trial_dir / "stdout.jsonl"
            parsed_path = trial_dir / "stdout.json"
            raw_path.write_text(raw)
            parsed_path.write_text(json.dumps(run_eval.parse_stream_json(raw)))
            record = {
                "trial_id": "sample-r1-1-control",
                "raw_stdout_sha256": run_eval.sha256(raw_path),
                "parsed_stdout_sha256": run_eval.sha256(parsed_path),
            }
            judge_eval.validated_response_payload(run_dir, record)
            parsed_path.write_text(json.dumps({"result": "tampered"}))
            with self.assertRaisesRegex(ValueError, "parsed response hash mismatch"):
                judge_eval.validated_response_payload(run_dir, record)

    def test_repository_workdir_detects_ambient_claude_md(self):
        found = run_eval.ancestor_instruction_files(ROOT / "results")
        self.assertIn(str(ROOT / "CLAUDE.md"), found)

    def test_metrics_detect_long_sentence_and_structure(self):
        text = "# Result\n\nShort sentence.\n\n- " + "word " * 21 + "done."
        result = score_eval.metrics(text)
        self.assertEqual(1, result["headings"])
        self.assertEqual(1, result["list_items"])
        self.assertEqual(1, result["sentences_over_20_words"])

    def test_blind_labels_are_stable(self):
        first = judge_eval.label_order(0)
        self.assertEqual(first, judge_eval.label_order(0))
        self.assertEqual({"control", "ste"}, set(first))

    def test_blind_labels_are_balanced_for_full_campaign(self):
        labels = [judge_eval.label_order(index)[0] for index in range(30)]
        self.assertEqual(15, labels.count("control"))
        self.assertEqual(15, labels.count("ste"))

    def test_safe_trial_path_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            with self.assertRaises(ValueError):
                judge_eval.safe_stdout_path(run_dir, "../../private-r1-1-control")
            with self.assertRaises(ValueError):
                judge_eval.safe_stdout_path(run_dir, "/tmp/private-r1-1-control")

    def test_scorer_rejects_trial_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            with self.assertRaises(ValueError):
                score_eval.safe_stdout_path(run_dir, "../../private-r1-1-control")

    def test_safe_judgment_path_rejects_prompt_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            judge_dir = Path(temp)
            with self.assertRaises(ValueError):
                judge_eval.safe_judgment_path(judge_dir, "../../private", 1, ".json")

    def test_judge_model_match_is_explicit(self):
        self.assertTrue(judge_eval.model_matches("sonnet", "claude-sonnet-5"))
        self.assertFalse(judge_eval.model_matches("sonnet", "claude-opus-5"))

    def test_cached_judgment_requires_matching_provenance(self):
        score = {
            "task_completion": 5,
            "focus": 5,
            "plain_language": 5,
            "jargon_discipline": 5,
            "nuance_and_safety": 5,
            "unnecessary_passages": [],
            "unexplained_jargon": [],
            "missing_requirements": [],
            "material_errors": [],
            "overall": "pass",
            "reason": "good",
        }
        existing = {
            "error": None,
            "judgment": {"answer_a": score, "answer_b": score, "winner": "tie", "pair_reason": "equal"},
            "judge_model": "sonnet",
            "resolved_judge_model": "claude-sonnet-5",
        }
        judge_eval.validate_cached_judgment(existing, {"judge_model": "sonnet"})
        with self.assertRaises(ValueError):
            judge_eval.validate_cached_judgment(existing, {"judge_model": "opus"})

    def test_failed_cached_judgment_is_retryable(self):
        existing = {"error": "TimeoutExpired", "judgment": None}
        self.assertFalse(judge_eval.cached_judgment_reusable(existing, {}))

    def test_judgment_artifact_must_match_raw_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            judge_dir = run_dir / "judgments"
            judge_dir.mkdir()
            raw = "\n".join(
                [
                    json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5"}}),
                    json.dumps({"type": "result", "result": json.dumps(self.valid_judgment())}),
                ]
            )
            raw_path = judge_dir / "sample-r1.stdout.txt"
            raw_path.write_text(raw)
            item = {
                "judgment": self.valid_judgment(),
                "resolved_judge_model": "claude-sonnet-5",
                "raw_stdout_sha256": judge_eval.sha256(raw_path),
            }
            judge_eval.validate_judgment_artifact(item, raw_path)
            item["judgment"]["winner"] = "A"
            with self.assertRaisesRegex(ValueError, "raw judge stream"):
                judge_eval.validate_judgment_artifact(item, raw_path)

    def test_expected_judgment_cli_comes_from_independent_run_manifest(self):
        expected = score_eval.expected_judgment_provenance(
            {"prompt_id": "sample", "repetition": 1},
            0,
            {"frozen_input_hashes": {"rubric.md": "r", "prompts.jsonl": "p"}},
            {"claude_version_before": "trusted-version"},
        )
        self.assertEqual("trusted-version", expected["claude_version"])

    def test_judge_schema_requires_quality_and_regression_scores(self):
        required = set(judge_eval.SCHEMA["$defs"]["score"]["required"])
        self.assertIn("focus", required)
        self.assertIn("jargon_discipline", required)
        self.assertIn("task_completion", required)
        self.assertIn("nuance_and_safety", required)

    def test_judgment_summary_unblinds_scores_after_grading(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            judge_dir = run_dir / "judgments"
            judge_dir.mkdir()
            payload = {
                "prompt_id": "sample",
                "labels": {"A": "ste", "B": "control"},
                "error": None,
                "judgment": {
                    "answer_a": {
                        "task_completion": 5,
                        "focus": 5,
                        "plain_language": 5,
                        "jargon_discipline": 5,
                        "nuance_and_safety": 4,
                        "material_errors": [],
                        "missing_requirements": [],
                        "overall": "pass",
                    },
                    "answer_b": {
                        "task_completion": 5,
                        "focus": 3,
                        "plain_language": 3,
                        "jargon_discipline": 3,
                        "nuance_and_safety": 5,
                        "material_errors": [],
                        "missing_requirements": [],
                        "overall": "pass",
                    },
                    "winner": "A",
                },
            }
            (judge_dir / "sample-r1.json").write_text(json.dumps(payload))
            result = score_eval.judgment_summary(run_dir)
            self.assertEqual(1, result["wins"]["ste"])
            self.assertEqual(2, result["ste_minus_control"]["focus"])

    def test_scorer_rejects_tampered_judgment_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            judge_dir = run_dir / "judgments"
            judge_dir.mkdir()
            payload = {
                "prompt_id": "sample",
                "labels": {"A": "ste", "B": "outside"},
                "error": None,
                "judgment": {
                    "answer_a": {
                        "task_completion": 5,
                        "focus": 5,
                        "plain_language": 5,
                        "jargon_discipline": 5,
                        "nuance_and_safety": 5,
                        "material_errors": [],
                        "missing_requirements": [],
                        "overall": "pass",
                    },
                    "answer_b": {
                        "task_completion": 5,
                        "focus": 5,
                        "plain_language": 5,
                        "jargon_discipline": 5,
                        "nuance_and_safety": 5,
                        "material_errors": [],
                        "missing_requirements": [],
                        "overall": "pass",
                    },
                    "winner": "tie",
                },
            }
            (judge_dir / "sample-r1.json").write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                score_eval.judgment_summary(run_dir)

    def test_control_regression_is_flagged_for_human_review(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            judge_dir = run_dir / "judgments"
            judge_dir.mkdir()
            judgment = self.valid_judgment()
            judgment["answer_a"]["material_errors"] = ["wrong"]
            payload = {
                "prompt_id": "sample",
                "repetition": 1,
                "labels": {"A": "control", "B": "ste"},
                "error": None,
                "judgment": judgment,
            }
            (judge_dir / "sample-r1.json").write_text(json.dumps(payload))
            result = score_eval.judgment_summary(run_dir)
            self.assertEqual(
                [{"prompt_id": "sample", "repetition": 1}], result["flagged_pairs"]
            )

    def test_pilot_cannot_receive_effect_verdict(self):
        manifest = {
            "status": "complete",
            "planned_trial_count": 2,
            "trial_count": 2,
            "errors": 0,
            "records": [
                {"prompt_id": "sample", "opus_5_verified": True},
                {"prompt_id": "sample", "opus_5_verified": True},
            ],
        }
        result = score_eval.acceptance(manifest, {}, {})
        self.assertEqual("indeterminate", result["verdict"])
        self.assertIn("pilot", result["reason"])

    def test_low_effort_campaign_is_indeterminate(self):
        manifest = {
            "status": "complete",
            "requested_model": "opus",
            "requested_effort": "low",
            "planned_trial_count": 60,
            "trial_count": 60,
            "errors": 0,
            "records": [
                {"prompt_id": f"prompt-{index // 6}", "opus_5_verified": True,
                 "requested_model": "opus", "requested_effort": "low"}
                for index in range(60)
            ],
        }
        result = score_eval.acceptance(manifest, {}, {})
        self.assertEqual("indeterminate", result["verdict"])
        self.assertIn("Opus 5 High", result["reason"])

    def test_completed_human_review_finalizes_supported_verdict(self):
        automated = {
            "verdict": "indeterminate",
            "automated_verdict": "supported",
            "reason": "human review is required before the final verdict",
        }
        human = {"complete": True, "final_verdict": "supported"}
        result = score_eval.apply_human_review(automated, human)
        self.assertEqual("supported", result["verdict"])

    def test_human_review_template_includes_frozen_and_flagged_pairs(self):
        sample = {"pairs": [{"prompt_id": "direct-answer", "repetition": 2}]}
        qualitative = {
            "flagged_pairs": [{"prompt_id": "nuanced-risk", "repetition": 1}]
        }
        pairs = human_review.required_pairs(sample, qualitative)
        self.assertEqual(
            [
                {"prompt_id": "direct-answer", "repetition": 2},
                {"prompt_id": "nuanced-risk", "repetition": 1},
            ],
            pairs,
        )

    def test_human_review_is_bound_to_reviewed_judgment(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / "inputs").mkdir()
            (run_dir / "trials" / "sample-r1-1-control").mkdir(parents=True)
            (run_dir / "trials" / "sample-r1-2-ste").mkdir(parents=True)
            (run_dir / "judgments").mkdir()
            manifest = {
                "records": [
                    {"prompt_id": "sample", "repetition": 1, "arm": "control",
                     "trial_id": "sample-r1-1-control"},
                    {"prompt_id": "sample", "repetition": 1, "arm": "ste",
                     "trial_id": "sample-r1-2-ste"},
                ]
            }
            (run_dir / "manifest.json").write_text(json.dumps(manifest))
            (run_dir / "inputs" / "human-review-sample.json").write_text(
                json.dumps({"pairs": [{"prompt_id": "sample", "repetition": 1}]})
            )
            (run_dir / "deterministic-scores.json").write_text(
                json.dumps({"qualitative": {"flagged_pairs": []}})
            )
            for arm, position in (("control", 1), ("ste", 2)):
                (run_dir / "trials" / f"sample-r1-{position}-{arm}" / "stdout.jsonl").write_text(
                    json.dumps({"type": "result", "result": arm})
                )
                (run_dir / "trials" / f"sample-r1-{position}-{arm}" / "stdout.json").write_text(
                    json.dumps({"result": arm})
                )
            judgment_path = run_dir / "judgments" / "sample-r1.json"
            judgment_path.write_text(json.dumps({"judgment": self.valid_judgment()}))
            (run_dir / "judgments" / "sample-r1.stdout.txt").write_text("raw")
            review = human_review.build_template(run_dir)
            (run_dir / "human-review.json").write_text(json.dumps(review))
            judgment_path.write_text(json.dumps({"judgment": {"changed": True}}))
            with self.assertRaisesRegex(ValueError, "changed after human review"):
                human_review.validate(run_dir, {"flagged_pairs": []})

    def test_pass_cubed_is_a_primary_gate(self):
        records = []
        for prompt_index in range(10):
            for repetition in range(3):
                records.extend(
                    [
                        {"prompt_id": f"prompt-{prompt_index}", "opus_5_verified": True,
                         "requested_model": "opus", "requested_effort": "high"},
                        {"prompt_id": f"prompt-{prompt_index}", "opus_5_verified": True,
                         "requested_model": "opus", "requested_effort": "high"},
                    ]
                )
        manifest = {
            "status": "complete",
            "requested_model": "opus",
            "requested_effort": "high",
            "planned_trial_count": 60,
            "trial_count": 60,
            "errors": 0,
            "records": records,
        }
        qualitative = {
            "judged_pairs": 30,
            "judge_errors": 0,
            "ste_non_tied_win_rate": 1.0,
            "ste_minus_control": {
                "focus": 1,
                "jargon_discipline": 1,
                "task_completion": 0,
                "nuance_and_safety": 0,
            },
            "material_error_counts": {"ste": 0},
            "missing_requirement_counts": {"ste": 0},
            "ste_pass_cubed_by_prompt": {f"prompt-{index}": index != 0 for index in range(10)},
        }
        result = score_eval.acceptance(manifest, {}, qualitative)
        self.assertFalse(result["primary_gates"]["ste_pass_cubed_all_prompts"])
        self.assertEqual("refuted", result["automated_verdict"])

    @staticmethod
    def valid_judgment():
        score = {
            "task_completion": 5,
            "focus": 5,
            "plain_language": 5,
            "jargon_discipline": 5,
            "nuance_and_safety": 5,
            "unnecessary_passages": [],
            "unexplained_jargon": [],
            "missing_requirements": [],
            "material_errors": [],
            "overall": "pass",
            "reason": "good",
        }
        return {
            "answer_a": dict(score),
            "answer_b": dict(score),
            "winner": "tie",
            "pair_reason": "equal",
        }


if __name__ == "__main__":
    unittest.main()
