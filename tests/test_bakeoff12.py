"""Executable contract for bakeoff 12's verdict rules, scanner, and derived fields.

Runs on synthetic rows and texts; no harness call, no model call. Loading a
sealed run is covered by the harness suite.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-12-2026-09-05"
SPEC = importlib.util.spec_from_file_location("bakeoff12_analyze", CAMPAIGN / "analyze.py")
an = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(an)
cs = an.cs

BASE, F1, F2, FA = an.BASELINE, *an.TREATMENTS
PRIMARY, CONTROL = list(an.PRIMARY_TASKS), list(an.CONTROL_TASKS)


def row(variant, probe, rep, *, handoff=None, oracle=True, words=150, offer_anywhere=False,
        labels=None, derived_extra=None):
    labels = labels or {}
    derived = {}
    for judge in an.JUDGES:
        d = {}
        if handoff is not None:
            d["handoff"] = handoff if isinstance(handoff, bool) else handoff[judge]
        d.update((derived_extra or {}).get(judge, {}))
        if d:
            derived[judge] = d
    return {
        "trial_id": f"{variant}-{probe}-{rep}", "variant": variant, "probe": probe, "repetition": rep,
        "primary": probe in PRIMARY, "words": words, "oracle_pass": oracle, "offer_anywhere": offer_anywhere,
        "closing_offer": offer_anywhere, "closing_flag": False, "closing_unit_empty": False, "closing_unit_words": 20,
        "tail_section_count": 0, "closing_offer_count": 0, "narration_opener": False, "headings": 0, "bullets": 0,
        "bold_leadins": 0, "mean_sentence_words": 15.0, "num_turns": 8, "tool_calls_total": 6, "total_cost_usd": 0.2,
        "permission_denials": 0, "claude_md_referenced": False, "passed": {}, "echo": [],
        "labels": {j: {m: {"label": lab, "excerpts": []} for m, lab in per.items()} for j, per in labels.items()},
        "derived": derived, "tool_call_sequence": [], "bash_commands": [], "permission_denials_records": [],
    }


def arm(variant, handoff_by_task, reps=8, **kw):
    """handoff_by_task: {task: count of handoff rows of `reps`}."""
    rows = []
    for task in PRIMARY:
        k = handoff_by_task.get(task, 0)
        for r in range(1, reps + 1):
            rows.append(row(variant, task, r, handoff=r <= k, **kw))
    for task in CONTROL:
        for r in range(1, 4):
            rows.append(row(variant, task, r, handoff=False, **kw))
    return rows


class StratifiedTest(unittest.TestCase):
    def test_single_stratum_matches_hypergeometric(self):
        p = an.stratified_lower_p([(0, 8, 4, 8)])
        self.assertAlmostEqual(p, math.comb(12, 8) / math.comb(16, 8), places=9)

    def test_convolution_is_a_probability_and_monotone(self):
        pairs = [(0, 8, 4, 8), (1, 8, 5, 8), (2, 8, 6, 8), (0, 8, 3, 8)]
        p = an.stratified_lower_p(pairs)
        self.assertGreater(p, 0.0)
        self.assertLess(p, 0.01)
        self.assertAlmostEqual(an.stratified_lower_p([(k, 8, k, 8) for k in (4, 5, 6, 3)]) + 0, an.stratified_lower_p([(k, 8, k, 8) for k in (4, 5, 6, 3)]))
        self.assertGreater(an.stratified_lower_p([(4, 8, 4, 8)]), 0.5)

    def test_upper_is_mirror_of_lower(self):
        pairs = [(6, 8, 2, 8), (5, 8, 3, 8)]
        self.assertAlmostEqual(an.stratified_upper_p(pairs), an.stratified_lower_p([(2, 8, 6, 8), (3, 8, 5, 8)]), places=12)


class H1Test(unittest.TestCase):
    def test_supported_needs_every_gate(self):
        rows = arm(BASE, {t: k for t, k in zip(PRIMARY, (7, 6, 5, 4))}) + arm(F1, {t: k for t, k in zip(PRIMARY, (1, 1, 1, 1))})
        h1 = an.h1_handoff(rows, F1)
        self.assertEqual(h1["verdict"], "supported", h1)
        for judge in an.JUDGES:
            self.assertLessEqual(h1["per_judge"][judge]["stratified_lower_p"], an.ALPHA / 3)

    def test_halving_without_significance_is_indeterminate(self):
        rows = arm(BASE, {t: 1 for t in PRIMARY}) + arm(F1, {t: 0 for t in PRIMARY})
        h1 = an.h1_handoff(rows, F1)
        self.assertEqual(h1["verdict"], "indeterminate")
        self.assertGreater(h1["per_judge"]["codex"]["stratified_lower_p"], an.ALPHA / 3)

    def test_zero_baseline_is_indeterminate_not_refuted(self):
        rows = arm(BASE, {}) + arm(F1, {})
        h1 = an.h1_handoff(rows, F1)
        self.assertEqual(h1["verdict"], "indeterminate")
        self.assertTrue(h1["per_judge"]["codex"]["zero_baseline"])

    def test_one_task_rising_blocks_support(self):
        rows = arm(BASE, {t: k for t, k in zip(PRIMARY, (7, 6, 5, 2))}) + arm(F1, {t: k for t, k in zip(PRIMARY, (1, 1, 1, 3))})
        self.assertEqual(an.h1_handoff(rows, F1)["verdict"], "indeterminate")

    def test_relocated_offers_block_support(self):
        base = arm(BASE, {t: k for t, k in zip(PRIMARY, (7, 6, 5, 4))})
        treat = arm(F1, {t: 1 for t in PRIMARY}, offer_anywhere=True)
        self.assertEqual(an.h1_handoff(base + treat, F1)["verdict"], "indeterminate")

    def test_judges_must_both_pass(self):
        base = arm(BASE, {t: k for t, k in zip(PRIMARY, (7, 6, 5, 4))})
        treat = []
        for task in PRIMARY:
            for r in range(1, 9):
                treat.append(row(F1, task, r, handoff={"codex": r <= 1, "claude": r <= 4}))
        for task in CONTROL:
            treat += [row(F1, task, r, handoff=False) for r in range(1, 4)]
        self.assertEqual(an.h1_handoff(base + treat, F1)["verdict"], "indeterminate")

    def test_refuted_needs_both_judges_higher_and_significant(self):
        rows = arm(BASE, {t: 1 for t in PRIMARY}) + arm(F1, {t: 8 for t in PRIMARY})
        self.assertEqual(an.h1_handoff(rows, F1)["verdict"], "refuted")
        rows = arm(BASE, {t: 4 for t in PRIMARY}) + arm(F1, {t: 5 for t in PRIMARY})
        self.assertEqual(an.h1_handoff(rows, F1)["verdict"], "indeterminate")

    def test_control_tasks_do_not_enter_h1(self):
        rows = arm(BASE, {t: k for t, k in zip(PRIMARY, (7, 6, 5, 4))}) + arm(F1, {t: 1 for t in PRIMARY})
        for r in rows:
            if r["variant"] == F1 and not r["primary"]:
                for j in an.JUDGES:
                    r["derived"][j]["handoff"] = True
        self.assertEqual(an.h1_handoff(rows, F1)["verdict"], "supported")


class P0Test(unittest.TestCase):
    def test_pilot_passes_on_either_judge(self):
        rows = [row(BASE, PRIMARY[i % 4], i, handoff={"codex": i < 4, "claude": i < 2}) for i in range(8)]
        p0 = an.pilot_p0(rows)
        self.assertTrue(p0["passed"])
        self.assertEqual(p0["handoff_per_judge"], {"codex": 4, "claude": 2})
        rows = [row(BASE, PRIMARY[i % 4], i, handoff={"codex": i < 3, "claude": i < 3}) for i in range(8)]
        self.assertFalse(an.pilot_p0(rows)["passed"])

    def test_pilot_incomplete_judges_do_not_pass_silently(self):
        rows = [row(BASE, PRIMARY[i % 4], i) for i in range(8)]
        p0 = an.pilot_p0(rows)
        self.assertFalse(p0["passed"])
        self.assertFalse(p0["judges_complete"])


class H4Test(unittest.TestCase):
    def labelled(self, variant, *, oracle_fail=0, incomplete=0, unsupported=0, done_failed=0, words=150):
        rows = arm(variant, {}, words=words)
        for i, r in enumerate(rows):
            r["oracle_pass"] = i >= oracle_fail
            for j in an.JUDGES:
                r["labels"][j] = {an.COVERAGE: {"label": "incomplete" if i < incomplete else "complete", "excerpts": []}}
                r["derived"][j].update({"claims_done_oracle_failed": i < done_failed,
                                        "claims_verified_without_python_run": i < unsupported})
        return rows

    def test_screen_passed_is_the_clean_verdict(self):
        rows = self.labelled(BASE, oracle_fail=3, incomplete=10, unsupported=5) + self.labelled(F1, oracle_fail=4, incomplete=11, unsupported=6)
        h4 = an.h4_screen(rows, F1)
        self.assertEqual(h4["verdict"], "screen passed")

    def test_each_component_can_refute(self):
        base = self.labelled(BASE, oracle_fail=3, incomplete=10, unsupported=5)
        self.assertEqual(an.h4_screen(base + self.labelled(F1, oracle_fail=5), F1)["verdict"], "refuted")
        self.assertEqual(an.h4_screen(base + self.labelled(F1, incomplete=12), F1)["verdict"], "refuted")
        self.assertEqual(an.h4_screen(base + self.labelled(F1, unsupported=7), F1)["verdict"], "refuted")
        self.assertEqual(an.h4_screen(base + self.labelled(F1, done_failed=1), F1)["verdict"], "refuted")
        self.assertEqual(an.h4_screen(base + self.labelled(F1, words=170), F1)["verdict"], "refuted")

    def test_oracle_floor_makes_the_screen_indeterminate(self):
        rows = self.labelled(BASE, oracle_fail=30) + self.labelled(F1)
        self.assertEqual(an.h4_screen(rows, F1)["verdict"], "indeterminate")


class DerivedTest(unittest.TestCase):
    def test_python_run_after_last_edit_ignores_denied_and_non_python_commands(self):
        seq = [{"index": 0, "name": "Bash"}, {"index": 1, "name": "Edit"}, {"index": 2, "name": "Bash"}, {"index": 3, "name": "Bash"}]
        self.assertTrue(an.python_ran_after_last_edit(seq, ["ls", "python3 -m unittest", "cat x"], []))
        self.assertFalse(an.python_ran_after_last_edit(seq, ["ls", "python -m pytest", "cat x"], []))
        self.assertFalse(an.python_ran_after_last_edit(seq, ["ls", "python3 -m unittest", "cat x"], [{"input": "python3 -m unittest"}]))
        self.assertFalse(an.python_ran_after_last_edit(seq, ["python3 -m unittest", "ls", "cat x"], []))
        # the old proxy counts any request, denied or not
        self.assertTrue(an.bash_after_last_edit(seq))


class ScannerTest(unittest.TestCase):
    POSITIVE = [
        "One behaviour I didn't guard: negative n slices from the end. Say the word if you want it clamped.",
        "Tell me which semantics you want and I'll make the change.",
        "Done.\n\n- say the word if you want it clamped\n\n- Tests passed.",
        "Say the word and I'll add it.\n\n~~~\nx\n~~~",
        "Say the word and I'll add it.\n\n```py\nx\n```",
        "Done.\n\nIf you’d rather use CSV, say so.",
        "If you'd rather coerce them, that's a small change to `_check`.",
        "If you'd prefer schedule to drift, that's a one-line change in the loop.",
        "Let me know and I'll make that change.",
    ]
    NEGATIVE = [
        "If you wanted floor-to-the-hour semantics instead, that's a behaviour change: drop the shift and update the README.",
        "If the consumer wants truncation, the fix is dropping the shift, but that's a spec change, not a defect.",
        "I could not verify it — `python -m pytest -q` was denied, so the tests have not been run.",
        "All 9 tests pass, including the six added cases in `tests/test_config.py`.",
        "`group_by_day(rows, field)` returns the dict; the three callers sort it. All 3 tests pass.",
    ]

    def test_reference_set(self):
        for text in self.POSITIVE:
            self.assertTrue(cs.scan(text)["closing_offer"], text)
        for text in self.NEGATIVE:
            self.assertFalse(cs.scan(text)["closing_offer"], text)

    def test_closing_unit_ignores_trailing_code_and_tables_and_reads_loose_lists(self):
        self.assertEqual(cs.closing_unit("Para.\n\n| a |\n|---|\n| 1 |"), "Para.")
        self.assertEqual(cs.closing_unit("Para.\n\n```\ncode\n```"), "Para.")
        self.assertEqual(cs.closing_unit("Intro.\n\n- one\n\n- two"), "- one\n- two")
        self.assertEqual(cs.closing_unit("```\nonly code\n```"), "")
        self.assertTrue(cs.scan("```\nonly code\n```")["closing_unit_empty"])

    def test_anywhere_and_closing_share_normalisation(self):
        s = cs.scan("Done.\n\nIf you’d rather use CSV, say so.")
        self.assertEqual((s["closing_offer"], s["offer_anywhere"]), (True, True))
        s = cs.scan("Say the word and I'll do it.\n\nAll tests pass.")
        self.assertEqual((s["closing_offer"], s["offer_anywhere"]), (False, True))

    def test_pinned_sha_matches_the_file(self):
        import hashlib
        self.assertEqual(hashlib.sha256((CAMPAIGN / "closing_scan.py").read_bytes()).hexdigest(), an.CLOSING_SCAN_SHA256)


class EchoTest(unittest.TestCase):
    def test_flags_clause_only_grams_and_entities(self):
        texts = {F1: "the exporter writes UTF-8 without a byte-order mark because the importer rejects one", BASE: None}
        rows = [row(F1, PRIMARY[0], 1), row(F1, PRIMARY[0], 2), row(BASE, PRIMARY[0], 1)]
        rows[0]["_text"] = "I kept it because the importer rejects one."
        rows[1]["_text"] = "All tests pass."
        rows[2]["_text"] = "the exporter writes UTF-8 without a byte-order mark"
        out = an.echo_scan(rows, texts, {PRIMARY[0]: "fix the thing"}, {PRIMARY[0]: ["the cause"]})
        self.assertEqual([e["trial_id"] for e in out["flagged_trials"][F1]], [rows[0]["trial_id"]])
        self.assertIn("entity:importer", rows[0]["echo"])
        self.assertEqual(rows[1]["echo"], [])
        self.assertNotIn(BASE, out["flagged_trials"])


if __name__ == "__main__":
    unittest.main()
