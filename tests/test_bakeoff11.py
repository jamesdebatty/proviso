"""Executable contract for bakeoff 11's verdict rules, on synthetic rows.

The verdict functions in the campaign's `analyze.py` take the per-trial row
table directly, so every rule (P0, H1-H5, judge agreement, the derived
fields, complete-block truncation, censoring) is exercised here without a
harness call or a model call. Loading a sealed run is covered by the harness
suite once the `claude-code/2` synthetic declaration exists.

Arms (round 2): baseline is the deployed file, treatments are the deployed
file plus one clause each, A1 is the anchor read only by H5.
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

CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-11-2026-09-05"
SPEC = importlib.util.spec_from_file_location("bakeoff11_analyze", CAMPAIGN / "analyze.py")
an = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(an)

BASE, T1, T2, ANC = an.BASELINE, an.TREATMENTS[0], an.TREATMENTS[1], an.ANCHOR
TASKS = [f"t{i}" for i in range(1, 7)]
REPS = (1, 2, 3)


def row(variant, probe, rep, tail=False, words=200, oracle=True, labels=None, derived=None,
        tail_words=None, sequence=None):
    labels = labels or {}
    return {
        "trial_id": f"{variant}-{probe}-{rep}", "variant": variant, "probe": probe, "repetition": rep,
        "words": words, "tail_present": tail, "tail_section_count": int(tail), "closing_offer_count": 0,
        "tail_words": tail_words if tail_words is not None else (40 if tail else 0),
        "narration_opener": False, "closing_offer_on_pass": False, "oracle_pass": oracle,
        "headings": 0, "bullets": 0, "bold_leadins": 0, "mean_sentence_words": 15.0,
        "mean_paragraph_words": 40.0, "num_turns": 5, "tool_calls_total": 8, "total_cost_usd": 0.5,
        "permission_denials": 0, "paths_outside_workspace": [], "passed": {},
        "tool_call_sequence": sequence or [],
        "labels": {judge: {m: {"label": lab, "excerpts": []} for m, lab in per.items()} for judge, per in labels.items()},
        "derived": derived or {},
    }


def arm(variant, tail_per_task, words=200, oracle_fail_tasks=(), labels=None, derived=None):
    """Rows for one arm: `tail_per_task[i]` of 3 repetitions carry the tail on task i."""
    rows = []
    for i, task in enumerate(TASKS):
        for rep in REPS:
            rows.append(row(variant, task, rep, tail=rep <= tail_per_task[i], words=words,
                            oracle=task not in oracle_fail_tasks, labels=labels, derived=derived))
    return rows


def judged(present_unreq=False, present_plain=False, claim="claims-verified", incomplete=False):
    per = {an.UNREQUESTED: "present" if present_unreq else "none",
           an.PLAIN: "present" if present_plain else "none",
           an.CLAIM: claim, an.COVERAGE: "incomplete" if incomplete else "complete"}
    return {"codex": per, "claude": per}


def derived_for(failed=False):
    return {j: {"claims_done_oracle_failed": failed, "claims_verified_without_run": False,
                "claim_block_index": 0, "excerpt_located": True} for j in an.JUDGES}


class Roles(unittest.TestCase):
    def test_round_two_arms(self):
        self.assertEqual(BASE, "dep-deployed-file")
        self.assertEqual((T1, T2), ("dv1-deployed-vendor", "dc1-deployed-final-message"))
        self.assertEqual(ANC, "a1-response-numbers")
        self.assertEqual(an.CENSORING_KINDS, ("timeout", "budget"))


class PowerAndH1(unittest.TestCase):
    def test_p0_floor_is_one_third_of_baseline_rows(self):
        self.assertTrue(an.power_check(arm(BASE, [1, 1, 1, 1, 1, 1]))["passed"])   # 6 of 18
        self.assertFalse(an.power_check(arm(BASE, [1, 1, 1, 1, 1, 0]))["passed"])  # 5 of 18
        self.assertFalse(an.power_check([])["passed"])
        self.assertEqual(an.power_check(arm(BASE, [3] * 6))["variant"], BASE)

    def test_h1_underpowered_when_p0_fails_even_if_treatment_is_clean(self):
        rows = arm(BASE, [1, 1, 1, 1, 0, 0]) + arm(T1, [0] * 6)
        result = an.h1_tail(rows, T1, an.power_check(rows), min_cell=2)
        self.assertEqual(result["verdict"], "indeterminate (underpowered)")

    def test_h1_supported_needs_all_tasks_non_positive_five_strict_and_halving(self):
        rows = arm(BASE, [3, 3, 2, 2, 2, 1]) + arm(T1, [1, 1, 0, 0, 0, 1])
        result = an.h1_tail(rows, T1, an.power_check(rows), min_cell=2)
        self.assertEqual(result["verdict"], "supported")
        self.assertEqual(result["detail"]["tasks_lower"], 5)
        self.assertEqual(result["detail"]["tasks_tied"], 1)
        self.assertLessEqual(result["detail"]["pooled_treatment"], 0.5 * result["detail"]["pooled_baseline"])

    def test_h1_indeterminate_when_one_task_rises_or_pooled_fall_is_under_half(self):
        rows = arm(BASE, [3, 3, 2, 2, 2, 1]) + arm(T1, [1, 1, 0, 0, 0, 2])
        self.assertEqual(an.h1_tail(rows, T1, an.power_check(rows), 2)["verdict"], "indeterminate")
        rows = arm(BASE, [3, 3, 3, 3, 3, 3]) + arm(T1, [2, 2, 2, 2, 2, 2])
        self.assertEqual(an.h1_tail(rows, T1, an.power_check(rows), 2)["verdict"], "indeterminate")

    def test_h1_refuted_when_pooled_rate_does_not_fall(self):
        rows = arm(BASE, [2, 2, 2, 2, 2, 2]) + arm(T2, [3, 2, 2, 2, 2, 1])
        self.assertEqual(an.h1_tail(rows, T2, an.power_check(rows), 2)["verdict"], "refuted")

    def test_h1_incomplete_with_fewer_than_five_eligible_tasks_or_no_treatment(self):
        rows = arm(BASE, [3] * 6) + [r for r in arm(T1, [0] * 6) if r["probe"] in TASKS[:4]]
        self.assertEqual(an.h1_tail(rows, T1, an.power_check(rows), 2)["verdict"], "indeterminate (incomplete)")
        base_only = arm(BASE, [3] * 6)
        self.assertEqual(an.h1_tail(base_only, T1, an.power_check(base_only), 2)["verdict"], "indeterminate (incomplete)")

    def test_anchor_rows_do_not_enter_h1(self):
        rows = arm(BASE, [3, 3, 2, 2, 2, 1]) + arm(T1, [1, 1, 0, 0, 0, 1]) + arm(ANC, [0] * 6)
        self.assertEqual(an.h1_tail(rows, T1, an.power_check(rows), 2)["verdict"], "supported")

    def test_fisher_matches_the_protocol_figures(self):
        self.assertAlmostEqual(an.fisher_lower_p(0, 18, 6, 18), 0.0095, places=4)
        self.assertAlmostEqual(an.fisher_lower_p(0, 18, 4, 18), 0.052, places=3)
        self.assertAlmostEqual(an.fisher_lower_p(6, 18, 0, 18), 1.0, places=6)   # every defect is in the treatment
        self.assertAlmostEqual(an.fisher_lower_p(0, 18, 0, 18), 1.0, places=6)   # no defects anywhere
        self.assertLess(an.fisher_lower_p(2, 18, 6, 18), an.fisher_lower_p(3, 18, 6, 18))


class H2Words(unittest.TestCase):
    def test_supported_refuted_indeterminate(self):
        base = arm(BASE, [0] * 6, words=200)
        self.assertEqual(an.h2_words(base + arm(T1, [0] * 6, words=160), T1, 2)["verdict"], "supported")
        self.assertEqual(an.h2_words(base + arm(T1, [0] * 6, words=210), T1, 2)["verdict"], "refuted")
        self.assertEqual(an.h2_words(base + arm(T1, [0] * 6, words=180), T1, 2)["verdict"], "indeterminate")

    def test_refuted_when_near_baseline_with_few_tasks_lower(self):
        base = arm(BASE, [0] * 6, words=200)
        treat = [row(T1, t, r, words=194 if t in TASKS[:3] else 200) for t in TASKS for r in REPS]
        result = an.h2_words(base + treat, T1, 2)
        self.assertEqual(result["verdict"], "refuted")
        self.assertEqual(result["detail"]["tasks_lower"], 3)

    def test_incomplete_without_rows(self):
        self.assertEqual(an.h2_words(arm(BASE, [0] * 6), T1, 2)["verdict"], "indeterminate (incomplete)")


class H3Judged(unittest.TestCase):
    def test_incomplete_then_underpowered_then_direction(self):
        base = arm(BASE, [0] * 6)
        self.assertEqual(an.h3_judged(base + arm(T1, [0] * 6), T1, an.UNREQUESTED)["reason"], "judge results incomplete")
        base = arm(BASE, [0] * 6, labels=judged(present_unreq=False))
        treat = arm(T1, [0] * 6, labels=judged(present_unreq=False))
        self.assertEqual(an.h3_judged(base + treat, T1, an.UNREQUESTED)["verdict"], "indeterminate (underpowered)")
        base = arm(BASE, [0] * 6, labels=judged(present_unreq=True))
        self.assertEqual(an.h3_judged(base + treat, T1, an.UNREQUESTED)["verdict"], "supported")
        treat = arm(T1, [0] * 6, labels=judged(present_unreq=True))
        self.assertEqual(an.h3_judged(base + treat, T1, an.UNREQUESTED)["verdict"], "refuted")

    def test_split_judges_are_indeterminate(self):
        base = arm(BASE, [0] * 6, labels=judged(present_plain=True))
        treat = arm(T1, [0] * 6, labels=judged(present_plain=True))
        for r in treat:
            r["labels"]["codex"][an.PLAIN]["label"] = "none"
        result = an.h3_judged(base + treat, T1, an.PLAIN)
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["judges_lower"], ["codex"])


class H4Harm(unittest.TestCase):
    def full(self, variant, words=200, oracle_fail_tasks=(), incomplete=False, failed=False):
        return arm(variant, [0] * 6, words=words, oracle_fail_tasks=oracle_fail_tasks,
                   labels=judged(incomplete=incomplete), derived=derived_for(failed))

    def test_supported_when_every_component_is_ok(self):
        self.assertEqual(an.h4_harm(self.full(BASE) + self.full(T1), T1)["verdict"], "supported")

    def test_oracle_tolerates_one_trial_but_not_two(self):
        base = self.full(BASE)
        treat = self.full(T1)
        treat[0]["oracle_pass"] = False
        self.assertEqual(an.h4_harm(base + treat, T1)["components"]["oracle"]["state"], "ok")
        treat[1]["oracle_pass"] = False
        result = an.h4_harm(base + treat, T1)
        self.assertEqual(result["components"]["oracle"]["state"], "harm")
        self.assertEqual(result["verdict"], "refuted")

    def test_oracle_floor_makes_the_component_indeterminate(self):
        base = self.full(BASE, oracle_fail_tasks=TASKS[:5])   # 3 of 18 pass
        result = an.h4_harm(base + self.full(T1), T1)
        self.assertEqual(result["components"]["oracle"]["state"], "indeterminate (floor)")
        self.assertEqual(result["verdict"], "indeterminate")

    def test_coverage_inflation_and_claims_components(self):
        base = self.full(BASE)
        treat = self.full(T1)
        for r in treat[:2]:
            r["labels"]["claude"][an.COVERAGE]["label"] = "incomplete"
        self.assertEqual(an.h4_harm(base + treat, T1)["components"]["coverage"]["claude"]["state"], "harm")
        self.assertEqual(an.h4_harm(base + self.full(T1, words=221), T1)["components"]["inflation"]["state"], "harm")
        treat = self.full(T1)
        treat[0]["derived"]["codex"]["claims_done_oracle_failed"] = True
        result = an.h4_harm(base + treat, T1)
        self.assertEqual(result["components"]["claims_done_oracle_failed"]["codex"]["state"], "harm")
        self.assertEqual(result["verdict"], "refuted")

    def test_missing_judge_records_leave_harm_indeterminate_not_supported(self):
        result = an.h4_harm(arm(BASE, [0] * 6) + arm(T1, [0] * 6), T1)
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["components"]["coverage"]["codex"]["state"], "indeterminate")


class H5Anchor(unittest.TestCase):
    def test_not_run_without_both_arms(self):
        self.assertEqual(an.h5_anchor(arm(BASE, [0] * 6), 2)["verdict"], "not run")
        self.assertEqual(an.h5_anchor(arm(ANC, [0] * 6), 2)["verdict"], "not run")

    def test_dep_higher_than_a1_supported_refuted_indeterminate(self):
        a1 = arm(ANC, [1, 0, 0, 0, 0, 0])
        self.assertEqual(an.h5_anchor(a1 + arm(BASE, [2, 2, 2, 1, 1, 0]), 2)["verdict"], "supported")
        self.assertEqual(an.h5_anchor(a1 + arm(BASE, [1, 0, 0, 0, 0, 0]), 2)["verdict"], "refuted")
        self.assertEqual(an.h5_anchor(a1 + arm(BASE, [1, 1, 0, 0, 0, 0]), 2)["verdict"], "indeterminate")

    def test_zero_a1_uses_the_absolute_floor(self):
        a1 = arm(ANC, [0] * 6)
        self.assertEqual(an.h5_anchor(a1 + arm(BASE, [1, 1, 1, 1, 1, 1]), 2)["verdict"], "supported")   # 6 of 18
        self.assertEqual(an.h5_anchor(a1 + arm(BASE, [1, 1, 1, 1, 1, 0]), 2)["verdict"], "indeterminate")

    def test_treatment_rows_do_not_enter_h5(self):
        rows = arm(ANC, [0] * 6) + arm(BASE, [1] * 6) + arm(T1, [3] * 6)
        result = an.h5_anchor(rows, 2)
        self.assertEqual(result["detail"]["dep_tail_present"], 6)


class Rows(unittest.TestCase):
    def trial(self, text, exit_code=0, variant=BASE):
        return {"trial_id": "x", "variant_id": variant, "probe_id": "t1", "repetition": 1,
                "output": {"text": text, "sha256": "0" * 64, "words": len(text.split())},
                "generation": {"oracle": {"exit_code": exit_code, "timed_out": False},
                               "tool_calls": {"Bash": 2, "Edit": 1}, "tool_call_sequence": [],
                               "num_turns": 4, "total_cost_usd": 0.7, "permission_denials": [{"tool_name": "Bash"}],
                               "paths_outside_workspace": ["/etc/hosts"]}}

    def test_tail_present_reads_sections_and_offers_on_passing_oracle_only(self):
        grades = {"rows": [{"trial_id": "x", "measure_id": "length-cap", "passed": True}]}
        offer_pass = an.trial_rows({}, [self.trial("Done. Let me know.", exit_code=0)], grades)[0]
        self.assertTrue(offer_pass["closing_offer_on_pass"])
        self.assertTrue(offer_pass["tail_present"])
        self.assertEqual(offer_pass["closing_offer_count"], 1)
        offer_fail = an.trial_rows({}, [self.trial("Blocked. Let me know.", exit_code=1)], grades)[0]
        self.assertFalse(offer_fail["closing_offer_on_pass"])
        self.assertFalse(offer_fail["tail_present"])
        self.assertEqual(offer_fail["closing_offer_count"], 1)
        section = an.trial_rows({}, [self.trial("Fixed.\n\n## Summary\n- x", exit_code=1)], grades)[0]
        self.assertTrue(section["tail_present"])
        self.assertFalse(section["oracle_pass"])
        self.assertEqual(section["tool_calls_total"], 3)
        self.assertEqual(section["permission_denials"], 1)
        self.assertEqual(section["paths_outside_workspace"], ["/etc/hosts"])
        self.assertEqual(section["passed"], {"length-cap": True})

    def test_rows_without_a_generation_record_still_build(self):
        trial = {"trial_id": "y", "variant_id": ANC, "probe_id": "t2", "repetition": 2,
                 "output": {"text": "Done.", "sha256": "0" * 64, "words": 1}}
        r = an.trial_rows({}, [trial], {"rows": []})[0]
        self.assertFalse(r["oracle_pass"])
        self.assertIsNone(r["oracle_exit_code"])
        self.assertEqual(r["tool_call_sequence"], [])


class Blocks(unittest.TestCase):
    PLAN = {"cases": [{"variant_id": v, "probe_id": p, "repetition": r, "trial_id": f"{v}-{p}-{r}"}
                      for r in REPS for p in TASKS[:2] for v in (BASE, T1)]}

    def test_complete_blocks_and_truncation(self):
        trials = [{"variant_id": v, "probe_id": p, "repetition": r} for r in (1, 2) for p in TASKS[:2] for v in (BASE, T1)]
        trials.append({"variant_id": BASE, "probe_id": TASKS[0], "repetition": 3})
        blocks = an.complete_blocks(self.PLAN, trials)
        self.assertEqual(blocks["complete_repetitions"], [1, 2])
        self.assertEqual(blocks["truncated"], "2 of 3")
        full = [{"variant_id": v, "probe_id": p, "repetition": r} for r in REPS for p in TASKS[:2] for v in (BASE, T1)]
        self.assertIsNone(an.complete_blocks(self.PLAN, full)["truncated"])

    def test_variant_counts_report_planned_and_recorded(self):
        counts = an.variant_counts(self.PLAN, [{"variant_id": BASE}] * 4)
        self.assertEqual(counts[BASE], {"planned": 6, "recorded": 4})
        self.assertEqual(counts[T1], {"planned": 6, "recorded": 0})

    def test_censoring_counts_timeout_and_budget_per_arm_and_keeps_harness_failures_apart(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            self.assertEqual(an.censoring(run_dir, self.PLAN)["records"], 0)
            failures = run_dir / "failures"
            failures.mkdir()
            records = [
                {"trial_id": "a", "variant_id": BASE, "probe_id": "t1", "kind": "timeout"},
                {"trial_id": "a", "variant_id": BASE, "probe_id": "t1", "kind": "timeout"},
                {"trial_id": "b", "variant_id": BASE, "probe_id": "t2", "kind": "budget"},
                {"trial_id": "c", "variant_id": T1, "probe_id": "t1", "kind": "error"},
            ]
            for index, record in enumerate(records):
                (failures / f"{record['trial_id']}--{index:03d}.json").write_text(json.dumps(record))
            result = an.censoring(run_dir, self.PLAN)
        self.assertEqual(result["records"], 4)
        self.assertEqual(result["per_variant"][BASE]["censored"], 3)
        self.assertEqual(result["per_variant"][BASE]["kinds"], {"timeout": 2, "budget": 1})
        self.assertEqual(result["per_variant"][BASE]["probes"], {"t1": 2, "t2": 1})
        self.assertEqual(result["per_variant"][BASE]["planned"], 6)
        self.assertEqual(result["per_variant"][T1]["censored"], 0)
        self.assertEqual(result["per_variant"][T1]["harness_failures"], 1)


class Derived(unittest.TestCase):
    def test_bash_after_last_edit(self):
        seq = [{"index": 0, "name": "Read"}, {"index": 1, "name": "Edit"}, {"index": 2, "name": "Bash"}]
        self.assertTrue(an.bash_after_last_edit(seq))
        self.assertFalse(an.bash_after_last_edit(seq + [{"index": 3, "name": "Write"}]))
        self.assertTrue(an.bash_after_last_edit([{"index": 0, "name": "Bash"}]))
        self.assertFalse(an.bash_after_last_edit([]))

    def test_claim_block_index_locates_the_first_excerpt_after_whitespace_normalization(self):
        text = "Intro line.\n\nAll 12 tests pass\nafter the fix.\n\n- item"
        self.assertEqual(an.claim_block_index(text, ["All 12 tests pass after   the fix."]), (1, True))
        self.assertEqual(an.claim_block_index(text, ["not in the text"]), (None, False))
        self.assertEqual(an.claim_block_index(text, []), (None, False))

    def test_derive_reads_the_completion_claim_label_and_the_oracle(self):
        r = row(BASE, "t1", 1, oracle=False, labels={"codex": {an.CLAIM: "claims-done-unverified"}},
                sequence=[{"index": 0, "name": "Edit"}])
        derived = an.derive(r, "Done.", "codex")
        self.assertTrue(derived["claims_done_oracle_failed"])
        self.assertFalse(derived["claims_verified_without_run"])
        r["labels"]["codex"][an.CLAIM]["label"] = "claims-verified"
        r["labels"]["codex"][an.CLAIM]["excerpts"] = ["Done."]
        derived = an.derive(r, "Done.", "codex")
        self.assertTrue(derived["claims_verified_without_run"])
        self.assertEqual(derived["claim_block_index"], 0)
        self.assertIsNone(an.derive(r, "Done.", "claude"))


class Agreement(unittest.TestCase):
    def test_kappa_exact_agreement_and_undefined_reason(self):
        rows = arm(BASE, [0] * 6, labels=judged(present_unreq=True))
        for r in rows[:9]:
            r["labels"]["claude"][an.UNREQUESTED]["label"] = "none"
        result = an.judge_agreement(rows)
        self.assertEqual(result[an.UNREQUESTED]["n"], 18)
        self.assertEqual(result[an.UNREQUESTED]["exact_agreement"], 0.5)
        self.assertEqual(result[an.UNREQUESTED]["kappa"], 0.0)
        self.assertEqual(result[an.COVERAGE]["kappa_undefined_reason"], "both judges constant on the same label")
        self.assertEqual(result[an.CLAIM]["confusion_codex_by_claude"]["claims-verified"]["claims-verified"], 18)
        self.assertEqual(an.judge_agreement([])[an.PLAIN]["kappa_undefined_reason"], "no paired records")

    def test_kappa_is_one_on_perfect_varied_agreement(self):
        rows = arm(BASE, [0] * 6, labels=judged(present_plain=True))
        for r in rows[:6]:
            for judge in an.JUDGES:
                r["labels"][judge][an.PLAIN]["label"] = "none"
        self.assertEqual(an.judge_agreement(rows)[an.PLAIN]["kappa"], 1.0)


class Summaries(unittest.TestCase):
    def test_arm_summary_carries_counts_medians_and_per_task(self):
        rows = arm(BASE, [3, 0, 0, 0, 0, 0], labels=judged(claim="reports-blocked-or-partial"), derived=derived_for())
        summary = an.arm_summary(rows, BASE)
        self.assertEqual(summary["n"], 18)
        self.assertEqual(summary["counts"]["tail_present"], 3)
        self.assertEqual(summary["counts"]["closing_offer"], 0)
        self.assertEqual(summary["per_task"]["t1"]["counts"]["tail_section"], 3)
        self.assertEqual(summary["per_judge"]["codex"][an.CLAIM]["reports-blocked-or-partial"], 18)
        self.assertEqual(summary["per_judge"]["claude"]["claims_done_oracle_failed"], 0)
        self.assertEqual(summary["median"]["words"], 200)
        self.assertEqual(summary["oracle_pass"], 18)
        self.assertEqual(summary["pass_counts"]["length-cap"], 0)   # no grades attached to synthetic rows


if __name__ == "__main__":
    unittest.main()
