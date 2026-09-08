#!/usr/bin/env python3
"""Validate the bakeoff 11 probes and prove each hidden oracle is live.

Interpreter: refuses to run under anything but Python 3.14.5, the version the
campaign pins, and runs every oracle with this same interpreter as the harness
does (argv[0] "python3" is substituted with sys.executable).

For every probe under ../probes/<id>/:

- the seed is copied to a fresh directory outside $HOME, oracle/ is copied in
  and run with the fixture's argv (``python3 -I -B oracle/run.py``); the seed
  must FAIL (exit non-zero), except for a no-edit probe, whose reference/
  holds only a README.md and whose seed must PASS;
- every ``reference*/`` directory is overlaid onto a fresh copy of the seed and
  the oracle must PASS (a probe with an open boundary carries one overlay per
  reading);
- hash pins inside oracle/check.py (``SEED`` or ``PINNED`` dicts) are
  recomputed from the seed bytes and must match; a ``SEED`` pin must cover
  every seed file;
- capture_spine.redact() is the identity over every byte of every file and
  is_auth_shaped_key is false for every path component and JSON key;
- no prompt and no must_cover string contains a tail title or an offer phrase
  (frozen regexes below), or the words the prompt-hygiene checklist bans;
- no __pycache__, *.pyc, .DS_Store, or symlink anywhere in the probe tree; the
  seed has no CLAUDE.md, oracle/, sitecustomize.py, usercustomize.py, or a
  file named after a stdlib module the oracle imports; the README states the
  test command verbatim; the seed stays under SEED_LINE_LIMIT lines.

Prints one line per oracle run with exit code and wall time, then
"N probes, 0 problems" and exits 0 on success.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # check_pins imports each check.py; leave no __pycache__ behind
HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
PROBES = CAMPAIGN / "probes"
REPO = CAMPAIGN.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from capture_spine import is_auth_shaped_key, redact  # noqa: E402

PINNED_PYTHON = "3.14.5"
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
SEED_LINE_LIMIT = 150
TEST_COMMAND = "python3 -m unittest discover -s tests -t ."
ORACLE_ARGV = ["python3", "-I", "-B", "oracle/run.py"]
TAIL_TITLE = re.compile(
    r"\b(?:next steps?|changes? (?:needed|required)|summary|in summary|notes?|what i did|"
    r"what changed|recommendations?|follow[- ]?ups?|caveats?|remaining work|open questions?|"
    r"what'?s left|what is left|limitations?|further work|future work|suggestions?|tl;?dr|"
    r"conclusion|other observations|additional notes?)\b", re.I)
OFFER = re.compile(
    r"\b(?:let me know|happy to|want me to|shall i|if you'd like|if you would like|feel free|"
    r"would you like me to|i can also)\b", re.I)
PROMPT_BANNED = re.compile(r"recommend|summar|heading|bullet|concise|brief|check\.py|oracle", re.I)
FORBIDDEN_SEED_NAMES = {"CLAUDE.md", "oracle", "sitecustomize.py", "usercustomize.py",
                        "unittest.py", "json.py", "hashlib.py", "subprocess.py", "tempfile.py",
                        "pathlib.py", "datetime.py", "os.py", "sys.py"}
JUNK_NAMES = {"__pycache__", ".DS_Store"}
# The oracle runs with a clean environment; PATH is kept so python3 resolves.
CLEAN_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1"}


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_no_edit(reference: Path) -> bool:
    return [p.relative_to(reference).as_posix() for p in files_under(reference)] == ["README.md"]


def references(probe: Path) -> list[Path]:
    return sorted(p for p in probe.iterdir() if p.is_dir() and p.name.startswith("reference"))


def check_tree(probe: Path, errors: list[str]) -> None:
    name = probe.name
    for path in probe.rglob("*"):
        rel = path.relative_to(probe)
        if path.is_symlink():
            errors.append(f"{name}: {rel} is a symlink")
        if path.name in JUNK_NAMES or path.suffix == ".pyc":
            errors.append(f"{name}: {rel} must not be in the probe tree")
    seed = probe / "seed"
    if seed.is_dir():
        for path in seed.rglob("*"):
            if path.name in FORBIDDEN_SEED_NAMES:
                errors.append(f"{name}: seed must not contain {path.relative_to(probe)}")


def check_shape(probe: Path, fixture: dict, errors: list[str]) -> None:
    name = probe.name
    if not ID.fullmatch(name):
        errors.append(f"{name}: id must match [a-z0-9][a-z0-9-]*")
    if set(fixture) != {"prompt", "oracle"}:
        errors.append(f"{name}: fixture.json keys must be exactly prompt and oracle")
    prompt = fixture.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append(f"{name}: prompt must be a non-empty string")
        prompt = ""
    oracle = fixture.get("oracle")
    if not isinstance(oracle, dict) or set(oracle) != {"argv", "timeout_seconds"}:
        errors.append(f"{name}: oracle must have exactly argv and timeout_seconds")
    else:
        if oracle["argv"] != ORACLE_ARGV:
            errors.append(f"{name}: oracle argv must be {ORACLE_ARGV}")
        if not isinstance(oracle["timeout_seconds"], int) or oracle["timeout_seconds"] < 1:
            errors.append(f"{name}: oracle timeout_seconds must be a positive integer")
    seed, oracle_dir = probe / "seed", probe / "oracle"
    for path, what in ((seed, "seed"), (oracle_dir, "oracle")):
        if not path.is_dir():
            errors.append(f"{name}: {what}/ must be a directory")
    refs = references(probe)
    if not refs or any(not files_under(r) for r in refs):
        errors.append(f"{name}: at least one non-empty reference*/ directory is required")
    for required in ("__init__.py", "check.py", "run.py"):
        if not (oracle_dir / required).is_file():
            errors.append(f"{name}: oracle/{required} is missing")
    readme = seed / "README.md"
    if not readme.is_file() or TEST_COMMAND not in readme.read_text():
        errors.append(f"{name}: seed/README.md must state the test command {TEST_COMMAND!r}")
    if seed.is_dir():
        lines = sum(len(p.read_bytes().splitlines()) for p in files_under(seed))
        if lines > SEED_LINE_LIMIT:
            errors.append(f"{name}: seed is {lines} lines, over the {SEED_LINE_LIMIT} limit")
    try:
        cover = json.loads((probe / "must-cover.json").read_text())
    except (OSError, ValueError) as exc:
        errors.append(f"{name}: must-cover.json unreadable: {exc}")
        return
    items = cover.get("must_cover") if isinstance(cover, dict) else None
    if not isinstance(cover, dict) or set(cover) != {"must_cover"} or not isinstance(items, list) \
            or not items or not all(isinstance(i, str) and i.strip() for i in items):
        errors.append(f"{name}: must-cover.json must be {{\"must_cover\": [non-empty strings]}}")
        return
    texts = [("prompt", prompt)] + [(f"must_cover[{i}]", s) for i, s in enumerate(items)]
    for label, text in texts:
        hit = TAIL_TITLE.search(text)
        if hit:
            errors.append(f"{name}: {label} contains tail title {hit.group(0)!r}")
        hit = OFFER.search(text)
        if hit:
            errors.append(f"{name}: {label} contains offer phrase {hit.group(0)!r}")
    hit = PROMPT_BANNED.search(prompt)
    if hit:
        errors.append(f"{name}: prompt contains banned word {hit.group(0)!r}")


def check_sanitizer(probe: Path, errors: list[str]) -> int:
    """Return the number of files scanned."""
    name = probe.name
    scanned = 0
    for path in files_under(probe):
        rel = path.relative_to(probe)
        scanned += 1
        for part in rel.parts:
            if is_auth_shaped_key(part):
                errors.append(f"{name}: path component {part!r} in {rel} is authorization-shaped")
        text = path.read_bytes().decode("utf-8", errors="surrogateescape")
        if redact(text) != text:
            errors.append(f"{name}: {rel} carries credential-shaped text the sanitizer would rewrite")
        if path.suffix == ".json":
            try:
                for key in json_keys(json.loads(text)):
                    if is_auth_shaped_key(key):
                        errors.append(f"{name}: JSON key {key!r} in {rel} is authorization-shaped")
            except ValueError as exc:
                errors.append(f"{name}: {rel} is not valid JSON: {exc}")
    return scanned


def json_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from json_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from json_keys(item)


def check_pins(probe: Path, errors: list[str]) -> None:
    """Recompute any sha256 pins inside oracle/check.py from the seed bytes."""
    name = probe.name
    spec = importlib.util.spec_from_file_location(f"pins_{name.replace('-', '_')}", probe / "oracle" / "check.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - any import failure is a fixture defect
        errors.append(f"{name}: oracle/check.py does not import: {exc!r}")
        return
    seed = probe / "seed"
    actual = {p.relative_to(seed).as_posix(): sha256(p) for p in files_under(seed)}
    pinned_all = getattr(module, "SEED", None)
    if pinned_all is not None and pinned_all != actual:
        errors.append(f"{name}: oracle SEED pins do not match the seed bytes or file list")
    pinned_some = getattr(module, "PINNED", None)
    if pinned_some is not None:
        for rel, digest in pinned_some.items():
            if actual.get(rel) != digest:
                errors.append(f"{name}: oracle PINNED[{rel!r}] does not match the seed bytes")


def run_oracle(probe: Path, fixture: dict, overlay: Path | None) -> tuple[subprocess.CompletedProcess, float]:
    home = str(Path.home().resolve())
    with tempfile.TemporaryDirectory(prefix="bakeoff11-probe-") as tmp:
        if str(Path(tmp).resolve()).startswith(home):
            raise RuntimeError(f"temp root is inside $HOME: {tmp}")
        workspace = Path(tmp) / "workspace"
        shutil.copytree(probe / "seed", workspace)
        if overlay is not None:
            shutil.copytree(overlay, workspace, dirs_exist_ok=True)
        for cache in workspace.rglob("__pycache__"):
            shutil.rmtree(cache)
        shutil.copytree(probe / "oracle", workspace / "oracle")
        argv = [sys.executable if a == "python3" else a for a in fixture["oracle"]["argv"]]
        started = time.monotonic()
        done = subprocess.run(
            argv, cwd=workspace, env=CLEAN_ENV, capture_output=True, text=True,
            timeout=fixture["oracle"]["timeout_seconds"],
        )
        return done, time.monotonic() - started


def check_oracle(probe: Path, fixture: dict, errors: list[str]) -> None:
    name = probe.name
    refs = references(probe)
    no_edit = len(refs) == 1 and is_no_edit(refs[0])
    runs: list[tuple[str, Path | None, bool]] = [("seed", None, no_edit)]
    if not no_edit:
        runs += [(ref.name, ref, True) for ref in refs]
    for label, overlay, expect_pass in runs:
        try:
            done, seconds = run_oracle(probe, fixture, overlay)
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as exc:
            errors.append(f"{name}: oracle could not run on {label}: {exc}")
            continue
        verdict = "pass" if done.returncode == 0 else "fail"
        print(f"  {name:26} {label:30} exit={done.returncode} ({verdict}, {seconds:.2f}s)")
        if expect_pass and done.returncode != 0:
            errors.append(f"{name}: {label} must pass the oracle; exit {done.returncode}\n{done.stderr[-600:]}")
        if not expect_pass and done.returncode == 0:
            errors.append(f"{name}: the unmodified seed already passes the oracle; the task is not live")


def main() -> int:
    print(f"interpreter: {sys.executable} ({platform.python_version()})")
    if platform.python_version() != PINNED_PYTHON:
        print(f"refusing: campaign pins Python {PINNED_PYTHON}; this is {platform.python_version()}")
        return 2
    errors: list[str] = []
    probes = sorted(p for p in PROBES.iterdir() if p.is_dir()) if PROBES.is_dir() else []
    if not probes:
        errors.append("no probes found under probes/")
    scanned = 0
    for probe in probes:
        before = len(errors)
        try:
            fixture = json.loads((probe / "fixture.json").read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"{probe.name}: fixture.json unreadable: {exc}")
            continue
        check_tree(probe, errors)
        check_shape(probe, fixture, errors)
        scanned += check_sanitizer(probe, errors)
        if len(errors) == before:
            check_pins(probe, errors)
            check_oracle(probe, fixture, errors)
        else:
            errors.append(f"{probe.name}: oracle run skipped because tree, shape, or sanitizer checks failed")
    sanitizer_clean = not any("credential-shaped" in e for e in errors)
    keys_clean = not any("authorization-shaped" in e for e in errors)
    print(f"redact identity: {'ok' if sanitizer_clean else 'FAILED'} ({scanned} files)")
    print(f"auth-shaped keys: {'none' if keys_clean else 'FOUND'}")
    for error in errors:
        print(error)
    print(f"{len(probes)} probes, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
