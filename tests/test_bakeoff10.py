"""Executable contract for bakeoff 10's verdict rules, on a synthetic run.

The run is the campaign's own offline declaration; judge records are written
directly in the sealed shape `clause_judge.py` produces, so every rule in
`analyze.py` is exercised without a model call.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-10-2026-09-01"
SPEC = importlib.util.spec_from_file_location("bakeoff10_analyze", CAMPAIGN / "analyze.py")
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


def write_judgments(run_dir: Path, judge_root: Path, judge: str, label_for) -> None:
    plan = cc._read_canonical(run_dir / "plan.json", "plan")
    trials = cc._load_trials(run_dir, plan)
    out = judge_root / judge
    out.mkdir(parents=True, exist_ok=True)
    for trial in trials:
        for measure in plan["measures"]:
            if measure["kind"] != "judgmental":
                continue
            binding = {
                "trial_sha256": trial["trial_sha256"],
                "output_sha256": trial["output"]["sha256"],
                "measure_id": measure["id"],
                "rubric_sha256": measure["rubric_sha256"],
            }
            task_id = cc._digest(binding)
            record = cc._seal({
                "schema": "clause-judgment/1",
                "task_id": task_id,
                "task_sha256": "0" * 64,
                "measure_id": measure["id"],
                "judge": judge,
                "judgment": {"label": label_for(trial, measure["id"]), "excerpts": [], "reason": "t"},
            }, "record_sha256")
            (out / f"{task_id}.json").write_bytes(cc._pretty(record))


class Verdicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.temporary.name) / "run"
        cc.ClauseCampaign.load(CAMPAIGN / "campaign-synthetic.toml").exercise(cls.run_dir)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def labels(self, present_a1: int, present_d1: int, incomplete_d2: int = 0):
        counters = {}

        def label_for(trial, measure):
            key = (trial["variant_id"], measure)
            index = counters.get(key, 0)
            counters[key] = index + 1
            if measure == "mannered-prose":
                budget = {"a1-response-numbers": present_a1, "d1-density-long": present_d1}.get(trial["variant_id"], 0)
                return "present" if index < budget else "none"
            budget = {"d2-density-short": incomplete_d2}.get(trial["variant_id"], 0)
            return "incomplete" if index < budget else "complete"
        return label_for

    def test_density_rules_read_the_retained_observations(self):
        with tempfile.TemporaryDirectory() as judge_root:
            result = analyze.analyze(self.run_dir, Path(judge_root))
        self.assertEqual(result["arms"]["a1-response-numbers"]["n"], 25)
        self.assertEqual(result["arms"]["a1-response-numbers"]["tasks"], 5)
        h1 = result["H1_d1_density"]
        self.assertEqual(h1["verdict"], "supported")
        self.assertEqual(h1["detail"]["mean_sentence_words"]["tasks_lower"], 5)
        self.assertGreaterEqual(h1["detail"]["mean_paragraph_words"]["relative_fall"], 0.10)
        # D2's placeholder keeps one long paragraph: it fails the declared split on
        # every trial, while the arm contrast (a relative fall) still reads.
        self.assertEqual(result["arms"]["d2-density-short"]["pass_counts"]["paragraph-length"], 0)
        self.assertIn(result["H2_d2_density"]["verdict"], {"supported", "indeterminate", "refuted"})
        self.assertLess(result["H2_d2_density"]["detail"]["mean_paragraph_words"]["relative_fall"],
                        h1["detail"]["mean_paragraph_words"]["relative_fall"])
        self.assertEqual(result["H3_mannered_prose"]["verdict"], "indeterminate")
        self.assertEqual(result["H3_mannered_prose"]["reason"], "judge results incomplete")
        self.assertEqual(result["H4_no_harm"]["d1-density-long"]["verdict"], "indeterminate")

    def test_mannered_prose_power_check_fires_before_any_comparison(self):
        with tempfile.TemporaryDirectory() as judge_root:
            root = Path(judge_root)
            for judge in ("codex", "claude"):
                write_judgments(self.run_dir, root, judge, self.labels(present_a1=3, present_d1=0))
            result = analyze.analyze(self.run_dir, root)
        self.assertEqual(result["H3_mannered_prose"]["verdict"], "indeterminate (underpowered)")
        self.assertEqual(result["judge_coverage"]["codex"], {"records": 150, "expected": 150})

    def test_mannered_prose_supported_only_when_both_judges_see_a_fall(self):
        with tempfile.TemporaryDirectory() as judge_root:
            root = Path(judge_root)
            write_judgments(self.run_dir, root, "codex", self.labels(present_a1=20, present_d1=4))
            write_judgments(self.run_dir, root, "claude", self.labels(present_a1=12, present_d1=12))
            split = analyze.analyze(self.run_dir, root)["H3_mannered_prose"]
            self.assertEqual(split["verdict"], "indeterminate")
            self.assertEqual(split["judges_lower_for_d1"], ["codex"])
            write_judgments(self.run_dir, root, "claude", self.labels(present_a1=12, present_d1=2))
            # records are immutable: rewrite into a fresh root instead
        with tempfile.TemporaryDirectory() as judge_root:
            root = Path(judge_root)
            write_judgments(self.run_dir, root, "codex", self.labels(present_a1=20, present_d1=4))
            write_judgments(self.run_dir, root, "claude", self.labels(present_a1=12, present_d1=2))
            result = analyze.analyze(self.run_dir, root)
        self.assertEqual(result["H3_mannered_prose"]["verdict"], "supported")
        self.assertEqual(result["judge_agreement"]["coverage"]["exact_agreement"], 1.0)

    def test_harm_reads_words_and_coverage_per_treatment(self):
        with tempfile.TemporaryDirectory() as judge_root:
            root = Path(judge_root)
            for judge in ("codex", "claude"):
                write_judgments(self.run_dir, root, judge, self.labels(present_a1=6, present_d1=1, incomplete_d2=3))
            result = analyze.analyze(self.run_dir, root)
        harm = result["H4_no_harm"]
        self.assertEqual(harm["d1-density-long"]["verdict"], "supported")
        self.assertEqual(harm["d2-density-short"]["verdict"], "refuted")
        self.assertFalse(harm["d2-density-short"]["coverage"]["codex"]["ok"])
        self.assertTrue(harm["d1-density-long"]["words"]["ok"])


if __name__ == "__main__":
    unittest.main()
