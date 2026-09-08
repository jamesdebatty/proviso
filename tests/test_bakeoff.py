from __future__ import annotations

import importlib.util
import json
from unittest import mock
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-2026-08-05"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


provider = load_module("bakeoff_provider", CAMPAIGN / "provider.py")
tests_module = load_module("bakeoff_tests", CAMPAIGN / "tests.py")
sys.modules["provider"] = provider
analyze = load_module("bakeoff_analyze", CAMPAIGN / "analyze.py")


class BakeoffTests(unittest.TestCase):
    def test_original_ste_variant_content_is_exact(self):
        self.assertEqual(
            (ROOT / "treatment" / "CLAUDE.md").read_text().rstrip("\n"),
            (CAMPAIGN / "variants" / "ste.md").read_text().rstrip("\n"),
        )

    def test_battery_has_three_new_complete_tasks(self):
        tasks = [json.loads(line) for line in (CAMPAIGN / "tasks.jsonl").read_text().splitlines()]
        self.assertEqual(3, len(tasks))
        self.assertEqual(3, len({item["id"] for item in tasks}))
        self.assertTrue(all(len(item["must_cover"]) >= 4 for item in tasks))
        generated = tests_module.generate_tests()
        self.assertEqual([item["id"] for item in tasks], [item["description"] for item in generated])

    def test_artifact_path_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            previous = os.environ.get("BAKEOFF_OUT_DIR")
            os.environ["BAKEOFF_OUT_DIR"] = temp
            try:
                with self.assertRaises(ValueError):
                    provider.artifact_dir("../../private", 1, "control")
                with self.assertRaises(ValueError):
                    provider.artifact_dir("safe", 1, "outside")
            finally:
                if previous is None:
                    os.environ.pop("BAKEOFF_OUT_DIR", None)
                else:
                    os.environ["BAKEOFF_OUT_DIR"] = previous

    def test_control_is_empty_and_variants_are_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.assertIsNone(provider.materialize(base / "control", None))
            digest = provider.materialize(base / "recipe", "variants/complete-recipe.md")
            self.assertIsNotNone(digest)
            self.assertEqual([], list((base / "control").iterdir()))
            self.assertEqual(["CLAUDE.md"], [item.name for item in (base / "recipe").iterdir()])

    def test_blind_label_rotation_is_balanced(self):
        orders = [analyze.label_order(index) for index in range(4)]
        for arm in provider.ARMS:
            self.assertEqual(set(analyze.LABELS), {next(k for k, v in item.items() if v == arm) for item in orders})

    def test_judgment_rejects_pairwise_winner_outside_pair(self):
        score = {
            "task_completion": 5, "focus": 5, "plain_language": 5,
            "jargon_discipline": 5, "nuance_and_safety": 5,
            "material_errors": [], "missing_requirements": [],
            "overall": "pass", "reason": "good",
        }
        item = {
            "answers": {label: dict(score) for label in analyze.LABELS},
            "pairwise": {
                "A_vs_B": "C", "A_vs_C": "A", "A_vs_D": "A",
                "B_vs_C": "B", "B_vs_D": "B", "C_vs_D": "C",
            },
            "overall_best": "A", "reason": "test",
        }
        with self.assertRaises(ValueError):
            analyze.validate_judgment(item)

    def test_response_cache_rejects_changed_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            expected = {
                "task_id": "safe", "repetition": 1, "arm": "control",
                "claude_version": "test", "requested_model": "opus",
                "requested_effort": "high", "clause_sha256": None,
                "prompt_sha256": "new",
            }
            (path / "meta.json").write_text(json.dumps({**expected, "prompt_sha256": "old"}))
            (path / "response.json").write_text("{}")
            (path / "stdout.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "prompt_sha256"):
                provider.load_cached(path, expected)

    def test_task_loader_rejects_unsafe_id(self):
        # Point the loader at a temp campaign rather than rewriting the real
        # tasks.jsonl: the previous version mutated a git-tracked artifact and
        # restored it in a finally, which made concurrent test runs look flaky
        # and would have left a single "../escape" record behind if the process
        # died mid-test.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tasks.jsonl").write_text(
                json.dumps({"id": "../escape", "prompt": "x", "must_cover": ["x"]}) + "\n"
            )
            with mock.patch.object(analyze, "CAMPAIGN", Path(tmp)):
                with self.assertRaises(ValueError):
                    analyze.tasks()


if __name__ == "__main__":
    unittest.main()
