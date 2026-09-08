from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-7-2026-08-09"
BAKEOFF6 = ROOT / "campaigns" / "clause-bakeoff-6-2026-08-06"
PRIOR_CAMPAIGNS = (
    ROOT / "campaigns" / "clause-bakeoff-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-3-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-4-2026-08-05",
    ROOT / "campaigns" / "clause-bakeoff-5-2026-08-05",
    BAKEOFF6,
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


provider = load_module("bakeoff7_provider", CAMPAIGN / "provider.py")
tests_module = load_module("bakeoff7_tests", CAMPAIGN / "tests.py")
sys.modules["provider"] = provider
analyze = load_module("bakeoff7_analyze", CAMPAIGN / "analyze.py")


def valid_judgment() -> dict:
    score = {
        "task_completion": 4, "focus": 4, "plain_language": 4,
        "jargon_discipline": 4, "nuance_and_safety": 4,
        "material_errors": [], "missing_requirements": [],
        "invented_precision": [],
        "overall": "pass", "reason": "fine",
    }
    return {
        "answers": {label: dict(score) for label in analyze.LABELS},
        "pairwise": {key: "tie" for key in analyze.PAIR_KEYS},
        "overall_best": "tie",
        "reason": "all similar",
    }


class Bakeoff7ArtifactTests(unittest.TestCase):
    def test_baseline_variant_is_byte_identical_to_bakeoff_6_winner(self):
        self.assertEqual(
            (BAKEOFF6 / "variants" / "guarded-subtractive-v2.md").read_bytes(),
            (CAMPAIGN / "variants" / "guarded-subtractive-v2.md").read_bytes(),
        )

    def test_candidate_is_v2_plus_one_numbers_section(self):
        v2 = (CAMPAIGN / "variants" / "guarded-subtractive-v2.md").read_text()
        plus = (CAMPAIGN / "variants" / "v2-plus-numbers.md").read_text()
        self.assertTrue(plus.startswith(v2))
        addition = plus[len(v2):]
        self.assertIn("## Numbers", addition)
        self.assertIn("Do not present a number you assumed or estimated", addition)
        self.assertNotIn("##", addition.replace("## Numbers", ""))

    def test_battery_has_five_new_tasks_with_no_tools_line(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        self.assertEqual(5, len(tasks))
        self.assertEqual(5, len({item["id"] for item in tasks}))
        self.assertTrue(all(len(item["must_cover"]) >= 4 for item in tasks))
        for item in tasks:
            self.assertIn("do not inspect files or use tools", item["prompt"].lower())
        prior_prompts = {
            json.loads(line)["prompt"]
            for source in PRIOR_CAMPAIGNS
            for line in (source / "tasks.jsonl").read_text().splitlines()
        }
        self.assertFalse({item["prompt"] for item in tasks} & prior_prompts)

    def test_battery_has_derivable_control_task(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        derivable = [item for item in tasks if item["category"] == "derivable-numbers"]
        self.assertEqual(1, len(derivable))
        self.assertTrue(any("60 GB" in line for line in derivable[0]["must_cover"]))
        tempting = [item for item in tasks if item["category"].startswith("invention-tempting")]
        self.assertEqual(4, len(tempting))

    def test_provider_arms_match_variant_files(self):
        self.assertEqual(provider.ARMS, set(provider.VARIANT_FILES))
        self.assertEqual({"v2-only", "v2-plus-numbers"}, provider.ARMS)
        self.assertTrue(all(provider.VARIANT_FILES.values()))

    def test_two_arm_labels_and_baseline(self):
        self.assertEqual(("A", "B"), analyze.LABELS)
        self.assertEqual(("A_vs_B",), analyze.PAIR_KEYS)
        self.assertEqual("v2-only", analyze.BASELINE)
        self.assertIn(analyze.BASELINE, analyze.ARMS)
        for index in range(6):
            labels = analyze.label_order(index)
            self.assertEqual(set(analyze.ARMS), set(labels.values()))


class Bakeoff7InstrumentTests(unittest.TestCase):
    def test_schema_requires_invented_precision(self):
        self.assertIn("invented_precision", analyze.SCORE_SCHEMA["properties"])
        self.assertIn("invented_precision", analyze.SCORE_SCHEMA["required"])
        codex = analyze.codex_schema()
        for label in analyze.LABELS:
            self.assertIn(
                "invented_precision",
                codex["properties"]["answers"]["properties"][label]["properties"],
            )

    def test_validate_judgment_requires_invented_precision(self):
        analyze.validate_judgment(valid_judgment())
        bad = valid_judgment()
        del bad["answers"]["A"]["invented_precision"]
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)
        bad = valid_judgment()
        bad["answers"]["B"]["invented_precision"] = [3]
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)

    def test_judge_prompt_defines_invented_precision_and_hides_arms(self):
        task = analyze.tasks()[0]
        labels = analyze.label_order(0)
        answers = {arm: f"answer from {arm}" for arm in analyze.ARMS}
        prompt = analyze.judge_prompt(task, labels, answers)
        self.assertIn("invented_precision", prompt)
        self.assertIn("explicit assumption", prompt)
        preamble = prompt.split("<answer-a>")[0]
        self.assertNotIn("v2-plus-numbers", preamble)
        self.assertNotIn("v2-only", preamble)

    def test_novel_numerals_counts_only_new_tokens(self):
        prompt = "The queue held about 40,000 messages at 2 GB per day."
        self.assertEqual(0, analyze.novel_numerals("Check the 40,000 messages.", prompt))
        self.assertEqual(2, analyze.novel_numerals(
            "You have roughly 3 hours before the 500 GB volume fills.", prompt
        ))

    def test_preflight_v2_rules_hold(self):
        filler = "This sentence pads the response with realistic technical words. " * 15
        self.assertEqual("stalled", analyze.preflight("Too short."))
        self.assertEqual("stalled", analyze.preflight(filler + '\n<invoke name="Bash">'))
        self.assertEqual("answered", analyze.preflight(filler))


class Bakeoff7RuleTests(unittest.TestCase):
    def test_error_status_rule_unchanged(self):
        self.assertEqual("confirmed", analyze.error_status({"sonnet": ["a"], "codex": ["b"]}))
        self.assertEqual("disputed", analyze.error_status({"codex": ["b"]}))
        self.assertEqual("clean", analyze.error_status({}))

    def test_gate_keys_are_baseline_relative(self):
        source = (CAMPAIGN / "analyze.py").read_text()
        for key in (
            "omissions_not_above_baseline",
            "invented_precision_not_above_baseline",
            "median_words_within_110pct_of_baseline",
            "stalls_not_above_baseline",
        ):
            self.assertIn(key, source)
        self.assertIn('1.10 * control_median_words', source)

    def test_adjudication_applies_to_confirmed_findings(self):
        source = (CAMPAIGN / "analyze.py").read_text()
        self.assertIn('if status in ("disputed", "confirmed"):', source)


if __name__ == "__main__":
    unittest.main()
