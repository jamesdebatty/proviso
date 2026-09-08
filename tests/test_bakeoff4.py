from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-4-2026-08-05"
BAKEOFF3 = ROOT / "campaigns" / "clause-bakeoff-3-2026-08-05"
BAKEOFF2 = ROOT / "campaigns" / "clause-bakeoff-2026-08-05"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


provider = load_module("bakeoff4_provider", CAMPAIGN / "provider.py")
tests_module = load_module("bakeoff4_tests", CAMPAIGN / "tests.py")
sys.modules["provider"] = provider
analyze = load_module("bakeoff4_analyze", CAMPAIGN / "analyze.py")


def valid_judgment() -> dict:
    score = {
        "task_completion": 4, "focus": 4, "plain_language": 4,
        "jargon_discipline": 4, "nuance_and_safety": 4,
        "material_errors": [], "missing_requirements": [],
        "overall": "pass", "reason": "fine",
    }
    return {
        "answers": {label: dict(score) for label in analyze.LABELS},
        "pairwise": {key: "tie" for key in analyze.PAIR_KEYS},
        "overall_best": "tie",
        "reason": "all similar",
    }


class Bakeoff4ArtifactTests(unittest.TestCase):
    def test_positive_recipe_is_byte_identical_to_bakeoff_3(self):
        self.assertEqual(
            (BAKEOFF3 / "variants" / "positive-recipe.md").read_bytes(),
            (CAMPAIGN / "variants" / "positive-recipe.md").read_bytes(),
        )

    def test_battery_has_five_new_complete_tasks_with_no_tools_line(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        self.assertEqual(5, len(tasks))
        self.assertEqual(5, len({item["id"] for item in tasks}))
        self.assertTrue(all(len(item["must_cover"]) >= 4 for item in tasks))
        for item in tasks:
            self.assertIn(
                "do not inspect files or use tools", item["prompt"].lower()
            )
        prior_prompts = {
            json.loads(line)["prompt"]
            for source in (BAKEOFF2, BAKEOFF3)
            for line in (source / "tasks.jsonl").read_text().splitlines()
        }
        self.assertFalse({item["prompt"] for item in tasks} & prior_prompts)

    def test_provider_arms_match_variant_files(self):
        self.assertEqual(provider.ARMS, set(provider.VARIANT_FILES))
        self.assertEqual(
            {"control", "positive-recipe", "budgeted-recipe", "structured-recipe"},
            provider.ARMS,
        )
        self.assertIsNone(provider.VARIANT_FILES["control"])

    def test_four_arm_labels_and_pairwise_keys(self):
        self.assertEqual(("A", "B", "C", "D"), analyze.LABELS)
        self.assertEqual(6, len(analyze.PAIR_KEYS))
        for index in range(8):
            labels = analyze.label_order(index)
            self.assertEqual(set(analyze.ARMS), set(labels.values()))


class Bakeoff4PreflightTests(unittest.TestCase):
    FILLER = "This sentence pads the response with realistic technical words. " * 15

    def test_v1_rules_still_hold(self):
        self.assertEqual("stalled", analyze.preflight("Too short."))
        text = self.FILLER + "\n\nLet me look at the project files first."
        self.assertEqual("stalled", analyze.preflight(text))
        self.assertEqual("answered", analyze.preflight(self.FILLER))

    def test_fake_invoke_transcript_is_stalled(self):
        text = self.FILLER + '\n<invoke name="Bash">\n<parameter name="command">ls -la</parameter>'
        self.assertEqual("stalled", analyze.preflight(text))

    def test_tool_header_transcript_is_stalled(self):
        text = self.FILLER + "\n**Tool: Bash**\n```\ncommand: ls -la\n```"
        self.assertEqual("stalled", analyze.preflight(text))

    def test_fake_directory_listing_is_stalled(self):
        text = self.FILLER + "\ntotal 0\ndrwxr-xr-x@ 2 user staff 64 Aug 5 20:35 ."
        self.assertEqual("stalled", analyze.preflight(text))

    def test_legitimate_technical_answer_is_answered(self):
        text = (
            "Run the rule in log-only mode first and count violations. Total "
            "rejections should be zero at this stage. Notify affected clients "
            "with a deadline, enforce by segment while monitoring, and keep a "
            "kill switch so a bad rollout can be reverted in seconds without a "
            "deploy. Do not enable enforcement for all traffic at once."
        )
        self.assertEqual("answered", analyze.preflight(text))


class Bakeoff4RuleTests(unittest.TestCase):
    def test_error_status_rule(self):
        self.assertEqual("confirmed", analyze.error_status({"sonnet": ["a"], "codex": ["b"]}))
        self.assertEqual("disputed", analyze.error_status({"codex": ["b"]}))
        self.assertEqual("clean", analyze.error_status({}))

    def test_codex_schema_inlines_refs_and_keeps_bounds(self):
        schema = analyze.codex_schema()
        encoded = json.dumps(schema)
        self.assertNotIn("$ref", encoded)
        self.assertNotIn("$defs", encoded)
        self.assertIn("minimum", encoded)
        for label in analyze.LABELS:
            self.assertIn(
                "material_errors",
                schema["properties"]["answers"]["properties"][label]["properties"],
            )

    def test_validate_judgment_round_trip(self):
        analyze.validate_judgment(valid_judgment())
        bad = valid_judgment()
        bad["pairwise"]["A_vs_D"] = "B"
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)

    def test_judge_prompt_contains_four_answers(self):
        task = analyze.tasks()[0]
        labels = analyze.label_order(0)
        answers = {arm: f"answer from {arm}" for arm in analyze.ARMS}
        prompt = analyze.judge_prompt(task, labels, answers)
        for label in analyze.LABELS:
            self.assertIn(f"ANSWER {label}:", prompt)
        self.assertIn("Grade four answers", prompt)
        for arm in ("positive-recipe", "budgeted-recipe", "structured-recipe"):
            self.assertNotIn(arm, prompt.split("<answer-a>")[0])


if __name__ == "__main__":
    unittest.main()
