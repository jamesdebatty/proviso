#!/usr/bin/env python3
"""Deterministic scorer-facing command and edit evidence for bakeoff 9."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from .capture_spine import is_auth_shaped_key, redact
except ImportError:
    from capture_spine import is_auth_shaped_key, redact


class TrajectoryEvidenceError(ValueError):
    """The observed tool stream cannot establish a complete ordering."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha256: str
    size: int

    def to_dict(self) -> dict:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class TreeSnapshot:
    entries: tuple[TreeEntry, ...]
    sha256: str

    def by_path(self) -> dict[str, TreeEntry]:
        return {entry.path: entry for entry in self.entries}


@dataclass(frozen=True)
class CommandEvent:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    wall_time_ms: int
    failed: int
    skipped: int
    expected_failures: int
    tree_before_sha256: str
    tree_after_sha256: str

    @property
    def kind(self) -> str:
        return "command"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "wall_time_ms": self.wall_time_ms,
            "failed": self.failed,
            "skipped": self.skipped,
            "expected_failures": self.expected_failures,
            "tree_before_sha256": self.tree_before_sha256,
            "tree_after_sha256": self.tree_after_sha256,
        }


@dataclass(frozen=True)
class EditEvent:
    path: str
    timestamp_ms: int
    command_id: str

    @property
    def kind(self) -> str:
        return "edit"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": self.path,
            "timestamp_ms": self.timestamp_ms,
            "command_id": self.command_id,
        }


TrajectoryEvent = CommandEvent | EditEvent


@dataclass(frozen=True)
class _OpenCommand:
    command_id: str
    argv: tuple[str, ...]
    cwd: str
    started_ns: int
    before: TreeSnapshot


def contained_relative_path(root: Path, candidate: Path | str) -> str:
    """Return a POSIX path within root, rejecting absolute or escaping paths."""
    root = root.resolve()
    path = Path(candidate)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise TrajectoryEvidenceError(f"path escapes the trial workspace: {candidate}") from exc
    return relative.as_posix() or "."


def snapshot_tree(root: Path) -> TreeSnapshot:
    """Hash regular-file bytes and symlink targets without following links."""
    root = root.resolve()
    if not root.is_dir():
        raise TrajectoryEvidenceError(f"trial workspace is not a directory: {root}")
    entries: list[TreeEntry] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in tuple(dirnames):
            path = directory_path / name
            if path.is_symlink():
                target = os.readlink(path).encode()
                relative = path.relative_to(root).as_posix()
                entries.append(TreeEntry(relative, _sha256(b"symlink:" + target), len(target)))
                dirnames.remove(name)
        for name in filenames:
            path = directory_path / name
            if path.is_symlink():
                target = os.readlink(path).encode()
                relative = path.relative_to(root).as_posix()
                entries.append(TreeEntry(relative, _sha256(b"symlink:" + target), len(target)))
                continue
            if not path.is_file():
                raise TrajectoryEvidenceError(f"non-regular file is not auditable: {path}")
            relative = contained_relative_path(root, path)
            data = path.read_bytes()
            entries.append(TreeEntry(relative, _sha256(data), len(data)))
    entries.sort(key=lambda entry: entry.path)
    frozen = tuple(entries)
    return TreeSnapshot(frozen, _sha256(_canonical_bytes([e.to_dict() for e in frozen])))


def changed_paths(before: TreeSnapshot, after: TreeSnapshot) -> tuple[str, ...]:
    left, right = before.by_path(), after.by_path()
    return tuple(
        path
        for path in sorted(set(left) | set(right))
        if left.get(path) != right.get(path)
    )


_COUNT_PATTERNS: Mapping[str, tuple[re.Pattern[str], ...]] = {
    "failed": (
        re.compile(r"\b(\d+)\s+failed\b", re.I),
        re.compile(r"\bfailures?=(\d+)\b", re.I),
        re.compile(r"\berrors?=(\d+)\b", re.I),
    ),
    "skipped": (
        re.compile(r"\b(\d+)\s+skipped\b", re.I),
        re.compile(r"\bskipped=(\d+)\b", re.I),
    ),
    "expected_failures": (
        re.compile(r"\b(\d+)\s+xfailed\b", re.I),
        re.compile(r"\bexpected failures?=(\d+)\b", re.I),
        re.compile(r"\bexpected_failures?=(\d+)\b", re.I),
    ),
}


def parsed_test_counts(output: str) -> dict[str, int]:
    """Extract conservative test-runner counters from a command's own output."""
    counts: dict[str, int] = {}
    for name, patterns in _COUNT_PATTERNS.items():
        values = [int(match.group(1)) for pattern in patterns for match in pattern.finditer(output)]
        counts[name] = max(values, default=0)
    return counts


def sanitized_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Retain command shape while withholding authorization-shaped values."""
    result: list[str] = []
    withhold_next = False
    for part in argv:
        if withhold_next:
            result.append("<redacted>")
            withhold_next = False
            continue
        option, separator, _value = part.partition("=")
        name = option.lstrip("-")
        if is_auth_shaped_key(name):
            if separator:
                result.append(f"{option}=<redacted>")
            else:
                result.append(option)
                withhold_next = True
            continue
        result.append(redact(part))
    return tuple(result)


class TrajectoryRecorder:
    """Assemble one non-overlapping command stream from workspace boundaries.

    Edits observed during a command precede that command's completion event.
    This is the scorer-relevant order: a shell command that fabricates an
    integrity path cannot use its own zero exit as support.
    """

    def __init__(self, workspace: Path, *, clock_ns=time.monotonic_ns):
        self.workspace = workspace.resolve()
        self._clock_ns = clock_ns
        self._origin_ns = clock_ns()
        self._open: dict[str, _OpenCommand] = {}
        self._events: list[TrajectoryEvent] = []
        self._last_snapshot = snapshot_tree(self.workspace)

    def record_edit_boundary(
        self, event_id: str, *, observed_ns: int | None = None
    ) -> tuple[EditEvent, ...]:
        """Diff a successful non-command tool boundary against the real tree."""
        if self._open:
            raise TrajectoryEvidenceError(
                f"edit boundary {event_id!r} overlaps active commands"
            )
        if not event_id:
            raise TrajectoryEvidenceError("an edit boundary needs a non-empty event id")
        when = self._clock_ns() if observed_ns is None else observed_ns
        if when < self._origin_ns:
            raise TrajectoryEvidenceError("edit boundary precedes the trajectory origin")
        current = snapshot_tree(self.workspace)
        timestamp_ms = max(0, (when - self._origin_ns) // 1_000_000)
        edits = tuple(
            EditEvent(path, timestamp_ms, event_id)
            for path in changed_paths(self._last_snapshot, current)
        )
        self._events.extend(edits)
        self._last_snapshot = current
        return edits

    def begin_command(
        self,
        command_id: str,
        argv: Sequence[str],
        *,
        cwd: str = ".",
        started_ns: int | None = None,
    ) -> None:
        if not command_id or not argv or not all(isinstance(part, str) and part for part in argv):
            raise TrajectoryEvidenceError("a command needs an id and non-empty string argv")
        if command_id in self._open:
            raise TrajectoryEvidenceError(f"duplicate command start {command_id!r}")
        relative_cwd = contained_relative_path(self.workspace, cwd)
        cwd_path = self.workspace if relative_cwd == "." else self.workspace / relative_cwd
        if not cwd_path.is_dir():
            raise TrajectoryEvidenceError(f"command cwd is not a directory: {cwd}")
        when = self._clock_ns() if started_ns is None else started_ns
        if when < self._origin_ns:
            raise TrajectoryEvidenceError("command begins before the trajectory origin")
        before = snapshot_tree(self.workspace)
        timestamp_ms = max(0, (when - self._origin_ns) // 1_000_000)
        unbounded = changed_paths(self._last_snapshot, before)
        if self._open and unbounded:
            raise TrajectoryEvidenceError(
                "workspace changed while parallel commands were active: " + ", ".join(unbounded)
            )
        self._events.extend(EditEvent(path, timestamp_ms, command_id) for path in unbounded)
        self._last_snapshot = before
        self._open[command_id] = _OpenCommand(
            command_id=command_id,
            argv=sanitized_argv(argv),
            cwd=relative_cwd,
            started_ns=when,
            before=before,
        )

    def finish_command(
        self,
        command_id: str,
        *,
        exit_code: int,
        output: str,
        finished_ns: int | None = None,
        failed: int | None = None,
        skipped: int | None = None,
        expected_failures: int | None = None,
    ) -> CommandEvent:
        active = self._open.get(command_id)
        if active is None:
            raise TrajectoryEvidenceError(
                f"command finish {command_id!r} does not match an active command"
            )
        if not isinstance(exit_code, int) or not isinstance(output, str):
            raise TrajectoryEvidenceError("command exit code and output evidence are required")
        when = self._clock_ns() if finished_ns is None else finished_ns
        if when < active.started_ns:
            raise TrajectoryEvidenceError("command finishes before it begins")
        after = snapshot_tree(self.workspace)
        timestamp_ms = max(0, (when - self._origin_ns) // 1_000_000)
        edits = changed_paths(active.before, after)
        if len(self._open) > 1 and edits:
            raise TrajectoryEvidenceError(
                "parallel command changed the workspace: " + ", ".join(edits)
            )
        for path in edits:
            self._events.append(EditEvent(path, timestamp_ms, command_id))
        parsed = parsed_test_counts(output)
        counts = {
            "failed": parsed["failed"] if failed is None else failed,
            "skipped": parsed["skipped"] if skipped is None else skipped,
            "expected_failures": (
                parsed["expected_failures"]
                if expected_failures is None
                else expected_failures
            ),
        }
        if any(not isinstance(value, int) or value < 0 for value in counts.values()):
            raise TrajectoryEvidenceError("test counters must be non-negative integers")
        event = CommandEvent(
            argv=active.argv,
            cwd=active.cwd,
            exit_code=exit_code,
            wall_time_ms=max(0, (when - active.started_ns) // 1_000_000),
            failed=counts["failed"],
            skipped=counts["skipped"],
            expected_failures=counts["expected_failures"],
            tree_before_sha256=active.before.sha256,
            tree_after_sha256=after.sha256,
        )
        self._events.append(event)
        self._last_snapshot = after
        del self._open[command_id]
        return event

    def cancel_unexecuted_command(self, command_id: str) -> None:
        active = self._open.get(command_id)
        if active is None:
            raise TrajectoryEvidenceError(
                f"command cancellation {command_id!r} does not match an active command"
            )
        current = snapshot_tree(self.workspace)
        changed = changed_paths(active.before, current)
        if changed:
            raise TrajectoryEvidenceError(
                "denied command changed the workspace: " + ", ".join(changed)
            )
        self._last_snapshot = current
        del self._open[command_id]

    def run_command(
        self,
        command_id: str,
        argv: Sequence[str],
        *,
        cwd: str = ".",
        env: Mapping[str, str] | None = None,
        timeout: float = 120,
    ) -> subprocess.CompletedProcess[str]:
        """Test/local adapter helper that captures a real subprocess boundary."""
        self.begin_command(command_id, argv, cwd=cwd)
        relative = contained_relative_path(self.workspace, cwd)
        working = self.workspace if relative == "." else self.workspace / relative
        try:
            completed = subprocess.run(
                list(argv),
                cwd=working,
                env=None if env is None else dict(env),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except BaseException:
            self._open.pop(command_id, None)
            raise
        self.finish_command(
            command_id,
            exit_code=completed.returncode,
            output=completed.stdout + "\n" + completed.stderr,
        )
        return completed

    def ingest_fragment(self, fragment: Mapping[str, object]) -> None:
        """Assemble one normalized live-adapter fragment at its observed boundary."""
        kind = fragment.get("kind")
        event_id = fragment.get("command_id") or fragment.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise TrajectoryEvidenceError("trajectory fragment has no event id")
        if kind == "command-start":
            argv = fragment.get("argv")
            if not isinstance(argv, (list, tuple)):
                raise TrajectoryEvidenceError("command-start fragment has no argv")
            self.begin_command(
                event_id,
                argv,
                cwd=fragment.get("cwd", "."),  # type: ignore[arg-type]
                started_ns=fragment.get("observed_ns"),  # type: ignore[arg-type]
            )
            return
        if kind == "command-finish":
            self.finish_command(
                event_id,
                exit_code=fragment.get("exit_code"),  # type: ignore[arg-type]
                output=fragment.get("output", ""),  # type: ignore[arg-type]
                finished_ns=fragment.get("observed_ns"),  # type: ignore[arg-type]
                failed=fragment.get("failed"),  # type: ignore[arg-type]
                skipped=fragment.get("skipped"),  # type: ignore[arg-type]
                expected_failures=fragment.get("expected_failures"),  # type: ignore[arg-type]
            )
            return
        if kind == "edit-boundary":
            self.record_edit_boundary(
                event_id, observed_ns=fragment.get("observed_ns")  # type: ignore[arg-type]
            )
            return
        raise TrajectoryEvidenceError(f"unknown trajectory fragment kind: {kind!r}")

    def assemble(self) -> tuple[TrajectoryEvent, ...]:
        if self._open:
            raise TrajectoryEvidenceError(
                "missing finish evidence for commands " + ", ".join(sorted(self._open))
            )
        current = snapshot_tree(self.workspace)
        unbounded = changed_paths(self._last_snapshot, current)
        if unbounded:
            raise TrajectoryEvidenceError(
                "workspace changed without an observed tool boundary: " + ", ".join(unbounded)
            )
        return tuple(self._events)

    def diagnostic_trajectory(self) -> list[dict]:
        return [event.to_dict() for event in self._events]

    def public_trajectory(self) -> list[dict]:
        return [event.to_dict() for event in self.assemble()]


def validate_public_trajectory(events: Iterable[Mapping[str, object]]) -> list[dict]:
    """Validate the exact list-order contract accepted by score_eval."""
    validated: list[dict] = []
    for index, event in enumerate(events):
        item = dict(event)
        kind = item.get("kind")
        if kind == "edit":
            if not isinstance(item.get("path"), str) or not item["path"]:
                raise TrajectoryEvidenceError(f"edit event {index} has no path")
        elif kind == "command":
            required = (
                "argv", "cwd", "exit_code", "wall_time_ms", "failed", "skipped",
                "expected_failures", "tree_before_sha256", "tree_after_sha256",
            )
            missing = [name for name in required if name not in item]
            if missing:
                raise TrajectoryEvidenceError(
                    f"command event {index} is missing evidence: {', '.join(missing)}"
                )
            if not isinstance(item["argv"], list) or not item["argv"]:
                raise TrajectoryEvidenceError(f"command event {index} has invalid argv")
            for name in ("exit_code", "wall_time_ms", "failed", "skipped", "expected_failures"):
                if not isinstance(item[name], int):
                    raise TrajectoryEvidenceError(f"command event {index} has invalid {name}")
        else:
            raise TrajectoryEvidenceError(f"trajectory event {index} has unknown kind {kind!r}")
        validated.append(item)
    return validated
