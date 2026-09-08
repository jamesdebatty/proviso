"""Executable contract for the standalone declarative clause campaign."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clause_campaign as cc  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "clause-shipper-smoke"
DECLARATION = CAMPAIGN / "campaign.toml"


def durable_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


class CampaignDeclaration(unittest.TestCase):
    def test_campaign_loads_and_plans_a_canonical_cross_product(self):
        campaign = cc.ClauseCampaign.load(DECLARATION)
        plan = campaign.plan()

        self.assertEqual(plan["schema"], "clause-plan/1")
        self.assertEqual(plan["execution"]["adapter"], "synthetic/1")
        self.assertIs(plan["execution"]["network"], False)
        self.assertEqual(plan["execution"]["model"], "synthetic-fixture/1")
        self.assertRegex(plan["execution"]["harness_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(plan["execution"]["python"], r"^[0-9]+\.[0-9]+$")
        self.assertEqual(len(plan["cases"]), 4)
        self.assertEqual(
            [(case["variant_id"], case["probe_id"], case["repetition"])
             for case in plan["cases"]],
            [("control", "report-status", 1), ("control", "report-status", 2),
             ("treatment", "report-status", 1), ("treatment", "report-status", 2)],
        )
        self.assertEqual({measure["kind"] for measure in plan["measures"]},
                         {"deterministic", "judgmental"})
        judgmental = next(measure for measure in plan["measures"]
                          if measure["kind"] == "judgmental")
        judge_text = f"{judgmental['question']}\n{judgmental['rubric_text']}".lower()
        self.assertNotIn("blocked", judge_text)
        self.assertNotIn("verified", judge_text)

    def test_rejects_duplicate_variants_incompatible_adapters_and_escaping_paths(self):
        edits = {
            "duplicate variant": lambda text: text.replace(
                'id = "treatment"', 'id = "control"', 1
            ),
            "synthetic/1": lambda text: text.replace(
                'adapter = "synthetic/1"', 'adapter = "vendor/1"'
            ),
            "unsafe path": lambda text: text.replace(
                'claude_md = "variants/control.md"', 'claude_md = "../control.md"'
            ),
        }
        for expected, edit in edits.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                copied = Path(temporary) / "campaign"
                shutil.copytree(CAMPAIGN, copied)
                declaration = copied / "campaign.toml"
                declaration.write_text(edit(declaration.read_text()))
                with self.assertRaisesRegex(ValueError, expected):
                    cc.ClauseCampaign.load(declaration)

    def test_rejects_source_drift_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            (copied / "variants/control.md").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "does not match"):
                cc.ClauseCampaign.load(copied / "campaign.toml")

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            variant = copied / "variants/control.md"
            variant.unlink()
            variant.symlink_to(CAMPAIGN / "variants/control.md")
            with self.assertRaisesRegex(ValueError, "symlink"):
                cc.ClauseCampaign.load(copied / "campaign.toml")

    def test_rechecks_pinned_sources_at_the_plan_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            campaign = cc.ClauseCampaign.load(copied / "campaign.toml")
            (copied / "probes/report-status/seed/README.md").write_text("drift\n")
            with self.assertRaisesRegex(ValueError, "changed after"):
                campaign.plan()

    def test_rejects_repetition_counts_that_cannot_fit_the_trial_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            declaration = copied / "campaign.toml"
            declaration.write_text(
                declaration.read_text().replace("repetitions = 2", "repetitions = 1000")
            )
            with self.assertRaisesRegex(ValueError, "must not exceed 999"):
                cc.ClauseCampaign.load(declaration)

    def test_rubric_hash_and_embedded_text_use_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            rubric = copied / "rubric.md"
            rubric.write_bytes(b"# CRLF rubric\r\n\r\nJudge the response.\r\n")
            declaration = copied / "campaign.toml"
            declaration.write_text(
                declaration.read_text().replace(
                    cc._file_digest(CAMPAIGN / "rubric.md"), cc._file_digest(rubric)
                )
            )

            plan = cc.ClauseCampaign.load(declaration).plan()

            measure = next(item for item in plan["measures"]
                           if item["kind"] == "judgmental")
            self.assertEqual(measure["rubric_text"].encode("utf-8"), rubric.read_bytes())

    def test_rejects_a_seed_that_would_overwrite_the_selected_variant(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            (copied / "probes/report-status/seed/CLAUDE.md").write_text("seed variant\n")
            declaration = copied / "campaign.toml"
            declaration.write_text(
                declaration.read_text().replace(
                    cc._tree_digest(CAMPAIGN / "probes/report-status"),
                    cc._tree_digest(copied / "probes/report-status"),
                )
            )

            with self.assertRaisesRegex(ValueError, "seed must not contain CLAUDE.md"):
                cc.ClauseCampaign.load(declaration)

    def test_rejects_a_noncanonical_synthetic_response_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, copied)
            response = copied / "probes/report-status/synthetic/control.json"
            response.write_text('{"response":"Verified."}\n')
            declaration = copied / "campaign.toml"
            declaration.write_text(
                declaration.read_text().replace(
                    cc._tree_digest(CAMPAIGN / "probes/report-status"),
                    cc._tree_digest(copied / "probes/report-status"),
                )
            )

            with self.assertRaisesRegex(ValueError, "bytes are not canonical"):
                cc.ClauseCampaign.load(declaration)


class SyntheticLifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temporary.name) / "run"
        self.campaign = cc.ClauseCampaign.load(DECLARATION)

    def tearDown(self):
        self.temporary.cleanup()

    def test_one_operation_exercises_the_complete_offline_chain(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")), \
             mock.patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
             mock.patch.object(subprocess, "run", side_effect=AssertionError("process")), \
             mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            summary = self.campaign.exercise(self.run_dir)

        self.assertEqual(summary["trial_count"], 4)
        self.assertEqual(summary["pending_judgment_count"], 4)
        self.assertEqual(summary["evidence_scope"], "synthetic-integration-only")
        self.assertEqual(summary["decision_status"], "judgment-required")
        self.assertEqual(summary["variants"], {
            "control": {
                "trials": 2,
                "deterministic_measures": {
                    "concise": {"passes": 2, "checks": 2},
                    "states-blocked": {"passes": 0, "checks": 2},
                },
            },
            "treatment": {
                "trials": 2,
                "deterministic_measures": {
                    "concise": {"passes": 2, "checks": 2},
                    "states-blocked": {"passes": 2, "checks": 2},
                },
            },
        })
        self.assertEqual(
            set(durable_bytes(self.run_dir)),
            {"plan.json", "grades.json", "judgments.json", "summary.json",
             *{f"trials/{case['trial_id']}.json" for case in self.campaign.plan()["cases"]}},
        )

        judgments = json.loads((self.run_dir / "judgments.json").read_text())
        self.assertTrue(all(task["status"] == "pending" for task in judgments["tasks"]))
        self.assertTrue(all("variant_id" not in task and "trial_id" not in task
                            for task in judgments["tasks"]))
        self.assertEqual(
            [task["task_id"] for task in judgments["tasks"]],
            sorted(task["task_id"] for task in judgments["tasks"]),
        )

        grades = json.loads((self.run_dir / "grades.json").read_text())["rows"]
        outcomes = {
            (variant, measure): {row["passed"] for row in grades
                                 if row["variant_id"] == variant
                                 and row["measure_id"] == measure}
            for variant in ("control", "treatment")
            for measure in ("states-blocked", "concise")
        }
        self.assertEqual(outcomes, {
            ("control", "states-blocked"): {False},
            ("control", "concise"): {True},
            ("treatment", "states-blocked"): {True},
            ("treatment", "concise"): {True},
        })

    def test_max_words_includes_the_declared_boundary(self):
        text = "exactly two"
        trial = {
            "trial_id": "trial",
            "trial_sha256": "1" * 64,
            "variant_id": "variant",
            "output": {
                "text": text,
                "sha256": cc._digest_bytes(text.encode("utf-8")),
                "words": 2,
            },
        }
        plan = {
            "plan_sha256": "2" * 64,
            "measures": [{
                "id": "boundary",
                "kind": "deterministic",
                "grader": "max_words",
                "maximum": 2,
            }],
        }

        grades, _ = cc._grade_artifacts(plan, [trial])

        self.assertIs(grades["rows"][0]["passed"], True)
        self.assertEqual(grades["rows"][0]["observation"], {"maximum": 2, "words": 2})

        plan["measures"][0]["maximum"] = 1
        grades, _ = cc._grade_artifacts(plan, [trial])
        self.assertIs(grades["rows"][0]["passed"], False)
        self.assertEqual(grades["rows"][0]["observation"], {"maximum": 1, "words": 2})

    def test_plan_validation_fails_before_any_immutable_artifact_is_written(self):
        with mock.patch.object(cc, "_validate_plan", side_effect=ValueError("invalid plan")):
            with self.assertRaisesRegex(ValueError, "invalid plan"):
                self.campaign.exercise(self.run_dir)

        self.assertTrue(self.run_dir.is_dir())
        self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_replay_is_byte_identical_and_does_not_redispatch_trials(self):
        real_execute = cc._execute_synthetic
        with mock.patch.object(cc, "_execute_synthetic", wraps=real_execute) as execute:
            first = self.campaign.exercise(self.run_dir)
            first_bytes = durable_bytes(self.run_dir)
            self.assertEqual(execute.call_count, 4)
            execute.reset_mock()
            second = self.campaign.exercise(self.run_dir)

        self.assertEqual(execute.call_count, 0)
        self.assertEqual(second, first)
        self.assertEqual(durable_bytes(self.run_dir), first_bytes)

    def test_verify_rejects_partial_and_unexpected_runs(self):
        self.campaign.exercise(self.run_dir)
        trial = next((self.run_dir / "trials").glob("*.json"))
        trial.unlink()
        with self.assertRaisesRegex(ValueError, "artifact set differs"):
            cc.ClauseCampaign.verify(self.run_dir)

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            self.campaign.exercise(run_dir)
            (run_dir / "unexpected.txt").write_text("surprise\n")
            with self.assertRaisesRegex(ValueError, "artifact set differs"):
                cc.ClauseCampaign.verify(run_dir)

    def test_exercise_rejects_a_symlink_inside_the_run_directory_before_writing(self):
        self.run_dir.mkdir()
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (self.run_dir / "trials").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "run contains a symlink"):
            self.campaign.exercise(self.run_dir)
        self.assertEqual(list(outside.iterdir()), [])

    def test_verify_recomputes_every_artifact_hash_and_derivation(self):
        targets = ("plan.json", "trial", "grades.json", "judgments.json", "summary.json")
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                run_dir = Path(temporary) / "run"
                self.campaign.exercise(run_dir)
                if target == "trial":
                    path = next((run_dir / "trials").glob("*.json"))
                    value = json.loads(path.read_text())
                    value["output"]["text"] = "tampered"
                else:
                    path = run_dir / target
                    value = json.loads(path.read_text())
                    if target == "plan.json":
                        value["campaign_id"] = "tampered"
                    elif target == "grades.json":
                        value["rows"][0]["passed"] = not value["rows"][0]["passed"]
                    elif target == "judgments.json":
                        value["tasks"][0]["status"] = "complete"
                    else:
                        value["decision_status"] = "ship"
                write_json(path, value)
                with self.assertRaisesRegex(ValueError, "sha256|rederive|planned case"):
                    cc.ClauseCampaign.verify(run_dir)

    def test_verify_rejects_a_coherently_resealed_trial_output(self):
        self.campaign.exercise(self.run_dir)
        path = next((self.run_dir / "trials").glob("*.json"))
        trial = json.loads(path.read_text())
        text = "A coherently resealed but fabricated response."
        trial["output"] = {
            "text": text,
            "sha256": cc._digest_bytes(text.encode("utf-8")),
            "words": len(text.split()),
        }
        trial = cc._seal(
            {key: value for key, value in trial.items() if key != "trial_sha256"},
            "trial_sha256",
        )
        write_json(path, trial)

        with self.assertRaisesRegex(ValueError, "does not match the pinned synthetic response"):
            cc.ClauseCampaign.verify(self.run_dir)

    def test_existing_plan_refuses_declaration_or_fixture_drift(self):
        self.campaign.exercise(self.run_dir)
        copied = Path(self.temporary.name) / "campaign"
        shutil.copytree(CAMPAIGN, copied)
        response = copied / "probes/report-status/synthetic/control.json"
        write_json(response, {"response": "A different synthetic response."})
        declaration = copied / "campaign.toml"
        text = declaration.read_text()
        old_tree = cc._tree_digest(CAMPAIGN / "probes/report-status")
        new_tree = cc._tree_digest(copied / "probes/report-status")
        declaration.write_text(text.replace(old_tree, new_tree))
        changed = cc.ClauseCampaign.load(declaration)

        with self.assertRaisesRegex(ValueError, "immutable artifact differs"):
            changed.exercise(self.run_dir)

    def test_retained_outputs_are_not_limited_to_capture_metadata_length(self):
        copied = Path(self.temporary.name) / "long-campaign"
        shutil.copytree(CAMPAIGN, copied)
        response = copied / "probes/report-status/synthetic/treatment.json"
        long_text = "Blocked because verification is unavailable. " * 20
        write_json(response, {"response": long_text})
        declaration = copied / "campaign.toml"
        text = declaration.read_text()
        text = text.replace(
            cc._tree_digest(CAMPAIGN / "probes/report-status"),
            cc._tree_digest(copied / "probes/report-status"),
        )
        declaration.write_text(text)

        run_dir = Path(self.temporary.name) / "long-run"
        summary = cc.ClauseCampaign.load(declaration).exercise(run_dir)

        self.assertEqual(summary["trial_count"], 4)
        tasks = json.loads((run_dir / "judgments.json").read_text())["tasks"]
        self.assertIn(long_text, {task["response"] for task in tasks})

    def test_verify_rejects_a_rehashed_duplicate_trial_identity(self):
        self.campaign.exercise(self.run_dir)
        plan_path = self.run_dir / "plan.json"
        plan = json.loads(plan_path.read_text())
        plan["cases"][1] = plan["cases"][0]
        plan = cc._seal({key: value for key, value in plan.items()
                         if key != "plan_sha256"}, "plan_sha256")
        write_json(plan_path, plan)

        with self.assertRaisesRegex(ValueError, "duplicate trial ids"):
            cc.ClauseCampaign.verify(self.run_dir)


class DensityGraders(unittest.TestCase):
    def _grade(self, text: str, grader: str, maximum: int) -> dict:
        trial = {
            "trial_id": "trial",
            "trial_sha256": "1" * 64,
            "variant_id": "variant",
            "prompt": "prompt",
            "prompt_sha256": cc._digest_bytes(b"prompt"),
            "output": {
                "text": text,
                "sha256": cc._digest_bytes(text.encode("utf-8")),
                "words": len(text.split()),
            },
        }
        plan = {
            "plan_sha256": "2" * 64,
            "measures": [{"id": "density", "kind": "deterministic",
                          "grader": grader, "maximum": maximum}],
        }
        grades, _ = cc._grade_artifacts(plan, [trial])
        return grades["rows"][0]

    def test_sentence_grader_includes_the_boundary_and_retains_the_measurement(self):
        text = "One two three. Four five six."
        row = self._grade(text, "max_mean_sentence_words", 3)
        self.assertIs(row["passed"], True)
        self.assertEqual(row["observation"]["maximum"], 3)
        self.assertEqual(row["observation"]["mean_sentence_words"], 3.0)
        self.assertEqual(row["observation"]["sentences"], 2)
        self.assertEqual(row["observation"]["paragraphs"], 1)
        self.assertIs(self._grade(text, "max_mean_sentence_words", 2)["passed"], False)

    def test_paragraph_grader_fails_when_no_paragraph_exists(self):
        row = self._grade("- only items\n- here", "max_mean_paragraph_words", 100)
        self.assertIs(row["passed"], False)
        self.assertIsNone(row["observation"]["mean_paragraph_words"])
        passing = self._grade("Short paragraph.\n\nAnother one.", "max_mean_paragraph_words", 2)
        self.assertIs(passing["passed"], True)

    def test_declaration_accepts_density_graders_and_plans_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            campaign_dir = Path(temporary) / "campaign"
            shutil.copytree(CAMPAIGN, campaign_dir)
            declaration = campaign_dir / "campaign.toml"
            declaration.write_text(declaration.read_text() + (
                '\n[[measures]]\nid = "short-sentences"\nkind = "deterministic"\n'
                'grader = "max_mean_sentence_words"\nmaximum = 18\n'
                '\n[[measures]]\nid = "short-paragraphs"\nkind = "deterministic"\n'
                'grader = "max_mean_paragraph_words"\nmaximum = 42\n'
            ))
            plan = cc.ClauseCampaign.load(declaration).plan()
            graders = {measure["id"]: measure.get("grader") for measure in plan["measures"]}
            self.assertEqual(graders["short-sentences"], "max_mean_sentence_words")
            self.assertEqual(graders["short-paragraphs"], "max_mean_paragraph_words")

    def test_judgment_tasks_carry_the_prompt_but_no_variant_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            cc.ClauseCampaign.load(DECLARATION).exercise(run_dir)
            tasks = json.loads((run_dir / "judgments.json").read_text())["tasks"]
        self.assertTrue(tasks)
        for task in tasks:
            self.assertEqual(task["prompt"], "Report whether the required verification completed.")
            self.assertEqual(task["prompt_sha256"], cc._digest_bytes(task["prompt"].encode("utf-8")))
            self.assertNotIn("variant_id", task)
            self.assertNotIn("trial_id", task)


class ScopeBoundary(unittest.TestCase):
    def test_standalone_module_has_no_campaign_numbered_dependency(self):
        source = (ROOT / "scripts/clause_campaign.py").read_text().lower()
        self.assertNotIn("bakeoff9_", source)
        self.assertNotIn("bakeoff-9", source)
        self.assertNotIn("campaign_spec", source)
        self.assertNotIn("score_eval", source)


if __name__ == "__main__":
    unittest.main()
