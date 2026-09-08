#!/usr/bin/env python3
"""Authoritative current and historical execution paths for this repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

import bakeoff9_campaign


ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN_DIR = ROOT / "campaigns" / "clause-bakeoff-9-2026-08-22"
PILOT_DECLARATION = CAMPAIGN_DIR / "pilot.toml"
RUNNER_MODULE = "bakeoff9_run"
SDK_MODULE = "bakeoff9_sdk"
DECISION_MODULE = "bakeoff9_decision"
_AUTO_IMPORT = object()


class ProtocolState(str, Enum):
    DRAFT = "draft"
    FROZEN = "frozen"


class Availability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Blocker:
    code: str
    blocks: str
    detail: str


@dataclass(frozen=True)
class CurrentExecution:
    campaign_id: str
    campaign_dir: Path
    protocol: Path
    declaration: Path
    fixture_validator: Path
    protocol_state: ProtocolState
    live_generation: Availability
    decision_analysis: Availability
    blockers: tuple[Blocker, ...]
    pilot_declaration: Path | None = None
    pilot_planning: Availability = Availability.UNAVAILABLE
    pilot_execution: Availability = Availability.UNAVAILABLE
    pilot_paid_dispatch: Availability = Availability.UNAVAILABLE

    def __post_init__(self) -> None:
        if self.protocol_state is ProtocolState.DRAFT and self.live_generation is Availability.AVAILABLE:
            raise ValueError("a draft campaign cannot expose a full run command")
        if self.pilot_execution is Availability.AVAILABLE and self.pilot_planning is Availability.UNAVAILABLE:
            raise ValueError("pilot execution requires pilot planning")
        if (
            self.pilot_paid_dispatch is Availability.AVAILABLE
            and self.pilot_execution is Availability.UNAVAILABLE
        ):
            raise ValueError("paid pilot dispatch requires an available execution path")
        if (
            self.decision_analysis is Availability.AVAILABLE
            and self.live_generation is Availability.UNAVAILABLE
        ):
            raise ValueError("decision analysis requires a complete live run path")

    @property
    def frozen(self) -> bool:
        return self.protocol_state is ProtocolState.FROZEN

    @property
    def runnable(self) -> bool:
        return self.full_run_ready

    @property
    def pilot_plan_ready(self) -> bool:
        return self.pilot_planning is Availability.AVAILABLE

    @property
    def pilot_ready(self) -> bool:
        """Deprecated: status cannot establish a run-specific preflight."""
        return False

    @property
    def pilot_execution_available(self) -> bool:
        return self.pilot_execution is Availability.AVAILABLE

    @property
    def pilot_ready_for_paid_dispatch(self) -> bool:
        return self.pilot_paid_dispatch is Availability.AVAILABLE

    @property
    def full_run_ready(self) -> bool:
        return self.frozen and self.live_generation is Availability.AVAILABLE

    @property
    def decision_ready(self) -> bool:
        return self.full_run_ready and self.decision_analysis is Availability.AVAILABLE


@dataclass(frozen=True)
class CheckResult:
    scope: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CheckReport:
    campaign_id: str
    results: tuple[CheckResult, ...]
    does_not_prove: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)


CURRENT_COMMANDS = ("status", "check", "grade")
LEGACY_SCRIPTS = {
    "generate": ROOT / "scripts" / "run_eval.py",
    "judge": ROOT / "scripts" / "judge_eval.py",
    "score": ROOT / "scripts" / "score_eval.py",
}
CHECK_SCOPES = (
    "active-campaign-binding",
    "campaign-declaration",
    "arm-input-hashes",
    "capture-spine-schema",
    "fixture-contracts-and-preconditions",
    "pilot-declaration",
    "primary-plan",
    "owner-reference-membership",
)
DOES_NOT_PROVE = (
    "the campaign can execute a paid pilot or full run",
    "a command/edit trajectory can reach the mechanical grader",
    "the current judges or decision analysis exist",
    "the owner reference has a complete pass, delayed repeat, and self-adjudication",
    "any arm is eligible or any campaign verdict is supported",
)

ACTIVE = CurrentExecution(
    campaign_id="clause-bakeoff-9-2026-08-22",
    campaign_dir=CAMPAIGN_DIR,
    protocol=CAMPAIGN_DIR / "preregistration.md",
    declaration=CAMPAIGN_DIR / "campaign.toml",
    fixture_validator=CAMPAIGN_DIR / "fixtures" / "validate.py",
    pilot_declaration=PILOT_DECLARATION,
    protocol_state=ProtocolState.DRAFT,
    live_generation=Availability.UNAVAILABLE,
    decision_analysis=Availability.UNAVAILABLE,
    blockers=(),
)


def _protocol_state(path: Path) -> ProtocolState:
    try:
        heading = "\n".join(path.read_text().splitlines()[:8]).lower()
    except OSError:
        return ProtocolState.DRAFT
    if "status: **frozen" in heading and "not frozen" not in heading:
        return ProtocolState.FROZEN
    return ProtocolState.DRAFT


def _generator_configuration_problems() -> list[str]:
    """Compatibility view; campaign readiness remains authoritative."""
    return bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir)._generator_problems()


def execution_status(
    *,
    campaign: object | None = None,
    runner_module: object = _AUTO_IMPORT,
    sdk_module: object = _AUTO_IMPORT,
    decision_module: object = _AUTO_IMPORT,
) -> CurrentExecution:
    """Project the campaign-owned readiness state onto the stable status schema."""
    del runner_module, sdk_module, decision_module
    owner = campaign or bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir)
    protocol = Path(getattr(owner, "protocol", ACTIVE.protocol))
    declaration = Path(getattr(owner, "declaration", ACTIVE.declaration))
    campaign_dir = Path(getattr(owner, "campaign_dir", ACTIVE.campaign_dir))
    campaign_id = getattr(owner, "campaign_id", ACTIVE.campaign_id)
    protocol_state = _protocol_state(protocol)
    readiness = owner.readiness()
    blockers = [Blocker(*item) for item in readiness.blockers]

    return CurrentExecution(
        campaign_id=campaign_id,
        campaign_dir=campaign_dir,
        protocol=protocol,
        declaration=declaration,
        fixture_validator=ACTIVE.fixture_validator,
        pilot_declaration=PILOT_DECLARATION,
        protocol_state=protocol_state,
        pilot_planning=Availability.AVAILABLE if readiness.pilot_plan_ready else Availability.UNAVAILABLE,
        pilot_execution=(
            Availability.AVAILABLE
            if readiness.pilot_execution_available else Availability.UNAVAILABLE
        ),
        pilot_paid_dispatch=(
            Availability.AVAILABLE
            if readiness.pilot_ready_for_paid_dispatch else Availability.UNAVAILABLE
        ),
        live_generation=Availability.AVAILABLE if readiness.full_run_ready else Availability.UNAVAILABLE,
        decision_analysis=Availability.AVAILABLE if readiness.decision_ready else Availability.UNAVAILABLE,
        blockers=tuple(blockers),
    )


def status_payload(status: CurrentExecution | None = None) -> dict:
    status = status or execution_status()
    commands = list(CURRENT_COMMANDS)
    if status.pilot_plan_ready:
        commands.append("pilot --plan-only")
    if status.pilot_execution_available:
        commands.append("pilot --execute")
    if status.full_run_ready:
        commands.append("run")
    if status.decision_ready:
        commands.append("decide")
    return {
        "active_campaign": status.campaign_id,
        "protocol": str(status.protocol.relative_to(ROOT)),
        "declaration": str(status.declaration.relative_to(ROOT)),
        "protocol_state": status.protocol_state.value,
        "frozen": status.frozen,
        "runnable": status.runnable,
        "pilot_plan_ready": status.pilot_plan_ready,
        "pilot_ready": status.pilot_ready,
        "pilot_execution_available": status.pilot_execution_available,
        "pilot_ready_for_paid_dispatch": status.pilot_ready_for_paid_dispatch,
        "full_run_ready": status.full_run_ready,
        "decision_ready": status.decision_ready,
        "pilot_planning": status.pilot_planning.value,
        "pilot_execution": status.pilot_execution.value,
        "pilot_paid_dispatch": status.pilot_paid_dispatch.value,
        "live_generation": status.live_generation.value,
        "decision_analysis": status.decision_analysis.value,
        "current_commands": commands,
        "legacy_commands": list(LEGACY_SCRIPTS),
        "offline_check_scopes": list(CHECK_SCOPES),
        "blockers": [
            {"code": item.code, "blocks": item.blocks, "detail": item.detail}
            for item in status.blockers
        ],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pilot_declaration_problems(path: Path = PILOT_DECLARATION) -> list[str]:
    """Compatibility wrapper over the campaign-owned canonical plan validation."""
    try:
        owner = bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir)
        if Path(path).resolve() != owner.pilot_declaration.resolve():
            owner.run.build_pilot_plan(owner.campaign_dir, Path(path))
        else:
            owner.build_plan()
        return []
    except Exception as exc:
        return [str(exc)]


def _pilot_declaration_check() -> CheckResult:
    problems = pilot_declaration_problems()
    return CheckResult(
        "pilot-declaration",
        not problems,
        "; ".join(problems) or "20 B1 fixtures, a1-intact, one excluded repetition",
    )


def _primary_plan_check() -> CheckResult:
    try:
        plan = bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir).validate_primary_plan()
    except Exception as exc:
        return CheckResult("primary-plan", False, str(exc))
    return CheckResult(
        "primary-plan", True,
        f"{len(plan.trials)} unique trials, sha256 {plan.plan_sha256}",
    )


def _gold_membership_check() -> CheckResult:
    try:
        import bakeoff9_gold

        membership = bakeoff9_gold.load_membership(ACTIVE.campaign_dir)
        packet = bakeoff9_gold.make_owner_packet(membership, ACTIVE.campaign_dir)
        bakeoff9_gold.validate_owner_packet(packet, membership, ACTIVE.campaign_dir)
    except Exception as exc:
        return CheckResult("owner-reference-membership", False, str(exc))
    return CheckResult(
        "owner-reference-membership", True,
        f"{len(membership.cases)} blind cases, membership sha256 {membership.membership_sha256}",
    )


def _declaration_checks() -> tuple[list[CheckResult], dict | None]:
    import campaign_spec

    try:
        spec = campaign_spec.load(ACTIVE.declaration)
    except (OSError, ValueError) as exc:
        return [CheckResult("campaign-declaration", False, str(exc))], None

    results = [
        CheckResult(
            "campaign-declaration",
            True,
            f"{len(spec['arms'])} arms, {len(spec.get('gates', []))} gates",
        )
    ]
    declared_protocol = ROOT / spec["campaign"].get("protocol", "")
    binding_problems = []
    if spec["campaign"].get("id") != ACTIVE.campaign_id:
        binding_problems.append("campaign id differs from the active route")
    if declared_protocol.resolve() != ACTIVE.protocol.resolve():
        binding_problems.append("protocol path differs from the active route")
    results.append(
        CheckResult(
            "active-campaign-binding",
            not binding_problems,
            "; ".join(binding_problems) or "declaration id and protocol match the active route",
        )
    )
    return results, spec


def _arm_hash_check(spec: dict | None) -> CheckResult:
    if spec is None:
        return CheckResult("arm-input-hashes", False, "declaration did not load")
    problems = []
    for arm in spec["arms"]:
        source = ACTIVE.campaign_dir / arm["claude_md"]
        if not source.is_file():
            problems.append(f"{arm['id']}: missing {arm['claude_md']}")
        elif _sha256(source) != arm.get("sha256"):
            problems.append(f"{arm['id']}: sha256 mismatch")
    return CheckResult(
        "arm-input-hashes",
        not problems,
        "; ".join(problems) or f"{len(spec['arms'])} declared arm files match",
    )


def _capture_spine_check(spec: dict | None) -> CheckResult:
    import capture_spine

    declared = (spec or {}).get("records", {}).get("source")
    expected = capture_spine.MANIFEST_SCHEMA_VERSION
    return CheckResult(
        "capture-spine-schema",
        declared == expected,
        f"declaration={declared!r}, implementation={expected!r}",
    )


RunCommand = Callable[..., subprocess.CompletedProcess]


def check_current(*, run: RunCommand = subprocess.run) -> CheckReport:
    """Check the current declaration and fixtures without a model or verdict."""
    declaration_results, spec = _declaration_checks()
    results = [
        *declaration_results,
        _arm_hash_check(spec),
        _capture_spine_check(spec),
        _pilot_declaration_check(),
        _primary_plan_check(),
        _gold_membership_check(),
    ]
    completed = run(
        [sys.executable, str(ACTIVE.fixture_validator)],
        cwd=ACTIVE.campaign_dir,
        capture_output=True,
        text=True,
        errors="replace",
    )
    detail = completed.stdout.strip() or completed.stderr.strip() or "no output"
    results.append(
        CheckResult(
            "fixture-contracts-and-preconditions",
            completed.returncode == 0,
            detail,
        )
    )
    return CheckReport(ACTIVE.campaign_id, tuple(results), DOES_NOT_PROVE)


def check_payload(report: CheckReport) -> dict:
    return {
        "active_campaign": report.campaign_id,
        "passed": report.passed,
        "results": [
            {"scope": item.scope, "passed": item.passed, "detail": item.detail}
            for item in report.results
        ],
        "does_not_prove": list(report.does_not_prove),
    }


def run_legacy(
    action: str,
    argv: Sequence[str],
    *,
    run: RunCommand = subprocess.run,
) -> int:
    """Forward one historical command without changing its argv or streams."""
    try:
        script = LEGACY_SCRIPTS[action]
    except KeyError as exc:
        raise ValueError(f"unknown historical action: {action}") from exc
    completed = run([sys.executable, str(script), *argv], cwd=ROOT)
    return completed.returncode


def _plan_payload(plan: object, run_dir: Path, *, executed: bool, committed: int = 0) -> dict:
    trials = list(getattr(plan, "trials"))
    return {
        "active_campaign": ACTIVE.campaign_id,
        "mode": "execute" if executed else "plan-only",
        "run_dir": str(run_dir),
        "plan_sha256": getattr(plan, "plan_sha256"),
        "trial_count": len(trials),
        "trial_ids": [getattr(trial, "trial_id") for trial in trials],
        "committed_trials": committed,
        "excluded_from_primary_analysis": True,
    }


def run_pilot(
    run_dir: Path,
    *,
    execute: bool,
    authorization_sha256: str | None = None,
    authorization_bytes: int | None = None,
    trial_ids: Sequence[str] = (),
    max_trials: int | None = None,
    campaign: object | None = None,
    runner_module: object = _AUTO_IMPORT,
    sdk_module: object = _AUTO_IMPORT,
) -> dict:
    """Compatibility wrapper over the campaign-owned pilot lifecycle."""
    del runner_module, sdk_module
    owner = campaign or bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir)
    if execute and (authorization_sha256 is None or authorization_bytes is None):
        raise ValueError("pilot execution requires authorization sha256 and byte count")
    if not execute:
        plan, _store = owner.persist_plan(Path(run_dir))
        selected = (
            owner.select_trials(
                Path(run_dir), plan, trial_ids=trial_ids, max_trials=max_trials
            )
            if trial_ids or max_trials is not None
            else tuple(plan.trials)
        )
        payload = _plan_payload(plan, Path(run_dir), executed=False)
        selected_ids = [trial.trial_id for trial in selected]
        payload.update(
            selected_trials=len(selected_ids),
            selected_trial_ids=selected_ids,
            selected_trial_ids_sha256=owner.selection_sha256(selected),
        )
        return payload
    result = owner.execute_pilot(
        Path(run_dir),
        authorization_sha256=authorization_sha256,
        authorization_bytes=authorization_bytes,
        trial_ids=trial_ids,
        max_trials=max_trials,
    )
    payload = _plan_payload(
        result["plan"], Path(run_dir), executed=True, committed=result["committed_trials"]
    )
    payload.update(
        selected_trials=result["selected_trials"],
        selected_trial_ids=result["selected_trial_ids"],
        selected_trial_ids_sha256=result["selected_trial_ids_sha256"],
        graded_trials=result["grades"]["graded_trials"],
    )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="show the active campaign and capabilities")
    status.add_argument("--json", action="store_true", help="emit machine-readable status")
    check = subparsers.add_parser("check", help="run the active campaign's offline checks")
    check.add_argument("--json", action="store_true", help="emit a machine-readable report")
    pilot = subparsers.add_parser("pilot", help="plan or execute the excluded A1 pilot")
    pilot.add_argument("--run-dir", type=Path, required=True)
    pilot_mode = pilot.add_mutually_exclusive_group(required=True)
    pilot_mode.add_argument("--plan-only", action="store_true")
    pilot_mode.add_argument("--execute", action="store_true")
    pilot.add_argument("--authorization-sha256")
    pilot.add_argument("--authorization-bytes", type=int)
    selection = pilot.add_mutually_exclusive_group()
    selection.add_argument("--trial-id", action="append", default=[])
    selection.add_argument("--max-trials", type=int)
    pilot.add_argument("--json", action="store_true", help="emit machine-readable output")
    grade = subparsers.add_parser("grade", help="grade committed bakeoff 9 trial capsules")
    grade.add_argument("--run-dir", type=Path, required=True)
    grade.add_argument("--out", type=Path)
    grade.add_argument("--json", action="store_true", help="emit machine-readable output")
    subparsers.add_parser("run", help="full run (capability-gated until protocol freeze)")
    decide = subparsers.add_parser("decide", help="decision analysis (capability-gated)")
    decide.add_argument("--run-dir", type=Path, required=True)
    decide.add_argument("--json", action="store_true", help="emit machine-readable output")
    legacy = subparsers.add_parser("legacy", help="run the historical control/STE pipeline")
    legacy.add_argument("action", choices=tuple(LEGACY_SCRIPTS))
    legacy.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def _print_status(payload: dict) -> None:
    print(f"active campaign: {payload['active_campaign']}")
    print(f"protocol: {payload['protocol']}")
    print(f"protocol state: {payload['protocol_state']}")
    print(f"frozen: {'yes' if payload['frozen'] else 'no'}")
    print(f"pilot-plan-ready: {'yes' if payload['pilot_plan_ready'] else 'no'}")
    print(f"pilot-ready: {'yes' if payload['pilot_ready'] else 'no'}")
    print(
        "pilot-execution-available: "
        + ("yes" if payload["pilot_execution_available"] else "no")
    )
    print(
        "pilot-ready-for-paid-dispatch: "
        + ("yes" if payload["pilot_ready_for_paid_dispatch"] else "no")
    )
    print(f"full-run-ready: {'yes' if payload['full_run_ready'] else 'no'}")
    print(f"runnable: {'yes' if payload['runnable'] else 'no'}")
    print(f"decision-ready: {'yes' if payload['decision_ready'] else 'no'}")
    print(f"available now: {', '.join(payload['current_commands'])}")
    print("offline check scopes: " + ", ".join(payload["offline_check_scopes"]))
    print("blockers:")
    for item in payload["blockers"]:
        print(f"  {item['code']} [{item['blocks']}]: {item['detail']}")


def _print_check(report: CheckReport) -> None:
    for result in report.results:
        label = "pass" if result.passed else "fail"
        print(f"[{label}] {result.scope}: {result.detail}")
    print("does not prove:")
    for claim in report.does_not_prove:
        print(f"  {claim}")


def _print_pilot(payload: dict) -> None:
    print(f"pilot mode: {payload['mode']}")
    print(f"run dir: {payload['run_dir']}")
    print(f"plan sha256: {payload['plan_sha256']}")
    print(f"trials: {payload['trial_count']}")
    if payload["mode"] == "execute":
        print(f"committed trials: {payload['committed_trials']}")


def _capability_error(status: CurrentExecution, capability: str) -> str:
    scopes = {
        "pilot": {"pilot", "pilot-execution"},
        "full-run": {"pilot", "pilot-execution", "full-run"},
        "decision": {"pilot", "pilot-execution", "full-run", "decision"},
    }[capability]
    details = [item.detail for item in status.blockers if item.blocks in scopes]
    return "; ".join(details) or f"{capability} is unavailable"


def main(argv: Sequence[str] | None = None, *, campaign: object | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "status":
        payload = status_payload(execution_status(campaign=campaign))
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            _print_status(payload)
        return 0
    if args.command == "check":
        report = check_current()
        if args.json:
            print(json.dumps(check_payload(report), indent=2))
        else:
            _print_check(report)
        return 0 if report.passed else 1
    if args.command == "pilot":
        if args.execute:
            if args.authorization_sha256 is None or args.authorization_bytes is None:
                print(
                    "pilot execution requires --authorization-sha256 and --authorization-bytes",
                    file=sys.stderr,
                )
                return 2
            if (
                len(args.authorization_sha256) != 64
                or any(character not in "0123456789abcdef" for character in args.authorization_sha256)
                or args.authorization_bytes < 1
            ):
                print("pilot authorization metadata is invalid", file=sys.stderr)
                return 2
            status = execution_status(campaign=campaign)
            if not status.pilot_execution_available:
                print("pilot execution unavailable: " + _capability_error(status, "pilot"), file=sys.stderr)
                return 2
        try:
            payload = run_pilot(
                args.run_dir,
                execute=args.execute,
                authorization_sha256=args.authorization_sha256,
                authorization_bytes=args.authorization_bytes,
                trial_ids=args.trial_id,
                max_trials=args.max_trials,
                campaign=campaign,
            )
        except Exception as exc:
            print(f"pilot unavailable: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            _print_pilot(payload)
        return 0
    if args.command == "grade":
        owner = campaign or bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir)
        try:
            payload = owner.grade(args.run_dir)
            if args.out:
                owner.grade_module.write_grades(args.out, payload)
        except Exception as exc:
            print(f"grade unavailable: {exc}", file=sys.stderr)
            return 2
        if args.json or not args.out:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "run":
        status = execution_status(campaign=campaign)
        if not status.full_run_ready:
            print("full run unavailable: " + _capability_error(status, "full-run"), file=sys.stderr)
            return 2
        print("full run route is not implemented", file=sys.stderr)
        return 2
    if args.command == "decide":
        status = execution_status(campaign=campaign)
        if not status.decision_ready:
            print("decision unavailable: " + _capability_error(status, "decision"), file=sys.stderr)
            return 2
        owner = campaign or bakeoff9_campaign.Bakeoff9Campaign(ACTIVE.campaign_dir)
        try:
            result = owner.decide(args.run_dir)
        except Exception as exc:
            print(f"decision unavailable: {exc}", file=sys.stderr)
            return 2
        payload = result.to_dict() if hasattr(result, "to_dict") else result
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    return run_legacy(args.action, args.args)


if __name__ == "__main__":
    raise SystemExit(main())
