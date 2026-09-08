"""The declaration format, checked by re-deriving a campaign that already ran.

The load-bearing test is `Bakeoff8Reproduction`: bakeoff 8's arms declared in
`campaign-declaration/1`, its deterministic summaries regenerated from
`out/bakeoff-20260814T055452Z` alone, and every number compared against the ones
its own 880-line `analyze.py` wrote into `bakeoff-results.json`. A format that
cannot reproduce a campaign that already ran has not been tested.

The two gates bakeoff 8 computed that this format does not express are asserted
explicitly rather than quietly dropped, so the gap stays visible.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import campaign_spec as cspec  # noqa: E402

BAKEOFF8 = ROOT / "campaigns" / "clause-bakeoff-8-2026-08-11"
BAKEOFF8_OUT = BAKEOFF8 / "out" / "bakeoff-20260814T055452Z"
BAKEOFF8_DECLARATION = ROOT / "sources" / "2026-08-25-t006-bakeoff8-declaration.toml"
BAKEOFF9 = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
BAKEOFF9_DECLARATION = BAKEOFF9 / "campaign.toml"
EXAMPLE_MANIFEST = ROOT / "sources" / "2026-08-24-t002-example-manifest.json"

SCORE_METRICS = ("task_completion", "focus", "plain_language",
                 "jargon_discipline", "nuance_and_safety")
ENTRY_FIELDS = ("material_error_entries", "missing_requirement_entries",
                "invented_precision_entries", "undefined_coinage_entries")
# Bakeoff 8 computed these two from the dual-judge allegation rule and the
# human-review adjudication merge. Neither is a reduction over records, so the
# format does not express them; bakeoff 9 retires them independently.
UNEXPRESSED_GATES = ("no_confirmed_material_errors", "no_unresolved_disputed_errors")

MINIMAL = """
schema = "campaign-declaration/1"
[campaign]
id = "x"
baseline_arm = "a"
[[arms]]
id = "a"
[[arms]]
id = "b"
[records]
source = "capture-spine/1"
[[reductions]]
name = "n"
over = "trial"
field = "output_tokens"
statistic = "median"
group_by = ["arm"]
"""


def write_declaration(directory: Path, text: str) -> Path:
    path = Path(directory) / "campaign.toml"
    path.write_text(text)
    return path


class Bakeoff8Reproduction(unittest.TestCase):
    """Regenerate bakeoff 8 from out/ through the declarative path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = cspec.load(BAKEOFF8_DECLARATION)
        cls.got = cspec.analyze(cls.spec, BAKEOFF8_OUT)
        manifest = json.loads((BAKEOFF8_OUT / "bakeoff-results.json").read_text())
        cls.expected = manifest["summary"]["arms"]
        cls.manifest = manifest
        cls.baseline = cls.spec["campaign"]["baseline_arm"]
        cls.arms = [arm["id"] for arm in cls.spec["arms"]]

    def reduction(self, name: str, *key: str):
        return self.got["reductions"][name]["/".join(key)]

    def test_reads_the_whole_result_set(self):
        self.assertEqual(self.got["records"]["response"], self.manifest["response_count"])
        self.assertEqual(self.got["records"]["judgment"],
                         self.manifest["judgment_count"] * len(self.arms))

    def test_mean_scores_match_the_archived_analyzer(self):
        for arm in self.arms:
            for judge in ("sonnet", "codex"):
                for metric in SCORE_METRICS:
                    with self.subTest(arm=arm, judge=judge, metric=metric):
                        self.assertEqual(
                            self.reduction(f"mean_{metric}", judge, arm),
                            self.expected[arm]["judges"][judge]["mean_scores"][metric])

    def test_judge_entry_counts_match(self):
        for arm in self.arms:
            for judge in ("sonnet", "codex"):
                for field in ENTRY_FIELDS:
                    with self.subTest(arm=arm, judge=judge, field=field):
                        self.assertEqual(self.reduction(field, judge, arm),
                                         self.expected[arm]["judges"][judge][field])

    def test_response_scan_medians_and_stalls_match(self):
        for arm in self.arms:
            with self.subTest(arm=arm):
                self.assertEqual(self.reduction("median_words", arm),
                                 self.expected[arm]["median_words"])
                self.assertEqual(self.reduction("median_novel_numerals", arm),
                                 self.expected[arm]["median_novel_numerals"])
                self.assertEqual(self.reduction("median_novel_coinages", arm),
                                 self.expected[arm]["median_novel_coinages"])
                self.assertEqual(self.reduction("stalled_responses", arm),
                                 self.expected[arm]["stalled_responses"])

    def test_pairwise_tallies_and_win_rates_match(self):
        """The only rename: bakeoff 8 keyed the baseline outcome by arm name."""
        for arm in self.arms:
            if arm == self.baseline:
                continue
            for judge in ("sonnet", "codex"):
                with self.subTest(arm=arm, judge=judge):
                    tally = dict(self.reduction("vs_baseline", judge, arm))
                    tally[self.baseline] = tally.pop("baseline")
                    self.assertEqual(tally,
                                     self.expected[arm]["judges"][judge]["vs_control"])
                    self.assertEqual(
                        self.reduction("non_tied_win_rate", judge, arm),
                        self.expected[arm]["judges"][judge]["non_tied_win_rate"])
            pooled = dict(self.reduction("pooled_vs_baseline", arm))
            pooled[self.baseline] = pooled.pop("baseline")
            self.assertEqual(pooled, self.expected[arm]["pooled_vs_control"])
            self.assertEqual(self.reduction("pooled_non_tied_win_rate", arm),
                             self.expected[arm]["pooled_non_tied_win_rate"])

    def test_comparisons_match(self):
        for arm in self.arms:
            if arm == self.baseline:
                continue
            self.assertEqual(self.got["comparisons"]["word_change_pct"][arm],
                             self.expected[arm]["word_change_pct"])
            for judge in ("sonnet", "codex"):
                with self.subTest(arm=arm, judge=judge):
                    self.assertEqual(
                        self.got["comparisons"]["nuance_delta"][f"{judge}/{arm}"],
                        self.expected[arm]["judges"][judge]["nuance_delta"])

    def test_declared_gates_match_and_the_gap_is_exactly_the_two_error_gates(self):
        for arm in self.arms:
            if arm == self.baseline:
                continue
            declared = self.got["gates"][arm]
            archived = self.expected[arm]["gates"]
            self.assertEqual(set(archived) - set(declared), set(UNEXPRESSED_GATES))
            for name, value in declared.items():
                with self.subTest(arm=arm, gate=name):
                    self.assertEqual(value, archived[name])
            # Bakeoff 8's `eligible` folds in the two gates above, so the
            # declared verdict is not the archived one and is not claimed to be.
            self.assertFalse(self.expected[arm]["eligible"])
            # Where gates exist, the arm still carries a boolean verdict.
            self.assertIsInstance(self.got["eligible"][arm], bool)

    def test_baseline_arm_gets_no_gate_row(self):
        self.assertNotIn(self.baseline, self.got["gates"])


class Bakeoff8ReaderChecks(unittest.TestCase):
    """The declaration is load-bearing: the reader refuses results that contradict it."""

    def setUp(self):
        self.spec = cspec.load(BAKEOFF8_DECLARATION)

    def test_undeclared_arm_raises(self):
        self.spec["arms"] = [arm for arm in self.spec["arms"] if arm["id"] != "composite"]
        with self.assertRaisesRegex(ValueError, "undeclared arm"):
            cspec.read_bakeoff_out(self.spec, BAKEOFF8_OUT)

    def test_binary_version_other_than_the_pin_raises(self):
        self.spec["pins"]["generator_binary_version"] = "2.1.239 (Claude Code)"
        with self.assertRaisesRegex(ValueError, "not the declared pin"):
            cspec.read_bakeoff_out(self.spec, BAKEOFF8_OUT)

    def test_clause_hash_other_than_the_arm_hash_raises(self):
        for arm in self.spec["arms"]:
            if arm["id"] == "composite":
                arm["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "clause hash"):
            cspec.read_bakeoff_out(self.spec, BAKEOFF8_OUT)


class Bakeoff9Declaration(unittest.TestCase):
    def setUp(self):
        self.spec = cspec.load(BAKEOFF9_DECLARATION)

    def test_validates_clean(self):
        self.assertEqual(cspec.validate(self.spec), [])

    def test_arm_clause_hashes_are_the_files_on_disk(self):
        for arm in self.spec["arms"]:
            with self.subTest(arm=arm["id"]):
                self.assertEqual(cspec._sha256_file(BAKEOFF9 / arm["claude_md"]),
                                 arm["sha256"])

    def test_declares_the_two_by_two_with_ablation_on_the_hard_stratum_only(self):
        levels = {arm["id"]: (arm["claude_md_factor"], arm["harness_prompt"])
                  for arm in self.spec["arms"]}
        self.assertEqual(set(levels.values()),
                         {("A1", "intact"), ("A2", "intact"),
                          ("A1", "ablated"), ("A2", "ablated")})
        for arm in self.spec["arms"]:
            expected = ["b1-hard"] if arm["harness_prompt"] == "ablated" else \
                ["b1-easy", "b1-hard", "b3"]
            self.assertEqual(arm["strata"], expected)

    def test_declares_no_gates_because_none_of_the_criteria_are_expressible(self):
        self.assertEqual(self.spec.get("gates", []), [])

    def test_reads_the_spine_and_not_the_archived_layout(self):
        self.assertEqual(self.spec["records"]["source"], "capture-spine/1")

    def test_zero_gates_leave_every_arm_without_an_eligible_verdict(self):
        """A declaration that gates nothing must not report arms as passing."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({
                "schema": "capture-spine/1",
                "trials": [{"trial_id": f"healthy-{arm['id']}", "arm": arm["id"],
                            "fixture_id": "healthy", "stratum": arm["strata"][0],
                            "surface_verdict": "match", "distinct_surfaces": 1,
                            "usage_totals": {"output_tokens": 100}}
                           for arm in self.spec["arms"]]}))
            got = cspec.analyze(self.spec, manifest)
        self.assertEqual(got["gates"],
                         {"a2-intact": {}, "a1-ablated": {}, "a2-ablated": {}})
        self.assertEqual(got["eligible"], {})


class SpineReader(unittest.TestCase):
    """Read the real T-002 worked manifest, which records one caught mismatch."""

    DECLARATION = """
schema = "campaign-declaration/1"
[campaign]
id = "spine-reader-check"
baseline_arm = "control"
[[arms]]
id = "control"
strata = ["b1-easy"]
[records]
source = "capture-spine/1"
[[reductions]]
name = "trials"
over = "trial"
statistic = "count"
group_by = ["arm"]
[[reductions]]
name = "surface_verdicts"
over = "trial"
field = "surface_verdict"
statistic = "tally"
group_by = ["arm"]
[[reductions]]
name = "median_output_tokens"
over = "trial"
field = "output_tokens"
statistic = "median"
group_by = ["arm"]
"""

    def analyze(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = cspec.load(write_declaration(directory, self.DECLARATION))
            return spec, cspec.analyze(spec, EXAMPLE_MANIFEST)

    def test_trial_records_carry_the_spine_fields_the_reductions_name(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = cspec.load(write_declaration(directory, self.DECLARATION))
            records = cspec.read_capture_spine(spec, EXAMPLE_MANIFEST)
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first["arm"], "control")
        self.assertEqual(first["stratum"], "b1-easy")
        self.assertEqual(first["surface_verdict"], "match")
        self.assertEqual(first["output_tokens"], 452)
        self.assertEqual(first["turns"], 2)

    def test_a_mid_run_surface_mismatch_survives_into_the_summary(self):
        _, got = self.analyze()
        self.assertEqual(got["reductions"]["trials"]["control"], 2)
        self.assertEqual(got["reductions"]["surface_verdicts"]["control"],
                         {"match": 1, "mismatch": 1})
        self.assertEqual(got["reductions"]["median_output_tokens"]["control"], 296)

    def test_a_stratum_the_arm_does_not_declare_raises(self):
        declaration = self.DECLARATION.replace('strata = ["b1-easy"]', 'strata = ["b3"]')
        with tempfile.TemporaryDirectory() as directory:
            spec = cspec.load(write_declaration(directory, declaration))
            with self.assertRaisesRegex(ValueError, "not declared over stratum"):
                cspec.read_capture_spine(spec, EXAMPLE_MANIFEST)

    def test_a_manifest_of_another_schema_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = cspec.load(write_declaration(directory, self.DECLARATION))
            other = Path(directory) / "other.json"
            other.write_text(json.dumps({"schema": "capture-spine/2", "trials": []}))
            with self.assertRaisesRegex(ValueError, "not a capture-spine/1 manifest"):
                cspec.read_capture_spine(spec, other)


class Validation(unittest.TestCase):
    def problems(self, text: str) -> list[str]:
        return cspec.validate(cspec_spec(text))

    def test_minimal_declaration_is_clean(self):
        self.assertEqual(self.problems(MINIMAL), [])

    def test_wrong_schema_is_a_problem(self):
        text = MINIMAL.replace("campaign-declaration/1", "campaign-declaration/2")
        self.assertIn("schema must be 'campaign-declaration/1'", self.problems(text))

    def test_baseline_must_name_a_declared_arm(self):
        text = MINIMAL.replace('baseline_arm = "a"', 'baseline_arm = "zzz"')
        self.assertIn("campaign.baseline_arm must name a declared arm", self.problems(text))

    def test_unknown_record_source_is_a_problem(self):
        text = MINIMAL.replace('source = "capture-spine/1"', 'source = "guesswork/1"')
        self.assertTrue(any("records.source" in item for item in self.problems(text)))

    def test_unknown_scan_is_a_problem(self):
        text = MINIMAL.replace('source = "capture-spine/1"',
                               'source = "capture-spine/1"\nscans = ["vibes"]')
        self.assertIn("unknown scan 'vibes'", self.problems(text))

    def test_group_by_must_include_arm_so_the_baseline_is_always_findable(self):
        text = MINIMAL.replace('group_by = ["arm"]', 'group_by = ["stratum"]')
        self.assertIn("n: group_by must include 'arm'", self.problems(text))

    def test_unknown_statistic_is_a_problem(self):
        text = MINIMAL.replace('statistic = "median"', 'statistic = "vibe"')
        self.assertTrue(any("statistic must be" in item for item in self.problems(text)))

    def test_share_needs_a_value_and_a_denominator(self):
        text = MINIMAL.replace('statistic = "median"', 'statistic = "share"')
        self.assertIn("n: share needs value and among", self.problems(text))

    def test_gate_naming_an_unknown_reduction_is_a_problem(self):
        text = MINIMAL + '\n[[gates]]\nname = "g"\nreduction = "nope"\nop = "<="\nvs = "baseline"\n'
        self.assertIn("gate 'g': unknown reduction or comparison", self.problems(text))

    def test_gate_needs_exactly_one_of_vs_and_value(self):
        text = MINIMAL + '\n[[gates]]\nname = "g"\nreduction = "n"\nop = "<="\n'
        self.assertIn("gate 'g': needs exactly one of vs, value", self.problems(text))
        text += 'vs = "baseline"\nvalue = 1.0\n'
        self.assertIn("gate 'g': needs exactly one of vs, value", self.problems(text))

    def test_load_raises_on_a_bad_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_declaration(directory, MINIMAL.replace('id = "a"', 'id = "b"'))
            with self.assertRaises(ValueError):
                cspec.load(path)


def cspec_spec(text: str) -> dict:
    import tomllib
    spec = tomllib.loads(text)
    spec["_path"] = "/nonexistent/campaign.toml"
    return spec


class Reductions(unittest.TestCase):
    RECORDS = [
        {"record": "trial", "arm": "a", "n": 1, "outcome": "win", "keep": "yes"},
        {"record": "trial", "arm": "a", "n": 3, "outcome": "loss", "keep": "no"},
        {"record": "trial", "arm": "b", "n": 10, "outcome": "win", "keep": "yes"},
        {"record": "judgment", "arm": "a", "n": 99, "outcome": "win", "keep": "yes"},
    ]

    def apply(self, **item):
        item.setdefault("over", "trial")
        item.setdefault("group_by", ["arm"])
        return cspec._apply(item, self.RECORDS)

    def test_only_the_named_record_kind_is_reduced(self):
        self.assertEqual(self.apply(field="n", statistic="sum"), {("a",): 4, ("b",): 10})

    def test_where_filters_without_erasing_the_group(self):
        got = self.apply(field="n", statistic="median", where={"keep": "yes"})
        self.assertEqual(got, {("a",): 1, ("b",): 10})

    def test_a_where_that_selects_nothing_counts_zero_rather_than_vanishing(self):
        got = self.apply(statistic="count", where={"keep": "maybe"})
        self.assertEqual(got, {("a",): 0, ("b",): 0})

    def test_empty_group_medians_are_none_not_an_error(self):
        got = self.apply(field="n", statistic="median", where={"keep": "maybe"})
        self.assertEqual(got, {("a",): None, ("b",): None})

    def test_tally_and_share(self):
        self.assertEqual(self.apply(field="outcome", statistic="tally"),
                         {("a",): {"loss": 1, "win": 1}, ("b",): {"win": 1}})
        got = self.apply(field="outcome", statistic="share", value="win",
                         among=["win", "loss"])
        self.assertEqual(got, {("a",): 0.5, ("b",): 1.0})

    def test_rounding_is_declared_not_implicit(self):
        got = self.apply(field="n", statistic="mean", round=1)
        self.assertEqual(got[("a",)], 2.0)
        self.assertEqual(self.apply(field="n", statistic="mean")[("a",)], 2)

    def test_missing_values_are_skipped_not_counted_as_zero(self):
        records = self.RECORDS + [{"record": "trial", "arm": "a", "n": None}]
        self.assertEqual(cspec._apply(
            {"over": "trial", "group_by": ["arm"], "field": "n", "statistic": "mean"},
            records)[("a",)], 2)


if __name__ == "__main__":
    unittest.main()
