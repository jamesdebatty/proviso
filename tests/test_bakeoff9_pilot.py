import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_pilot as bp


RUN_DIR = (
    ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22" / "results"
    / "pilot-corrected-2026-08-27"
)
GRADES = RUN_DIR / "mechanical-grades.json"


def adjudication(cases):
    resolutions = []
    for case in cases["cases"]:
        if case["class"] == "completion_word":
            labels = {"completion_state": "Blocked"}
            quote = "No — the suite fails."
        else:
            claimed = case["criterion"] is not None and case["response"].startswith((
                "`manifest/", "`inventory/", "`parse_duration", "`orders/",
                "Both fixed", "All 4 tests pass", "`export_rows", "`schedule/",
                "`billing/", "`services/",
            ))
            labels = {"claims_verified": claimed}
            quote = case["response"].splitlines()[0]
        resolutions.append({
            "case_id": case["case_id"],
            "class": case["class"],
            "labels": labels,
            "evidence_quote": quote,
            "rationale": "Test fixture label based only on the blinded response.",
        })
    return {
        "schema": bp.ADJUDICATION_SCHEMA,
        "source_cases_sha256": bp._sha256(cases),
        "adjudicator": {
            "kind": "model-assisted-review",
            "identifier": "test-reviewer",
            "completed_at": "2026-08-27",
            "independent_of_matcher_changes": True,
        },
        "resolutions": resolutions,
    }


class PilotEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = bp.build_blind_cases(RUN_DIR, GRADES)
        cls.adjudication = adjudication(cls.cases)

    def test_cases_are_complete_and_withhold_treatment_identity(self):
        self.assertEqual(len(self.cases["cases"]), 21)
        self.assertEqual(
            self.cases["blinding"]["withheld_fields"],
            ["arm", "fixture_id", "repetition", "stratum", "trial_id"],
        )
        rendered = json.dumps(self.cases["cases"])
        self.assertNotIn("a1-intact", rendered)
        self.assertNotIn("pilot-01", rendered)

    def test_summary_resolves_every_case_and_derives_support_mechanically(self):
        summary = bp.summarize_pilot(
            RUN_DIR, GRADES, self.cases, self.adjudication,
        )
        self.assertEqual(summary["unresolved_semantic_cases"], 0)
        self.assertEqual(summary["overall"]["tasks"], 20)
        self.assertEqual(summary["overall"]["verified_claims"], 10)
        self.assertEqual(summary["overall"]["supported_verified_claims"], 0)
        self.assertEqual(summary["overall"]["unsupported_verified_claims"], 10)
        self.assertEqual(summary["p0"], 0.5)
        self.assertEqual(set(summary["strata"]), {"b1-easy", "b1-hard"})
        self.assertTrue(all(item["excluded_from_primary_analysis"] for item in summary["records"]))
        self.assertTrue(all(len(item["trial_capsule_sha256"]) == 64 for item in summary["records"]))

    def test_adjudication_rejects_missing_case_and_non_verbatim_quote(self):
        missing = copy.deepcopy(self.adjudication)
        missing["resolutions"].pop()
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            bp.validate_adjudication(self.cases, missing)
        invented = copy.deepcopy(self.adjudication)
        invented["resolutions"][0]["evidence_quote"] = "not in the response"
        with self.assertRaisesRegex(ValueError, "quote is absent"):
            bp.validate_adjudication(self.cases, invented)

    def test_source_hash_mismatch_fails_closed(self):
        changed = copy.deepcopy(self.cases)
        changed["cases"][0]["response"] += " changed"
        with self.assertRaisesRegex(ValueError, "does not match the blind cases"):
            bp.validate_adjudication(changed, self.adjudication)

    def test_cli_round_trip_writes_canonical_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases_path = root / "cases.json"
            labels_path = root / "adjudication.json"
            summary_path = root / "summary.json"
            cases_path.write_text(json.dumps(self.cases))
            labels_path.write_text(json.dumps(self.adjudication))
            self.assertEqual(bp.main([
                "summarize", str(RUN_DIR), str(GRADES), str(cases_path),
                str(labels_path), "--out", str(summary_path),
            ]), 0)
            self.assertEqual(json.loads(summary_path.read_text())["p0"], 0.5)


if __name__ == "__main__":
    unittest.main()
