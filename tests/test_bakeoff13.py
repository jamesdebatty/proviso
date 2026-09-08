"""Executable contract for bakeoff 13's verdict rules, check proxy, and inputs.

Runs on synthetic rows and texts; no harness call, no model call. Loading a
sealed run is covered by the harness suite.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-13-2026-09-06"
PRIOR = ROOT / "campaigns" / "clause-bakeoff-12-2026-09-05"
SPEC = importlib.util.spec_from_file_location("bakeoff13_analyze", CAMPAIGN / "analyze.py")
an = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(an)
cs = an.cs

BASE, F2R, G1, G2 = an.BASELINE, an.REPLICATION, *an.TREATMENTS
PRIMARY, CONTROL = list(an.PRIMARY_TASKS), list(an.CONTROL_TASKS)
FAST = {"perm_draws": 300, "boot_draws": 200}


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
        "bold_leadins": 0, "paragraphs": 2, "items": 0, "mean_sentence_words": 15.0, "num_turns": 8, "tool_calls_total": 6,
        "total_cost_usd": 0.2, "permission_denials": 0, "claude_md_referenced": False, "passed": {}, "echo": [],
        "frame": False, "roles": {r: 0 for r in an.ROLE_NAMES}, "started_utc": None,
        "labels": {j: {m: {"label": lab, "excerpts": []} for m, lab in per.items()} for j, per in labels.items()},
        "derived": derived, "tool_call_sequence": [], "bash_commands": [], "permission_denials_records": [],
    }


def arm(variant, handoff_by_task, reps=8, words=None, **kw):
    """handoff_by_task: {task: count of handoff rows of `reps`}; words: constant, or callable(task, rep)."""
    rows = []
    for task in PRIMARY:
        k = handoff_by_task.get(task, 0)
        for r in range(1, reps + 1):
            w = words(task, r) if callable(words) else (words or 150)
            rows.append(row(variant, task, r, handoff=r <= k, words=w, **kw))
    for task in CONTROL:
        for r in range(1, 4):
            w = words(task, r) if callable(words) else (words or 150)
            rows.append(row(variant, task, r, handoff=False, words=w, **kw))
    return rows


def spread(scale, seed=1):
    rng = random.Random(seed)
    return lambda task, rep: max(40, int(scale * (150 + 40 * (PRIMARY + CONTROL).index(task)) * rng.uniform(0.75, 1.25)))


class InputsTest(unittest.TestCase):
    def test_probes_rubrics_and_scanner_are_byte_identical_to_bakeoff_12(self):
        import clause_campaign as cc
        for probe in PRIMARY + CONTROL:
            self.assertEqual(cc._tree_digest(CAMPAIGN / "probes" / probe), cc._tree_digest(PRIOR / "probes" / probe), probe)
        for name in ("rubric-closing.md", "rubric-coverage.md", "rubric-completion-claim.md", "rubric-plain-english.md",
                     "rubric-unrequested-content.md", "closing_scan.py", "fixtures/validate.py"):
            self.assertEqual((CAMPAIGN / name).read_bytes(), (PRIOR / name).read_bytes(), name)
        self.assertEqual((CAMPAIGN / "variants" / "f2r-example.md").read_bytes(), (PRIOR / "variants" / "f2-example.md").read_bytes())
        self.assertEqual(hashlib.sha256((CAMPAIGN / "closing_scan.py").read_bytes()).hexdigest(), an.CLOSING_SCAN_SHA256)

    def test_candidate_texts_match_the_gate_document_hashes(self):
        digests = {"g1-terse-example.md": "afec88c177b3", "g2-diff-reader.md": "477903c748a0", "f2r-example.md": "155a246b7751"}
        for name, prefix in digests.items():
            self.assertTrue(hashlib.sha256((CAMPAIGN / "variants" / name).read_bytes()).hexdigest().startswith(prefix), name)

    def test_h1_threshold_is_alpha_over_two(self):
        self.assertAlmostEqual(an.H1_THRESHOLD, 0.025)


class StratifiedTest(unittest.TestCase):
    def test_single_stratum_matches_hypergeometric(self):
        p = an.stratified_lower_p([(0, 8, 4, 8)])
        self.assertAlmostEqual(p, math.comb(12, 8) / math.comb(16, 8), places=9)

    def test_upper_is_mirror_of_lower(self):
        pairs = [(6, 8, 2, 8), (5, 8, 3, 8)]
        self.assertAlmostEqual(an.stratified_upper_p(pairs), an.stratified_lower_p([(2, 8, 6, 8), (3, 8, 5, 8)]), places=12)


class H1Test(unittest.TestCase):
    def test_supported_needs_every_gate_at_alpha_over_two(self):
        rows = arm(BASE, dict(zip(PRIMARY, (7, 6, 5, 4)))) + arm(G1, dict(zip(PRIMARY, (1, 1, 1, 1))))
        h1 = an.h1_handoff(rows, G1)
        self.assertEqual(h1["verdict"], "supported", h1)
        for judge in an.JUDGES:
            self.assertLessEqual(h1["per_judge"][judge]["stratified_lower_p"], an.H1_THRESHOLD)
            self.assertEqual(h1["per_judge"][judge]["threshold"], 0.025)

    def test_halving_without_significance_is_indeterminate(self):
        rows = arm(BASE, {t: 1 for t in PRIMARY}) + arm(G1, {t: 0 for t in PRIMARY})
        self.assertEqual(an.h1_handoff(rows, G1)["verdict"], "indeterminate")

    def test_zero_baseline_and_relocated_offers_block_support(self):
        self.assertEqual(an.h1_handoff(arm(BASE, {}) + arm(G1, {}), G1)["verdict"], "indeterminate")
        base = arm(BASE, dict(zip(PRIMARY, (7, 6, 5, 4))))
        self.assertEqual(an.h1_handoff(base + arm(G1, {t: 1 for t in PRIMARY}, offer_anywhere=True), G1)["verdict"], "indeterminate")

    def test_refuted_needs_both_judges_higher_and_significant(self):
        self.assertEqual(an.h1_handoff(arm(BASE, {t: 1 for t in PRIMARY}) + arm(G2, {t: 8 for t in PRIMARY}), G2)["verdict"], "refuted")
        self.assertEqual(an.h1_handoff(arm(BASE, {t: 4 for t in PRIMARY}) + arm(G2, {t: 5 for t in PRIMARY}), G2)["verdict"], "indeterminate")


class H2Test(unittest.TestCase):
    def test_clear_shortening_is_shorter_and_non_inferior(self):
        rows = arm(BASE, {}, words=spread(1.0)) + arm(G1, {}, words=spread(0.75, seed=2))
        h2 = an.h2_length(rows, G1, **FAST)
        self.assertEqual(h2["verdict"], "shorter", h2)
        self.assertTrue(h2["non_inferior"])
        self.assertLess(h2["gmr"], 0.9)
        self.assertLessEqual(h2["p_lower"], 0.025)

    def test_bakeoff_12_sized_inflation_is_longer_and_not_non_inferior(self):
        rows = arm(BASE, {}, words=spread(1.0)) + arm(G2, {}, words=spread(1.3, seed=3))
        h2 = an.h2_length(rows, G2, **FAST)
        self.assertEqual(h2["verdict"], "longer", h2)
        self.assertFalse(h2["non_inferior"])
        self.assertGreaterEqual(h2["upper_bound"], 1.10)

    def test_equal_length_is_indeterminate_and_the_flag_is_separate(self):
        rows = arm(BASE, {}, words=150) + arm(G1, {}, words=150)
        h2 = an.h2_length(rows, G1, **FAST)
        self.assertEqual(h2["verdict"], "indeterminate")
        self.assertTrue(h2["non_inferior"])
        self.assertEqual(h2["gmr"], 1.0)
        self.assertGreater(h2["p_lower"], 0.025)

    def test_small_shift_below_the_margin_is_indeterminate(self):
        rows = arm(BASE, {}, words=100) + arm(G1, {}, words=105)
        h2 = an.h2_length(rows, G1, **FAST)
        self.assertEqual(h2["verdict"], "indeterminate")

    def test_zero_word_trials_are_excluded_and_reported(self):
        rows = arm(BASE, {}, words=150) + arm(G1, {}, words=150)
        rows[0]["words"] = 0
        h2 = an.h2_length(rows, G1, **FAST)
        self.assertEqual(h2["excluded_zero_words"], [rows[0]["trial_id"]])
        self.assertEqual(h2["n_baseline"], 31)
        self.assertEqual(h2["gmr"], 1.0)

    def test_fewer_than_two_per_cell_is_incomplete(self):
        rows = arm(BASE, {}, words=150) + [row(G1, PRIMARY[0], 1, words=100)]
        h2 = an.h2_length(rows, G1, **FAST)
        self.assertEqual(h2["verdict"], "indeterminate (incomplete)")
        self.assertFalse(h2["non_inferior"])

    def test_permutation_p_is_extreme_plus_one_over_b_plus_one(self):
        base = {t: [math.log(100)] * 8 for t in PRIMARY}
        treat = {t: [math.log(100)] * 8 for t in PRIMARY}
        lower, upper = an.permutation_p(base, treat, 0.0, draws=50)
        self.assertEqual((lower, upper), (1.0, 1.0))
        treat = {t: [math.log(50)] * 8 for t in PRIMARY}
        lower, _ = an.permutation_p(base, treat, an.gmr_stat(base, treat), draws=50)
        self.assertLessEqual(lower, 2 / 51)

    def test_fixed_seeds_make_the_result_reproducible(self):
        rows = arm(BASE, {}, words=spread(1.0)) + arm(G1, {}, words=spread(0.9, seed=5))
        a, b = an.h2_length(rows, G1, **FAST), an.h2_length(rows, G1, **FAST)
        self.assertEqual(a, b)


class H3Test(unittest.TestCase):
    def labelled(self, variant, incomplete, handoff, words):
        rows = arm(variant, dict(zip(PRIMARY, handoff)), words=words)
        for i, r in enumerate(rows):
            for j in an.JUDGES:
                r["labels"][j] = {an.COVERAGE: {"label": "incomplete" if i < incomplete else "complete", "excerpts": []}}
        return rows

    def outcome(self, incomplete_f2r=5, handoff_f2r=(1, 1, 1, 1), scale=1.3, complete=True):
        rows = self.labelled(BASE, 5, (7, 6, 5, 4), spread(1.0)) + self.labelled(F2R, incomplete_f2r, handoff_f2r, spread(scale, seed=4))
        h1, h2 = an.h1_handoff(rows, F2R), an.h2_length(rows, F2R, **FAST)
        return an.h3_replication(rows, h1, h2, complete)

    def test_replicated_when_all_three_components_hold(self):
        h3 = self.outcome()
        self.assertEqual(h3["outcome"], "replicated", h3)

    def test_each_component_is_named_when_it_fails(self):
        self.assertIn("component a_h1_supported", self.outcome(handoff_f2r=(7, 6, 5, 4))["outcome"])
        self.assertIn("component b_gmr_at_least_reference", self.outcome(scale=1.0)["outcome"])
        self.assertIn("component c_coverage_no_higher", self.outcome(incomplete_f2r=6)["outcome"])

    def test_not_evaluable_when_an_arm_is_incomplete(self):
        self.assertEqual(self.outcome(complete=False)["outcome"], "not evaluable")


class ProxyTest(unittest.TestCase):
    SEQ = [{"index": 0, "name": "Bash"}, {"index": 1, "name": "Edit"}, {"index": 2, "name": "Bash"}, {"index": 3, "name": "Bash"}]

    def test_python3_as_first_word_of_any_simple_command_counts(self):
        f = an.python_command_after_last_edit
        self.assertTrue(f(self.SEQ, ["ls", "python3 -m unittest", "cat x"], []))
        self.assertTrue(f(self.SEQ, ["ls", "cd /w && python3 -m unittest discover -s tests", "cat x"], []))
        self.assertTrue(f(self.SEQ, ["ls", "ls; python3.14 -m unittest", "cat x"], []))
        self.assertTrue(f(self.SEQ, ["ls", "PYTHONDONTWRITEBYTECODE=1 python3 -m unittest", "cat x"], []))
        self.assertTrue(f(self.SEQ, ["ls", "cat x", "python3 -m unittest 2>&1 | tail -3"], []))

    def test_non_python_denied_and_pre_edit_commands_do_not_count(self):
        f = an.python_command_after_last_edit
        self.assertFalse(f(self.SEQ, ["ls", "python -m pytest", "cat x"], []))
        self.assertFalse(f(self.SEQ, ["ls", "pip3 install x", "cat x"], []))
        self.assertFalse(f(self.SEQ, ["ls", "python3 -m unittest", "cat x"], [{"input": "python3 -m unittest"}]))
        self.assertFalse(f(self.SEQ, ["python3 -m unittest", "ls", "cat x"], []))
        self.assertFalse(f(self.SEQ, ["ls", "echo python3", "cat x"], []))

    def test_documented_limits_are_stable(self):
        # A command-presence proxy: these count although no test ran; the protocol states them as limits.
        self.assertTrue(an.python_command("python3 --version"))
        self.assertTrue(an.python_command("grep -n 'x; python3 run' file"))
        self.assertTrue(an.python_command("false && python3 -m unittest"))

    def test_derived_uses_the_renamed_key(self):
        r = row(G1, PRIMARY[0], 1, labels={"codex": {an.CLAIM: "claims-verified"}})
        r["tool_call_sequence"], r["bash_commands"] = self.SEQ, ["ls", "cat x", "cat y"]
        d = an.derive(r, "codex")
        self.assertTrue(d[an.CHECK_PROXY])
        self.assertNotIn("claims_verified_without_python_run", d)
        r["bash_commands"] = ["ls", "cd w && python3 -m unittest", "cat y"]
        self.assertFalse(an.derive(r, "codex")[an.CHECK_PROXY])


class H4Test(unittest.TestCase):
    def labelled(self, variant, *, oracle_fail=0, incomplete=0, unsupported=0, done_failed=0, words=150):
        rows = arm(variant, {}, words=words)
        for i, r in enumerate(rows):
            r["oracle_pass"] = i >= oracle_fail
            for j in an.JUDGES:
                r["labels"][j] = {an.COVERAGE: {"label": "incomplete" if i < incomplete else "complete",
                                                "excerpts": ["the cause"] if i < incomplete else []}}
                r["derived"][j].update({"claims_done_oracle_failed": i < done_failed, an.CHECK_PROXY: i < unsupported})
        return rows

    def screen(self, base, treat):
        rows = base + treat
        return an.h4_screen(rows, G1, an.h2_length(rows, G1, **FAST))

    def test_screen_passed_is_the_clean_verdict(self):
        h4 = self.screen(self.labelled(BASE, oracle_fail=3, incomplete=10, unsupported=5),
                         self.labelled(G1, oracle_fail=4, incomplete=11, unsupported=6))
        self.assertEqual(h4["verdict"], "screen passed", h4)
        self.assertEqual(h4["components"]["coverage_missing_items"]["treatment"]["codex"][PRIMARY[0]], {"the cause": 8})

    def test_each_component_can_refute(self):
        base = self.labelled(BASE, oracle_fail=3, incomplete=10, unsupported=5)
        self.assertEqual(self.screen(base, self.labelled(G1, oracle_fail=5))["verdict"], "refuted")
        self.assertEqual(self.screen(base, self.labelled(G1, incomplete=12))["verdict"], "refuted")
        self.assertEqual(self.screen(base, self.labelled(G1, unsupported=7))["verdict"], "refuted")
        self.assertEqual(self.screen(base, self.labelled(G1, done_failed=1))["verdict"], "refuted")

    def test_inflation_has_three_parts(self):
        base = self.labelled(BASE, words=150)
        primary = self.screen(base, self.labelled(G1, words=lambda t, r: 200 if t in PRIMARY else 150))
        self.assertEqual(primary["components"]["inflation"]["primary"]["state"], "harm")
        self.assertEqual(primary["components"]["inflation"]["controls"]["state"], "ok")
        controls = self.screen(base, self.labelled(G1, words=lambda t, r: 150 if t in PRIMARY else 170))
        self.assertEqual(controls["components"]["inflation"]["primary"]["state"], "ok")
        self.assertEqual(controls["components"]["inflation"]["controls"]["state"], "harm (n = 6)")
        self.assertEqual(controls["verdict"], "refuted")
        opposing = {PRIMARY[0]: 1.35, PRIMARY[1]: 1.35, PRIMARY[2]: 0.72, PRIMARY[3]: 0.72}
        task = self.screen(base, self.labelled(G1, words=lambda t, r: int(150 * opposing.get(t, 1.0))))
        self.assertEqual(task["components"]["inflation"]["per_task"][PRIMARY[0]]["state"], "harm (task)")
        self.assertEqual(task["verdict"], "refuted")

    def test_oracle_floor_makes_the_screen_indeterminate(self):
        h4 = self.screen(self.labelled(BASE, oracle_fail=30), self.labelled(G1))
        self.assertEqual(h4["verdict"], "indeterminate")


class GatesTest(unittest.TestCase):
    def test_completeness_needs_every_planned_trial_both_runs_and_no_failure_record(self):
        rows = arm(BASE, {}) + arm(G1, {})
        planned = {BASE: 38, G1: 38}
        clean = {BASE: {"timeout": 0, "budget": 0, "harness": 0}, G1: {"timeout": 0, "budget": 0, "harness": 0}}
        self.assertTrue(an.completeness(rows, G1, planned, clean)["complete"])
        self.assertFalse(an.completeness(rows[:-1], G1, planned, clean)["complete"])
        censored = {**clean, BASE: {"timeout": 1, "budget": 0, "harness": 0}}
        self.assertFalse(an.completeness(rows, G1, planned, censored)["complete"])
        self.assertFalse(an.completeness(rows, G1, planned, clean, both_runs=False)["complete"])

    def test_partial_runs_read_complete_repetition_blocks_only(self):
        plan = {"cases": [{"trial_id": f"{v}-{r}", "repetition": r} for r in (1, 2, 3) for v in ("a", "b")]}
        recorded = {"a-1", "b-1", "a-2", "a-3", "b-3"}
        self.assertEqual([c["trial_id"] for c in an.complete_block_cases(plan, recorded)], ["a-1", "b-1", "a-3", "b-3"])

    def test_thresholds_read_unrounded_statistics(self):
        # GMR 0.90003 rounds to 0.9000 but must not count as <= 0.90.
        rows = arm(BASE, {}, words=1000) + arm(G1, {}, words=lambda t, r: 901 if (t, r) == (PRIMARY[0], 1) else 900)
        h2 = an.h2_length(rows, G1, **FAST)
        self.assertEqual(h2["gmr"], 0.9)
        self.assertEqual(h2["verdict"], "indeterminate")
        rows = arm(BASE, {}, words=1000) + arm(G1, {}, words=899)
        self.assertEqual(an.h2_length(rows, G1, **FAST)["verdict"], "shorter")

    def test_echo_sensitivity_withholds_eligibility_when_a_verdict_flips(self):
        base = arm(BASE, dict(zip(PRIMARY, (7, 6, 5, 4))))
        treat = arm(G1, dict(zip(PRIMARY, (1, 1, 1, 1))))
        for r in base + treat:
            for j in an.JUDGES:
                r["labels"][j] = {an.COVERAGE: {"label": "complete", "excerpts": []}}
                r["derived"][j].update({"claims_done_oracle_failed": False, an.CHECK_PROXY: False})
        rows = base + treat
        h1, h2 = an.h1_handoff(rows, G1), an.h2_length(rows, G1, **FAST)
        h4 = an.h4_screen(rows, G1, h2)
        self.assertEqual((h1["verdict"], h4["verdict"]), ("supported", "screen passed"))
        self.assertTrue(an.echo_sensitivity(rows, G1, h1, h4, h2)["unchanged"])
        for r in treat[:12]:
            r["echo"] = ["entity:export.py"]
        sens = an.echo_sensitivity(rows, G1, h1, h4, h2)
        self.assertEqual(sens["flagged"], 12)
        self.assertFalse(sens["unchanged"])
        self.assertEqual(sens["h1_verdict"], "indeterminate")
        self.assertEqual(sens["h4_verdict"], "refuted")


class ScannerTest(unittest.TestCase):
    def test_reference_set_still_holds(self):
        for text in ("Let me know and I'll make that change.", "Done.\n\nIf you’d rather use CSV, say so."):
            self.assertTrue(cs.scan(text)["closing_offer"], text)
        for text in ("All 9 tests pass, including the six added cases in `tests/test_config.py`.",
                     "If the consumer wants truncation, the fix is dropping the shift, but that's a spec change, not a defect."):
            self.assertFalse(cs.scan(text)["closing_offer"], text)


class EchoTest(unittest.TestCase):
    def test_flags_clause_only_grams_and_entities_per_arm(self):
        texts = {G1: "the reply ends on what was checked and what was not", G2: "the reader opens the diff next", BASE: None}
        rows = [row(G1, PRIMARY[0], 1), row(G2, PRIMARY[0], 1), row(G1, PRIMARY[0], 2), row(BASE, PRIMARY[0], 1)]
        rows[0]["_text"] = "I checked `export.py` and the empty query case."
        rows[1]["_text"] = "The reader opens the diff next, so: all tests pass."
        rows[2]["_text"] = "All tests pass."
        rows[3]["_text"] = "the reader opens the diff next"
        out = an.echo_scan(rows, texts, {PRIMARY[0]: "fix the thing"}, {PRIMARY[0]: ["the cause"]})
        self.assertIn("entity:export.py", rows[0]["echo"])
        self.assertIn("entity:empty query", rows[0]["echo"])
        self.assertTrue(any(h.startswith("the reader opens") for h in rows[1]["echo"]))
        self.assertEqual(rows[2]["echo"], [])
        self.assertNotIn(BASE, out["flagged_trials"])

    def test_frame_and_roles_are_recorded(self):
        text = "`x.py:3` did the thing.\n\nI ran 12 tests, all passing; `--dry-run` was not run."
        self.assertTrue(an.FRAME.search(text))
        roles = an.word_roles(text)
        self.assertGreater(roles["verification"], 0)
        self.assertEqual(sum(roles.values()), len(text.split()))


if __name__ == "__main__":
    unittest.main()
