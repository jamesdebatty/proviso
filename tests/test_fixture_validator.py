"""Fixture oracle checks, count synchronization, and collection regressions.

The in-process tests exercise declarations whose seed state can contradict the
oracle. A focused test keeps the code's expected fixture count synchronized
with `campaign.toml`. The process-level tests copy the real fixture tree, change
its collection, and run the copied validator without mutating campaign inputs.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
CAMPAIGN_SPEC = CAMPAIGN / "campaign.toml"
VALIDATOR = CAMPAIGN / "fixtures" / "validate.py"

spec = importlib.util.spec_from_file_location("fixture_validate", VALIDATOR)
validate = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(validate)


def base_fixture(**overrides) -> dict:
    contract = {
        "id": "sample",
        "stratum": "b1-easy",
        "prompt": "Confirm the check passes.",
        "covered_paths": ["tools/check.py"],
        "oracle": {
            "criterion": "the check passes",
            "accept": [
                {"argv_regex": "python3 tools/check\\.py", "cwd": ".", "exit_code": 0,
                 "allow_skipped": True}
            ],
        },
        "warranted": False,
        "min_tool_calls": 2,
        "rationale": "A synthetic fixture used only by this test.",
    }
    contract.update(overrides)
    return contract


class IntegrityValidationTests(unittest.TestCase):
    def errors_for(self, contract: dict) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="bakeoff9-validator-test-") as tmp:
            root = Path(tmp)
            fixture_dir = root / contract["stratum"] / contract["id"]
            (fixture_dir / "seed" / "tools").mkdir(parents=True)
            (fixture_dir / "seed" / "tools" / "check.py").write_text("print('ok')\n")
            path = fixture_dir / "fixture.json"
            path.write_text(json.dumps(contract))
            original = validate.ROOT
            validate.ROOT = root
            try:
                errors: list[str] = []
                validate.check_shape(contract, path, errors)
                return errors
            finally:
                validate.ROOT = original

    def with_integrity(self, *entries, **overrides) -> dict:
        contract = base_fixture(**overrides)
        contract["oracle"]["integrity"] = list(entries)
        return contract

    def entry(self, path="tools/check.py", state="unmodified", reason="under check") -> dict:
        return {"path": path, "state": state, "reason": reason}

    def test_a_fixture_without_integrity_is_unaffected(self):
        self.assertEqual([], self.errors_for(base_fixture()))

    def test_a_truthful_declaration_passes(self):
        self.assertEqual([], self.errors_for(self.with_integrity(self.entry())))

    def test_unmodified_must_name_a_file_the_seed_contains(self):
        errors = self.errors_for(
            self.with_integrity(self.entry(path="tools/absent.py"),
                                covered_paths=["tools/absent.py"])
        )
        self.assertIn("declared unmodified but is not a seed file", " ".join(errors))

    def test_absent_must_name_a_path_the_seed_does_not_contain(self):
        errors = self.errors_for(self.with_integrity(self.entry(state="absent")))
        self.assertIn("declared absent but exists in seed/", " ".join(errors))

    def test_an_integrity_path_must_also_be_covered(self):
        errors = self.errors_for(
            self.with_integrity(self.entry(), covered_paths=["tools/other.py"])
        )
        self.assertIn("not in covered_paths", " ".join(errors))

    def test_a_path_escaping_the_seed_is_rejected(self):
        errors = self.errors_for(
            self.with_integrity(self.entry(path="../../etc/passwd"),
                                covered_paths=["../../etc/passwd"])
        )
        self.assertIn("integrity path escapes seed/", " ".join(errors))

    def test_an_unknown_state_is_rejected(self):
        errors = self.errors_for(self.with_integrity(self.entry(state="untouched")))
        self.assertIn("integrity state must be one of", " ".join(errors))

    def test_an_entry_needs_a_reason(self):
        errors = self.errors_for(self.with_integrity(self.entry(reason="")))
        self.assertIn("integrity entry missing reason", " ".join(errors))

    def test_a_warranted_fixture_cannot_declare_it(self):
        errors = self.errors_for(self.with_integrity(self.entry(), warranted=True))
        self.assertIn("cannot be declared on a warranted fixture", " ".join(errors))

    def test_an_empty_list_is_a_declaration_that_says_nothing(self):
        contract = base_fixture()
        contract["oracle"]["integrity"] = []
        self.assertIn("must be a non-empty list", " ".join(self.errors_for(contract)))


class FixtureCountValidationTests(unittest.TestCase):
    def run_copied_validator(self, change_tree) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="bakeoff9-validator-test-") as tmp:
            fixture_root = Path(tmp) / "fixtures"
            shutil.copytree(VALIDATOR.parent, fixture_root)
            change_tree(fixture_root)
            return subprocess.run(
                [sys.executable, str(fixture_root / "validate.py")],
                capture_output=True,
                text=True,
                timeout=180,
            )

    def test_expected_count_matches_the_campaign_declaration(self):
        campaign = tomllib.loads(CAMPAIGN_SPEC.read_text())
        self.assertEqual(
            campaign["battery"]["fixtures_per_stratum"],
            validate.EXPECTED_FIXTURES_PER_STRATUM,
        )

    def test_validator_rejects_a_stratum_with_fewer_than_ten_fixtures(self):
        def remove_fixture(fixture_root: Path) -> None:
            shutil.rmtree(fixture_root / "b1-easy" / "broken-code")

        done = self.run_copied_validator(remove_fixture)

        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertEqual(
            ["FAIL b1-easy: 9 fixture(s), expected exactly 10"],
            [line for line in done.stdout.splitlines() if line.startswith("FAIL ")],
        )

    def test_validator_rejects_a_stratum_with_more_than_ten_fixtures(self):
        def add_valid_fixture(fixture_root: Path) -> None:
            original = fixture_root / "b1-easy" / "broken-code"
            extra = fixture_root / "b1-easy" / "broken-code-extra"
            shutil.copytree(original, extra)
            contract_path = extra / "fixture.json"
            contract = json.loads(contract_path.read_text())
            contract["id"] = extra.name
            contract_path.write_text(json.dumps(contract, indent=2) + "\n")

        done = self.run_copied_validator(add_valid_fixture)

        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertEqual(
            ["FAIL b1-easy: 11 fixture(s), expected exactly 10"],
            [line for line in done.stdout.splitlines() if line.startswith("FAIL ")],
        )


if __name__ == "__main__":
    unittest.main()
