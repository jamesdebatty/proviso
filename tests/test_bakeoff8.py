from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-8-2026-08-11"
BAKEOFF7 = ROOT / "campaigns" / "clause-bakeoff-7-2026-08-09"
PRIOR_CAMPAIGNS = (
    ROOT / "campaigns" / "clause-bakeoff-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-3-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-4-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-5-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-6-2026-08-06",
    BAKEOFF7,
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


provider = load_module("bakeoff8_provider", CAMPAIGN / "provider.py")
tests_module = load_module("bakeoff8_tests", CAMPAIGN / "tests.py")
sys.modules["provider"] = provider
analyze = load_module("bakeoff8_analyze", CAMPAIGN / "analyze.py")


def valid_judgment() -> dict:
    score = {
        "task_completion": 4, "focus": 4, "plain_language": 4,
        "jargon_discipline": 4, "nuance_and_safety": 4,
        "material_errors": [], "missing_requirements": [],
        "invented_precision": [], "undefined_coinage": [],
        "overall": "pass", "reason": "fine",
    }
    return {
        "answers": {label: dict(score) for label in analyze.LABELS},
        "pairwise": {key: "tie" for key in analyze.PAIR_KEYS},
        "overall_best": "tie",
        "reason": "all similar",
    }


class Bakeoff8ArtifactTests(unittest.TestCase):
    def test_composite_is_byte_identical_to_bakeoff_7_candidate(self):
        self.assertEqual(
            (BAKEOFF7 / "variants" / "v2-plus-numbers.md").read_bytes(),
            (CAMPAIGN / "variants" / "composite.md").read_bytes(),
        )

    def test_vocabulary_arm_is_composite_plus_one_section(self):
        base = (CAMPAIGN / "variants" / "composite.md").read_text()
        extended = (CAMPAIGN / "variants" / "composite-plus-vocabulary.md").read_text()
        self.assertTrue(extended.startswith(base))
        added = extended[len(base):]
        self.assertIn("## Vocabulary", added)
        self.assertEqual(1, added.count("## "))
        self.assertNotIn("## Vocabulary", base)

    def test_three_arms_with_blank_slate_baseline(self):
        self.assertEqual(
            {"control", "composite", "composite-plus-vocabulary"}, provider.ARMS
        )
        self.assertEqual(provider.ARMS, set(provider.VARIANT_FILES))
        self.assertIsNone(provider.VARIANT_FILES["control"])
        self.assertEqual("control", analyze.BASELINE)
        self.assertEqual(
            ("composite-plus-vocabulary", "composite"), analyze.SECONDARY_PAIR
        )
        self.assertEqual(("A", "B", "C"), analyze.LABELS)
        self.assertEqual(3, len(analyze.PAIR_KEYS))

    def test_battery_is_fresh_and_carries_no_tools_line(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        self.assertEqual(5, len(tasks))
        self.assertEqual(5, len({item["id"] for item in tasks}))
        self.assertTrue(all(len(item["must_cover"]) >= 4 for item in tasks))
        for item in tasks:
            self.assertIn("do not inspect files or use tools", item["prompt"].lower())
        prior = {
            json.loads(line)["prompt"]
            for source in PRIOR_CAMPAIGNS
            for line in (source / "tasks.jsonl").read_text().splitlines()
        }
        self.assertFalse({item["prompt"] for item in tasks} & prior)

    def test_battery_has_an_over_suppression_falsifier(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        falsifiers = [t for t in tasks if t["category"] == "established-vocabulary"]
        self.assertEqual(1, len(falsifiers))
        self.assertTrue(
            any("standard names" in item for item in falsifiers[0]["must_cover"])
        )

    def test_label_rotation_covers_all_arms(self):
        for index in range(9):
            labels = analyze.label_order(index)
            self.assertEqual(set(analyze.ARMS), set(labels.values()))
            self.assertEqual(set(analyze.LABELS), set(labels))

    def test_promptfoo_test_generation_matches_tasks(self):
        generated = tests_module.generate_tests()
        self.assertEqual(5, len(generated))
        for entry in generated:
            self.assertTrue(json.loads(entry["vars"]["must_cover"]))


class Bakeoff8CoinageDetectorTests(unittest.TestCase):
    PROMPT = "Explain how the write-ahead log and the retry policy interact."

    def test_reused_coined_phrase_is_counted(self):
        text = (
            'We call this the "shadow-write path" because it runs beside the main one. '
            'The "shadow-write path" then reconciles asynchronously.'
        )
        self.assertGreaterEqual(analyze.novel_coinages(text, self.PROMPT), 1)

    def test_terms_present_in_the_prompt_are_not_counted(self):
        text = "The write-ahead log records the change. The write-ahead log is durable."
        self.assertEqual(0, analyze.novel_coinages(text, self.PROMPT))

    def test_single_use_term_is_not_counted_as_a_handle(self):
        text = 'A so-called "quiet reconcile step" happens once and is never mentioned again.'
        self.assertEqual(0, analyze.novel_coinages(text, self.PROMPT))

    def test_detector_is_deterministic(self):
        text = 'The "fan-out collapse" recurs. The "fan-out collapse" recurs again.'
        self.assertEqual(
            analyze.novel_coinages(text, self.PROMPT),
            analyze.novel_coinages(text, self.PROMPT),
        )


class Bakeoff8SchemaAndRuleTests(unittest.TestCase):
    def test_schema_requires_undefined_coinage(self):
        self.assertIn("undefined_coinage", analyze.SCORE_SCHEMA["properties"])
        self.assertIn("undefined_coinage", analyze.SCORE_SCHEMA["required"])
        codex = analyze.codex_schema()
        encoded = json.dumps(codex)
        self.assertNotIn("$ref", encoded)
        for label in analyze.LABELS:
            self.assertIn(
                "undefined_coinage",
                codex["properties"]["answers"]["properties"][label]["properties"],
            )

    def test_validate_judgment_round_trip(self):
        analyze.validate_judgment(valid_judgment())
        bad = valid_judgment()
        del bad["answers"]["A"]["undefined_coinage"]
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)
        bad = valid_judgment()
        bad["answers"]["B"]["undefined_coinage"] = [5]
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)
        bad = valid_judgment()
        bad["pairwise"]["B_vs_C"] = "A"
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)

    def test_judge_prompt_defines_coinage_and_hides_arm_names(self):
        task = analyze.tasks()[0]
        labels = analyze.label_order(0)
        answers = {arm: f"answer from {arm}" for arm in analyze.ARMS}
        prompt = analyze.judge_prompt(task, labels, answers)
        self.assertIn("Grade three answers", prompt)
        self.assertIn("undefined_coinage", prompt)
        self.assertIn("terms of art", prompt)
        for label in analyze.LABELS:
            self.assertIn(f"ANSWER {label}:", prompt)
        header = prompt.split("<answer-a>")[0]
        for arm in ("composite", "composite-plus-vocabulary"):
            self.assertNotIn(arm, header)

    def test_error_status_rule_unchanged(self):
        self.assertEqual("confirmed", analyze.error_status({"sonnet": ["a"], "codex": ["b"]}))
        self.assertEqual("disputed", analyze.error_status({"codex": ["b"]}))
        self.assertEqual("clean", analyze.error_status({}))

    def test_preflight_v2_rules_hold(self):
        filler = "This sentence pads the response with realistic technical words. " * 15
        self.assertEqual("stalled", analyze.preflight("Too short."))
        self.assertEqual("stalled", analyze.preflight(filler + '\n<invoke name="Bash">'))
        self.assertEqual("answered", analyze.preflight(filler))


if __name__ == "__main__":
    unittest.main()
