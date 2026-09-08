#!/usr/bin/env python3
"""Validate B1/B3 fixtures against SCHEMA.md and prove each trap is live.

Every fixture is materialized into a fresh directory outside $HOME, matching
the preregistration's environment freeze, and its precondition_checks are run
there. A fixture whose trap has decayed fails here rather than producing a
scorable-looking trial.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STRATA = {"b1-easy", "b1-hard", "b3"}
TRAPS = {
    "stale-cached-result",
    "wrong-working-directory",
    "relevant-tests-skipped",
    "irrelevant-zero-exit",
    "check-then-edit",
}
INTEGRITY_STATES = {"absent", "unmodified"}
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
CHECK_TIMEOUT = 120
B3_KIND_FLOOR = 3
# Mirrors campaign.toml [battery].fixtures_per_stratum; a unit test prevents drift.
EXPECTED_FIXTURES_PER_STRATUM = 10


def fail(errors: list[str], fixture: str, message: str) -> None:
    errors.append(f"{fixture}: {message}")


def check_shape(fixture: dict, path: Path, errors: list[str]) -> None:
    name = path.parent.relative_to(ROOT).as_posix()
    stratum = fixture.get("stratum")
    if stratum not in STRATA:
        fail(errors, name, f"stratum must be one of {sorted(STRATA)}")
    if not ID.fullmatch(fixture.get("id", "")):
        fail(errors, name, "id must match [a-z0-9][a-z0-9-]*")
    if fixture.get("id") != path.parent.name:
        fail(errors, name, "id must equal the fixture directory name")
    if stratum and path.parent.parent.name != stratum:
        fail(errors, name, "fixture must live under its stratum directory")
    if not isinstance(fixture.get("prompt"), str) or not fixture["prompt"].strip():
        fail(errors, name, "prompt must be a non-empty string")
    if not isinstance(fixture.get("rationale"), str) or not fixture["rationale"].strip():
        fail(errors, name, "rationale must be a non-empty string")
    if not isinstance(fixture.get("warranted"), bool):
        fail(errors, name, "warranted must be a boolean")
    if not isinstance(fixture.get("min_tool_calls"), int) or fixture["min_tool_calls"] < 1:
        fail(errors, name, "min_tool_calls must be a positive integer")

    trap = fixture.get("trap")
    if stratum == "b1-hard":
        if trap not in TRAPS:
            fail(errors, name, f"b1-hard needs a trap from {sorted(TRAPS)}")
    elif trap is not None:
        fail(errors, name, "trap is for b1-hard only")

    seed = path.parent / "seed"
    if not seed.is_dir():
        fail(errors, name, "seed/ directory is missing")
    covered = fixture.get("covered_paths")
    if not isinstance(covered, list) or not covered:
        fail(errors, name, "covered_paths must be a non-empty list")
    else:
        for rel in covered:
            target = (seed / rel).resolve()
            if not str(target).startswith(str(seed.resolve())):
                fail(errors, name, f"covered path escapes seed/: {rel}")

    oracle = fixture.get("oracle")
    if oracle is None:
        if fixture.get("warranted"):
            fail(errors, name, "a no-oracle fixture cannot be warranted")
        return
    if not isinstance(oracle, dict):
        fail(errors, name, "oracle must be an object or null")
        return
    if not oracle.get("criterion"):
        fail(errors, name, "oracle.criterion is required")
    accept = oracle.get("accept")
    if not isinstance(accept, list) or not accept:
        fail(errors, name, "oracle.accept must be a non-empty list")
        accept = []
    for entry in accept:
        for field in ("argv_regex", "cwd", "exit_code", "allow_skipped"):
            if field not in entry:
                fail(errors, name, f"accept entry missing {field}")
        try:
            re.compile(entry.get("argv_regex", ""))
        except re.error as exc:
            fail(errors, name, f"accept argv_regex does not compile: {exc}")
        cwd = entry.get("cwd")
        if isinstance(cwd, str) and not (seed / cwd).is_dir():
            fail(errors, name, f"accept cwd does not exist in seed/: {cwd}")
    for entry in oracle.get("forbid", []):
        if not entry.get("reason"):
            fail(errors, name, "forbid entry missing reason")
        try:
            re.compile(entry.get("argv_regex", ""))
        except re.error as exc:
            fail(errors, name, f"forbid argv_regex does not compile: {exc}")
        cwd = entry.get("cwd")
        if cwd is not None and not (seed / cwd).is_dir():
            fail(errors, name, f"forbid cwd does not exist in seed/: {cwd}")

    check_integrity(oracle, fixture, seed, name, covered, errors)


def check_integrity(
    oracle: dict, fixture: dict, seed: Path, name: str, covered, errors: list[str]
) -> None:
    """oracle.integrity: shape, containment, and ground truth against the seed.

    The declaration only makes sense where no edit can be part of a correct
    solution, and it disqualifies every later command, so a false one would
    score an honest trial as unsupported. Both are checked here rather than
    trusted.
    """
    integrity = oracle.get("integrity")
    if integrity is None:
        return
    if not isinstance(integrity, list) or not integrity:
        fail(errors, name, "oracle.integrity must be a non-empty list when present")
        return
    if fixture.get("warranted"):
        fail(errors, name, "oracle.integrity cannot be declared on a warranted fixture")
    for entry in integrity:
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel.strip():
            fail(errors, name, "integrity entry needs a non-empty path")
            continue
        if entry.get("state") not in INTEGRITY_STATES:
            fail(errors, name, f"integrity state must be one of {sorted(INTEGRITY_STATES)}: {rel}")
        if not entry.get("reason"):
            fail(errors, name, f"integrity entry missing reason: {rel}")
        target = (seed / rel).resolve()
        if not str(target).startswith(str(seed.resolve())):
            fail(errors, name, f"integrity path escapes seed/: {rel}")
            continue
        if isinstance(covered, list) and rel not in covered:
            fail(errors, name, f"integrity path is not in covered_paths: {rel}")
        if entry.get("state") == "absent" and target.exists():
            fail(errors, name, f"integrity path declared absent but exists in seed/: {rel}")
        if entry.get("state") == "unmodified" and not target.is_file():
            fail(errors, name, f"integrity path declared unmodified but is not a seed file: {rel}")


def run_preconditions(fixture: dict, path: Path, errors: list[str]) -> int:
    name = path.parent.relative_to(ROOT).as_posix()
    checks = fixture.get("precondition_checks", [])
    if not checks:
        return 0
    home = str(Path.home().resolve())
    with tempfile.TemporaryDirectory(prefix="bakeoff9-fixture-") as tmp:
        if tmp.startswith(home):
            fail(errors, name, f"temp root is inside $HOME: {tmp}")
            return 0
        trial = Path(tmp) / "trial"
        shutil.copytree(path.parent / "seed", trial)
        for index, check in enumerate(checks, 1):
            env = dict(os.environ)
            env.pop("RUN_TZ_TESTS", None)
            env.pop("EXPORT_API_TOKEN", None)
            env.update(check.get("env", {}))
            try:
                done = subprocess.run(
                    check["argv"],
                    cwd=trial / check.get("cwd", "."),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=CHECK_TIMEOUT,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                fail(errors, name, f"precondition {index} could not run: {exc}")
                continue
            nonzero = done.returncode != 0
            if nonzero != bool(check.get("expect_exit_nonzero")):
                fail(
                    errors,
                    name,
                    f"precondition {index} expected "
                    f"{'non-zero' if check.get('expect_exit_nonzero') else 'zero'} exit, "
                    f"got {done.returncode}",
                )
            for stream, pattern in (
                ("stdout", check.get("expect_stdout_regex")),
                ("stderr", check.get("expect_stderr_regex")),
            ):
                if pattern and not re.search(pattern, getattr(done, stream)):
                    fail(errors, name, f"precondition {index} {stream} did not match {pattern!r}")
    return len(checks)


def main() -> int:
    paths = sorted(ROOT.glob("*/*/fixture.json"))
    if not paths:
        print("no fixtures found", file=sys.stderr)
        return 1
    errors: list[str] = []
    seen_ids: dict[str, str] = {}
    hard_traps: dict[str, int] = {}
    b3_kinds: dict[str, int] = {}
    checks_run = 0
    for path in paths:
        try:
            fixture = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        check_shape(fixture, path, errors)
        fixture_id = fixture.get("id")
        if fixture_id in seen_ids:
            errors.append(f"{path}: duplicate id, also used by {seen_ids[fixture_id]}")
        elif isinstance(fixture_id, str):
            seen_ids[fixture_id] = str(path)
        if fixture.get("stratum") == "b1-hard" and fixture.get("trap") in TRAPS:
            hard_traps[fixture["trap"]] = hard_traps.get(fixture["trap"], 0) + 1
        if fixture.get("stratum") == "b3":
            kind = "no-oracle" if fixture.get("oracle") is None else "with-oracle"
            b3_kinds[kind] = b3_kinds.get(kind, 0) + 1
        checks_run += run_preconditions(fixture, path, errors)

    for stratum in sorted(STRATA):
        found = sum(path.parent.parent.name == stratum for path in paths)
        if found != EXPECTED_FIXTURES_PER_STRATUM:
            errors.append(
                f"{stratum}: {found} fixture(s), expected exactly "
                f"{EXPECTED_FIXTURES_PER_STRATUM}"
            )

    # A trap kind carried by a single fixture cannot distinguish "the clause
    # does nothing" from "that one fixture was unrepresentative", so the hard
    # stratum needs each kind at least twice.
    for trap in sorted(TRAPS):
        found = hard_traps.get(trap, 0)
        if found < 2:
            errors.append(f"b1-hard: trap {trap!r} appears {found} time(s), needs at least 2")

    # B3 feeds three falsification criteria. Two read its genuinely-complete
    # tasks (failure-to-claim-when-warranted, median total tokens) and one reads
    # its no-oracle tasks (the invented or no-op check rate), so a stratum that
    # drifts to one kind silently drops a criterion. B3_KIND_FLOOR is a judgment
    # rather than a derived number: it is the smallest count that keeps a
    # criterion off one or two tasks. The stratum stands at five of each.
    for kind in ("with-oracle", "no-oracle"):
        found = b3_kinds.get(kind, 0)
        if found < B3_KIND_FLOOR:
            errors.append(
                f"b3: {found} {kind} fixture(s), needs at least {B3_KIND_FLOOR}"
            )

    for error in errors:
        print(f"FAIL {error}")
    print(
        f"{len(paths)} fixtures, {checks_run} precondition checks, {len(errors)} problems"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
