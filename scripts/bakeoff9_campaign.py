#!/usr/bin/env python3
"""Deep operator interface for the bakeoff 9 pilot lifecycle."""

from __future__ import annotations

import hashlib
import json
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import bakeoff9_grade
import bakeoff9_decision
import bakeoff9_gold
import bakeoff9_judge
import bakeoff9_pipeline
import bakeoff9_run
import bakeoff9_sdk


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAMPAIGN_DIR = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"


class CampaignError(RuntimeError):
    pass


@dataclass(frozen=True)
class CampaignReadiness:
    pilot_plan_ready: bool
    pilot_execution_available: bool
    pilot_ready_for_paid_dispatch: bool
    full_run_ready: bool
    decision_ready: bool
    blockers: tuple[tuple[str, str, str], ...]

    @property
    def pilot_ready(self) -> bool:
        """Deprecated: readiness cannot establish a run-specific preflight."""
        return False


class Bakeoff9Campaign:
    """Own plan, preflight, execution, validation, and offline grade routing."""

    def __init__(
        self,
        campaign_dir: Path = DEFAULT_CAMPAIGN_DIR,
        *,
        run_module=bakeoff9_run,
        sdk_module=bakeoff9_sdk,
        grade_module=bakeoff9_grade,
        pipeline_module=bakeoff9_pipeline,
        adapter_factory: Callable | None = None,
        preflight: Callable | None = None,
        judge_bindings: Sequence[bakeoff9_pipeline.JudgeBinding] = (),
        gold_repository=None,
        calibration_policy=None,
        decision_policy=None,
        analysis_run_dir: Path | None = None,
    ):
        self.campaign_dir = Path(campaign_dir).resolve()
        self.protocol = self.campaign_dir / "preregistration.md"
        self.declaration = self.campaign_dir / "campaign.toml"
        self.pilot_declaration = self.campaign_dir / "pilot.toml"
        self.run = run_module
        self.sdk = sdk_module
        self.grade_module = grade_module
        self.pipeline = pipeline_module
        self.adapter_factory = adapter_factory
        self.preflight = preflight
        self.judge_bindings = tuple(judge_bindings)
        # Labels reach the campaign only through the loader; there is no
        # constructor path that accepts a gold set directly.
        self.gold_repository = gold_repository or bakeoff9_gold.GoldRepository.open(
            self.campaign_dir
        )
        self.calibration_policy = calibration_policy
        self.decision_policy = decision_policy
        self.analysis_run_dir = None if analysis_run_dir is None else Path(analysis_run_dir)

    @property
    def campaign_id(self) -> str:
        return tomllib.loads(self.declaration.read_text())["campaign"]["id"]

    @property
    def protocol_frozen(self) -> bool:
        heading = "\n".join(self.protocol.read_text().splitlines()[:8]).lower()
        return "status: **frozen" in heading and "not frozen" not in heading

    def build_plan(self):
        return self.run.build_pilot_plan(self.campaign_dir, self.pilot_declaration)

    def build_full_plan(self, *, allow_draft: bool = False):
        return self.run.build_full_plan(self.campaign_dir, allow_draft=allow_draft)

    def freeze_declaration(self) -> dict:
        declaration = tomllib.loads(self.declaration.read_text())
        self.run.validate_freeze_declaration(declaration)
        return declaration["freeze"]

    def frozen_judge_configs(self, rubric: str) -> tuple[bakeoff9_judge.JudgeConfig, ...]:
        judges = self.freeze_declaration()["judges"]
        return tuple(
            bakeoff9_judge.JudgeConfig(
                provider, item["vendor"], item["model"], rubric,
                item["resolved_model_must_equal_requested"],
            )
            for provider, item in sorted(judges.items())
        )

    def frozen_calibration_policy(self) -> bakeoff9_judge.CalibrationPolicy:
        freeze = self.freeze_declaration()
        gold, calibration = freeze["gold"], freeze["calibration"]
        return bakeoff9_judge.CalibrationPolicy(
            tuple(gold["required_classes"]), gold["minimum_cases_per_class"],
            calibration["minimum_exact_agreement"],
            calibration["minimum_cohen_kappa"],
            calibration["allow_perfect_degenerate"],
            tuple(gold["reported_classes"]),
        )

    def frozen_decision_policy(self) -> bakeoff9_decision.AnalysisPolicy:
        freeze = self.freeze_declaration()
        analysis, design, tokens = freeze["analysis"], freeze["design"], freeze["tokens"]
        token_policy = bakeoff9_decision.TokenPolicy(
            tokens["name"],
            tuple(
                bakeoff9_decision.TokenTerm(field, weight)
                for field, weight in zip(tokens["terms"], tokens["weights"], strict=True)
            ),
        )
        return bakeoff9_decision.AnalysisPolicy(
            seed=analysis["seed"], iterations=analysis["iterations"],
            accept_reachable=design["accept_capable"],
            accept_limitation=design["accept_limitation"],
            interval_method=analysis["interval_method"],
            p_value_method=analysis["p_value_method"],
            h_relative_denominator=analysis["h_relative_denominator"],
            token_policy=token_policy, alpha=analysis["alpha"],
        )

    def materialize_primary_plan(self):
        return self.run.materialize_primary_plan(self.campaign_dir)

    def validate_primary_plan(self):
        return self.run.validate_primary_plan(self.campaign_dir)

    def persist_plan(self, run_dir: Path):
        plan = self.build_plan()
        store = self.run.TrialStore(Path(run_dir))
        store.write_plan(plan)
        return plan, store

    def _generator_problems(self) -> list[str]:
        try:
            declaration = tomllib.loads(self.declaration.read_text())
            adapter = self.sdk.build_generation_adapter(
                campaign_dir=self.campaign_dir, declaration=declaration
            )
        except Exception as exc:
            return [str(exc)]
        pins = declaration.get("pins") or {}
        problems = []
        if pins.get("generator_effort") != "high":
            problems.append("generator effort is not high")
        binary = Path(adapter.binary).expanduser()
        expected = pins.get("generator_binary_sha256")
        if not binary.is_file():
            problems.append(f"pinned generator binary is missing: {binary}")
        elif not isinstance(expected, str) or hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
            problems.append("pinned generator binary sha256 mismatch")
        return problems

    def readiness(self) -> CampaignReadiness:
        blockers: list[tuple[str, str, str]] = []
        try:
            self.build_plan()
            plan_ready = True
        except Exception as exc:
            plan_ready = False
            blockers.append(("pilot-declaration-invalid", "pilot", str(exc)))
        generator_problems = self._generator_problems()
        if generator_problems:
            blockers.append(
                ("generator-configuration-invalid", "pilot-execution", "; ".join(generator_problems))
            )
        pilot_execution_available = (
            plan_ready
            and not generator_problems
            and callable(self.preflight or self.sdk.synthetic_401_preflight)
            and callable(self.adapter_factory or self.sdk.build_generation_adapter)
        )
        blockers.append((
            "run-specific-preflight-required",
            "pilot-dispatch",
            "paid dispatch is not ready until this run's synthetic-401 preflight is admitted",
        ))
        try:
            self.build_full_plan(allow_draft=True)
            full_plan_ready = True
        except Exception as exc:
            full_plan_ready = False
            blockers.append(("full-run-contract-invalid", "full-run", str(exc)))
        if not self.protocol_frozen:
            blockers.append(("protocol-draft", "full-run", "the protocol header is draft — not frozen"))
        full_run_ready = full_plan_ready and self.protocol_frozen and not generator_problems
        decision_missing = []
        if len(self.judge_bindings) != 2 or len({item.config.vendor for item in self.judge_bindings}) != 2:
            decision_missing.append("two separate judge vendors")
        gold_status = self.gold_repository.readiness()
        if not gold_status.ready:
            decision_missing.append(
                "frozen gold artifact (" + "; ".join(gold_status.blockers) + ")"
            )
        if self.calibration_policy is None:
            decision_missing.append("calibration policy")
        if self.decision_policy is None:
            decision_missing.append("decision policy")
        if self.analysis_run_dir is None:
            decision_missing.append("completed run artifacts")
        else:
            try:
                plan = self.run.load_plan(self.analysis_run_dir / "plan.json")
                artifacts = self.run.load_trial_artifacts(
                    self.analysis_run_dir, plan, require_all=True
                )
                if (
                    plan.run_kind is not self.run.RunKind.CAMPAIGN
                    or len(artifacts) != 240
                    or any(not isinstance(item, self.run.CompletedTrial) for item in artifacts)
                ):
                    raise CampaignError("run is not one complete 240-trial campaign")
            except Exception as exc:
                decision_missing.append(f"complete run artifacts ({exc})")
        if decision_missing:
            blockers.append((
                "decision-inputs-unbound", "decision", "missing " + ", ".join(decision_missing)
            ))
        decision_ready = full_run_ready and not decision_missing
        return CampaignReadiness(
            plan_ready, pilot_execution_available, False,
            full_run_ready, decision_ready, tuple(blockers)
        )

    def committed(self, run_dir: Path, plan=None):
        plan = plan or self.run.load_plan(Path(run_dir) / "plan.json")
        return self.run.load_trial_artifacts(Path(run_dir), plan)

    def select_trials(
        self,
        run_dir: Path,
        plan,
        *,
        trial_ids: Sequence[str] = (),
        max_trials: int | None = None,
    ) -> tuple:
        if trial_ids and max_trials is not None:
            raise CampaignError("--trial-id and --max-trials are mutually exclusive")
        committed = {trial.trial_id for trial in self.committed(run_dir, plan)}
        requested = set(trial_ids)
        planned = {trial.trial_id for trial in plan.trials}
        unknown = sorted(requested - planned)
        if unknown:
            raise CampaignError("unknown trial ids: " + ", ".join(unknown))
        candidates = [
            trial for trial in plan.trials
            if trial.trial_id not in committed and (not requested or trial.trial_id in requested)
        ]
        if max_trials is not None:
            if max_trials < 1:
                raise CampaignError("--max-trials must be positive")
            candidates = candidates[:max_trials]
        if not candidates:
            raise CampaignError("no uncommitted planned trials were selected")
        return tuple(candidates)

    def selection_sha256(self, trials: Sequence) -> str:
        return self.run.authorized_trial_ids_sha256(
            [trial.trial_id for trial in trials]
        )

    def _bind_preflight(self, adapter, case, workspace: Path, preflight: Callable | None = None):
        receipt = (preflight or self.sdk.synthetic_401_preflight)(
            binary=adapter.binary,
            workspace=workspace,
            model=adapter.model,
            prompt=case.prompt,
            harness_prompt=case.harness_prompt,
            node_executable=adapter.node_executable,
        )
        if not isinstance(receipt, dict):
            raise CampaignError("synthetic-401 preflight returned no receipt")
        required = {
            "admitted": True,
            "surface_verdict": "match",
            "hooks_surface_neutral": True,
            "control_baseline_match": True,
            "instrumented_baseline_match": True,
            "inference_purchased": False,
        }
        if any(receipt.get(key) != value for key, value in required.items()):
            raise CampaignError("synthetic-401 preflight did not admit the instrumented surfaces")
        for key in ("baseline_sha256", "baseline_surface_key", "receipt_sha256"):
            value = receipt.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise CampaignError(f"synthetic-401 preflight lacks bound {key}")
        if not isinstance(receipt.get("binding"), dict):
            raise CampaignError("synthetic-401 preflight lacks baseline binding evidence")
        return adapter.with_preflight(receipt)

    def execute_pilot(
        self,
        run_dir: Path,
        *,
        authorization_sha256: str,
        authorization_bytes: int,
        trial_ids: Sequence[str] = (),
        max_trials: int | None = None,
        adapter=None,
        preflight: Callable | None = None,
        workspace_root: Path | None = None,
    ) -> dict:
        plan, store = self.persist_plan(run_dir)
        selected = self.select_trials(
            run_dir, plan, trial_ids=trial_ids, max_trials=max_trials
        )
        selected_ids = [trial.trial_id for trial in selected]
        authorization = self.run.PaidAuthorizationEvidence.from_digest(
            authorization_sha256,
            authorization_bytes,
            plan=plan,
            authorized_trial_ids=selected_ids,
        )
        if adapter is None:
            factory = self.adapter_factory or self.sdk.build_generation_adapter
            adapter = factory(
                campaign_dir=self.campaign_dir,
                declaration=tomllib.loads(self.declaration.read_text()),
            )

        def execute(root: Path):
            results = []
            for trial in selected:
                results.append(
                    self.run.execute_trial(
                        plan=plan,
                        trial_id=trial.trial_id,
                        store=store,
                        adapter=adapter,
                        authorization=authorization,
                        authorized_trial_ids=selected_ids,
                        workspace_root=root,
                        prepare_adapter=lambda current, case, workspace: self._bind_preflight(
                            current, case, workspace, preflight or self.preflight
                        ),
                    )
                )
            return results

        if workspace_root is None:
            with tempfile.TemporaryDirectory(prefix="bakeoff9-workspaces-", dir="/tmp") as temporary:
                results = execute(Path(temporary))
        else:
            results = execute(Path(workspace_root))
        failed = [trial for trial in results if isinstance(trial, self.run.FailedTrial)]
        if failed:
            detail = "; ".join(
                f"{trial.trial_id}: {trial.failure.get('code', 'unknown')}" for trial in failed
            )
            raise CampaignError("selected pilot trials failed: " + detail)
        if any(not isinstance(trial, self.run.CompletedTrial) for trial in results):
            raise CampaignError("selected pilot returned an unknown artifact type")
        inert = [
            trial.trial_id for trial in results
            if trial.artifact["fixture"]["contract"].get("min_tool_calls", 0) > 0
            and trial.artifact["capture"].get("executed_tool_count", 0) == 0
        ]
        if inert:
            raise CampaignError(
                "tool-requiring pilot trials executed no tools: " + ", ".join(inert)
            )
        grades = self.grade(run_dir)
        return {
            "plan": plan,
            "selected_trial_ids": selected_ids,
            "selected_trial_ids_sha256": authorization.authorized_trial_ids_sha256,
            "selected_trials": len(selected),
            "committed_trials": len(self.committed(run_dir, plan)),
            "grades": grades,
        }

    def grade(self, run_dir: Path) -> dict:
        return self.grade_module.grade_run(Path(run_dir))

    def decide(self, run_dir: Path | None = None):
        run_dir = Path(run_dir or self.analysis_run_dir) if (run_dir or self.analysis_run_dir) else None
        if run_dir is None:
            raise CampaignError("decision requires completed run artifacts")
        if any(value is None for value in (
            self.calibration_policy, self.decision_policy,
        )) or len(self.judge_bindings) != 2:
            raise CampaignError("decision judge, gold, calibration, and policy inputs are unbound")
        gold = self.gold_repository.load().gold_set
        grades = self.grade(run_dir)
        return self.pipeline.analyze_graded_run(
            grades=grades,
            trial_capsules=self.pipeline.trial_capsules_from_run(run_dir),
            gold=gold,
            judge_bindings=self.judge_bindings,
            calibration_policy=self.calibration_policy,
            decision_policy=self.decision_policy,
        )
