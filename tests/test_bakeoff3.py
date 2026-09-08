from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-3-2026-08-05"
PRIOR_CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-2026-08-05"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


provider = load_module("bakeoff3_provider", CAMPAIGN / "provider.py")
tests_module = load_module("bakeoff3_tests", CAMPAIGN / "tests.py")
sys.modules["provider"] = provider
analyze = load_module("bakeoff3_analyze", CAMPAIGN / "analyze.py")


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


class Bakeoff3ArtifactTests(unittest.TestCase):
    def test_complete_recipe_is_byte_identical_to_bakeoff_2(self):
        self.assertEqual(
            (PRIOR_CAMPAIGN / "variants" / "complete-recipe.md").read_bytes(),
            (CAMPAIGN / "variants" / "complete-recipe.md").read_bytes(),
        )

    def test_battery_has_five_new_complete_tasks(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        self.assertEqual(5, len(tasks))
        self.assertEqual(5, len({item["id"] for item in tasks}))
        self.assertTrue(all(len(item["must_cover"]) >= 4 for item in tasks))
        prior_prompts = {
            json.loads(line)["prompt"]
            for line in (PRIOR_CAMPAIGN / "tasks.jsonl").read_text().splitlines()
        }
        self.assertFalse({item["prompt"] for item in tasks} & prior_prompts)

    def test_analyzer_tasks_validate(self):
        self.assertEqual(5, len(analyze.tasks()))

    def test_promptfoo_test_generation_matches_tasks(self):
        generated = tests_module.generate_tests()
        self.assertEqual(5, len(generated))
        for entry in generated:
            self.assertIn("task_id", entry["vars"])
            self.assertTrue(json.loads(entry["vars"]["must_cover"]))

    def test_provider_arms_match_variant_files(self):
        self.assertEqual(provider.ARMS, set(provider.VARIANT_FILES))
        self.assertEqual(
            {"control", "positive-recipe", "complete-recipe"}, provider.ARMS
        )
        self.assertIsNone(provider.VARIANT_FILES["control"])


class Bakeoff3LabelTests(unittest.TestCase):
    def test_label_rotation_is_deterministic_and_covers_arms(self):
        for index in range(9):
            labels = analyze.label_order(index)
            self.assertEqual(set(analyze.LABELS), set(labels))
            self.assertEqual(set(analyze.ARMS), set(labels.values()))
        first = {arm: [] for arm in analyze.ARMS}
        for index in range(6):
            first[analyze.label_order(index)["A"]].append(index)
        self.assertTrue(all(len(indices) == 2 for indices in first.values()))

    def test_pairwise_result_maps_labels(self):
        pairwise = {"A_vs_B": "A", "A_vs_C": "tie", "B_vs_C": "C"}
        self.assertEqual("candidate", analyze.pairwise_result(pairwise, "A", "B"))
        self.assertEqual("control", analyze.pairwise_result(pairwise, "B", "A"))
        self.assertEqual("tie", analyze.pairwise_result(pairwise, "C", "A"))


class Bakeoff3PreflightTests(unittest.TestCase):
    def test_short_response_is_stalled(self):
        self.assertEqual("stalled", analyze.preflight("I will check the project."))

    def test_final_paragraph_inspection_intent_is_stalled(self):
        filler = "This is a real sentence about the system with plenty of words. " * 10
        text = filler + "\n\nLet me look at the project files to understand the setup."
        self.assertEqual("stalled", analyze.preflight(text))

    def test_mid_answer_inspection_phrase_is_answered(self):
        text = (
            "I need to look at the repository normally, but here is the answer.\n\n"
            + "Check the cache layer first because stale nodes explain intermittent "
            "old behavior. Verify each instance's build endpoint and compare versions. "
            "Then invalidate the CDN and confirm the asset hashes match the release. "
            "Finally restart any instance that still reports the old build number."
        )
        self.assertEqual("answered", analyze.preflight(text))

    def test_normal_answer_is_answered(self):
        text = (
            "Rotate the credential in stages. Create the new secret, validate it on "
            "one instance, roll it out gradually while monitoring failures, and keep "
            "the old secret available for rollback until validation completes. Only "
            "revoke the old credential after every instance uses the new one."
        )
        self.assertEqual("answered", analyze.preflight(text))


class Bakeoff3SchemaTests(unittest.TestCase):
    def test_codex_schema_inlines_refs_and_keeps_bounds(self):
        schema = analyze.codex_schema()
        encoded = json.dumps(schema)
        self.assertNotIn("$ref", encoded)
        self.assertNotIn("$defs", encoded)
        self.assertIn("minimum", encoded)
        self.assertIn("maximum", encoded)
        for label in analyze.LABELS:
            self.assertIn(
                "material_errors",
                schema["properties"]["answers"]["properties"][label]["properties"],
            )

    def test_schema_hash_is_stable(self):
        self.assertEqual(
            analyze.schema_sha256(analyze.codex_schema()),
            analyze.schema_sha256(analyze.codex_schema()),
        )

    def test_validate_judgment_accepts_valid_and_rejects_invalid(self):
        analyze.validate_judgment(valid_judgment())
        bad = valid_judgment()
        bad["answers"]["A"]["focus"] = 6
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)
        bad = valid_judgment()
        bad["pairwise"]["A_vs_B"] = "C"
        with self.assertRaises(ValueError):
            analyze.validate_judgment(bad)


class Bakeoff3CodexParsingTests(unittest.TestCase):
    def events(self, texts: list[str], completed: bool = True) -> str:
        lines = ['{"type":"thread.started","thread_id":"t1"}', '{"type":"turn.started"}']
        for index, text in enumerate(texts):
            item = {"id": f"item_{index}", "type": "agent_message", "text": text}
            lines.append(json.dumps({"type": "item.completed", "item": item}))
        if completed:
            lines.append('{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}')
        return "\n".join(lines)

    def test_parses_single_agent_message(self):
        raw = self.events([json.dumps(valid_judgment())])
        parsed = analyze.parse_codex_events(raw)
        self.assertEqual(valid_judgment(), parsed["judgment"])

    def test_rejects_multiple_agent_messages(self):
        raw = self.events([json.dumps(valid_judgment()), json.dumps(valid_judgment())])
        with self.assertRaises(ValueError):
            analyze.parse_codex_events(raw)

    def test_rejects_incomplete_turn(self):
        raw = self.events([json.dumps(valid_judgment())], completed=False)
        with self.assertRaises(ValueError):
            analyze.parse_codex_events(raw)

    def test_rollout_model_extraction(self):
        rollout = "\n".join([
            json.dumps({"type": "session_meta", "payload": {"id": "x"}}),
            json.dumps({"type": "turn_context", "payload": {"turn_id": "t", "model": "gpt-5.6-sol"}}),
        ])
        self.assertEqual("gpt-5.6-sol", analyze.codex_rollout_model(rollout))
        conflicting = rollout + "\n" + json.dumps(
            {"type": "turn_context", "payload": {"turn_id": "u", "model": "other"}}
        )
        with self.assertRaises(ValueError):
            analyze.codex_rollout_model(conflicting)
        with self.assertRaises(ValueError):
            analyze.codex_rollout_model(json.dumps({"type": "session_meta", "payload": {}}))


class Bakeoff3ErrorRuleTests(unittest.TestCase):
    def test_error_status_rule(self):
        self.assertEqual("confirmed", analyze.error_status({"sonnet": ["a"], "codex": ["b"]}))
        self.assertEqual("disputed", analyze.error_status({"sonnet": ["a"]}))
        self.assertEqual("disputed", analyze.error_status({"codex": ["b"]}))
        self.assertEqual("clean", analyze.error_status({}))

    def test_judge_prompt_contains_labels_tasks_and_ideas(self):
        task = analyze.tasks()[0]
        labels = analyze.label_order(0)
        answers = {arm: f"answer from {arm}" for arm in analyze.ARMS}
        prompt = analyze.judge_prompt(task, labels, answers)
        for label in analyze.LABELS:
            self.assertIn(f"ANSWER {label}:", prompt)
        for idea in task["must_cover"]:
            self.assertIn(idea, prompt)
        for arm in ("positive-recipe", "complete-recipe"):
            self.assertNotIn(arm, prompt.split("<answer-a>")[0])


if __name__ == "__main__":
    unittest.main()
