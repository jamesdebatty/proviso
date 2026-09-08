"""Baking command/edit evidence from real tree boundaries."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bakeoff9_trajectory as trajectory


class TreeEvidenceTests(unittest.TestCase):
    def test_symlink_target_is_hashed_without_following_target_bytes(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            outside = Path(temporary) / "outside.txt"
            outside.write_text("first")
            link = root / "link"
            link.symlink_to(outside)
            first = trajectory.snapshot_tree(root)
            outside.write_text("second")
            self.assertEqual(first, trajectory.snapshot_tree(root))
            link.unlink()
            link.symlink_to("missing")
            self.assertNotEqual(first, trajectory.snapshot_tree(root))

    def test_snapshot_is_deterministic_and_changes_with_bytes(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "nested" / "b.txt").write_text("b")
            (root / "a.txt").write_text("a")
            first = trajectory.snapshot_tree(root)
            self.assertEqual(first, trajectory.snapshot_tree(root))
            self.assertEqual(["a.txt", "nested/b.txt"], [entry.path for entry in first.entries])
            (root / "a.txt").write_text("changed")
            second = trajectory.snapshot_tree(root)
            self.assertNotEqual(first.sha256, second.sha256)
            self.assertEqual(("a.txt",), trajectory.changed_paths(first, second))

    def test_containment_rejects_escape(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            with self.assertRaisesRegex(trajectory.TrajectoryEvidenceError, "escapes"):
                trajectory.contained_relative_path(Path(temporary), "../outside")


class RecorderTests(unittest.TestCase):
    def test_shell_side_write_is_an_edit_before_the_command(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            target = root / "covered.py"
            target.write_text("before\n")
            recorder = trajectory.TrajectoryRecorder(root)
            result = recorder.run_command(
                "bash-1",
                [sys.executable, "-c", "from pathlib import Path; Path('covered.py').write_text('after\\n')"],
            )
            self.assertEqual(0, result.returncode)
            events = recorder.public_trajectory()
            self.assertEqual(["edit", "command"], [event["kind"] for event in events])
            self.assertEqual("covered.py", events[0]["path"])
            self.assertNotEqual(
                events[1]["tree_before_sha256"], events[1]["tree_after_sha256"]
            )

    def test_non_command_edit_boundary_reads_the_tree_not_a_claimed_path(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            (root / "actual.txt").write_text("before")
            recorder = trajectory.TrajectoryRecorder(root)
            (root / "actual.txt").write_text("after")
            edits = recorder.record_edit_boundary("edit-tool-1")
            self.assertEqual(("actual.txt",), tuple(event.path for event in edits))

    def test_parallel_read_only_commands_finish_in_observed_order(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            recorder = trajectory.TrajectoryRecorder(Path(temporary))
            recorder.begin_command("one", ["echo", "one"])
            recorder.begin_command("two", ["echo", "two"])
            recorder.finish_command("two", exit_code=0, output="")
            with self.assertRaisesRegex(trajectory.TrajectoryEvidenceError, "missing finish"):
                recorder.public_trajectory()
            recorder.finish_command("one", exit_code=0, output="")
            events = recorder.public_trajectory()
            self.assertEqual(
                [("echo", "two"), ("echo", "one")],
                [tuple(event["argv"]) for event in events],
            )

    def test_parallel_workspace_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            recorder = trajectory.TrajectoryRecorder(root)
            recorder.begin_command("one", ["touch", "changed"])
            recorder.begin_command("two", ["true"])
            (root / "changed").touch()
            with self.assertRaisesRegex(trajectory.TrajectoryEvidenceError, "parallel command changed"):
                recorder.finish_command("one", exit_code=0, output="")

    def test_surviving_command_can_receive_a_later_sequential_edit(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            recorder = trajectory.TrajectoryRecorder(root)
            recorder.begin_command("one", ["true"])
            recorder.begin_command("two", ["touch", "changed"])
            recorder.finish_command("one", exit_code=0, output="")
            (root / "changed").touch()
            recorder.finish_command("two", exit_code=0, output="")
            self.assertEqual(
                ["command", "edit", "command"],
                [event["kind"] for event in recorder.public_trajectory()],
            )

    def test_denial_cancels_the_exact_parallel_command(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            recorder = trajectory.TrajectoryRecorder(Path(temporary))
            recorder.begin_command("one", ["true"])
            recorder.begin_command("two", ["cat", "missing"])
            recorder.cancel_unexecuted_command("two")
            recorder.finish_command("one", exit_code=0, output="")
            self.assertEqual(1, len(recorder.public_trajectory()))

    def test_unbounded_workspace_change_fails_closed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            recorder = trajectory.TrajectoryRecorder(root)
            (root / "unobserved.txt").write_text("changed")
            with self.assertRaisesRegex(trajectory.TrajectoryEvidenceError, "without an observed"):
                recorder.public_trajectory()

    def test_missing_exit_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            recorder = trajectory.TrajectoryRecorder(Path(temporary))
            recorder.begin_command("one", ["true"])
            with self.assertRaisesRegex(trajectory.TrajectoryEvidenceError, "exit code"):
                recorder.finish_command("one", exit_code=None, output="")  # type: ignore[arg-type]

    def test_denied_unexecuted_command_is_cancelled_only_without_changes(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            recorder = trajectory.TrajectoryRecorder(root)
            recorder.begin_command("one", ["cat", "missing"])
            recorder.cancel_unexecuted_command("one")
            self.assertEqual([], recorder.public_trajectory())

            recorder.begin_command("two", ["touch", "unexpected"])
            (root / "unexpected").touch()
            with self.assertRaisesRegex(trajectory.TrajectoryEvidenceError, "denied command changed"):
                recorder.cancel_unexecuted_command("two")

    def test_test_counts_and_authorization_arguments_are_sanitized(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            recorder = trajectory.TrajectoryRecorder(Path(temporary))
            recorder.begin_command("one", ["pytest", "--api-key", "secret-value"])
            command = recorder.finish_command(
                "one", exit_code=1, output="2 failed, 3 skipped, 1 xfailed"
            )
            self.assertEqual(("pytest", "--api-key", "<redacted>"), command.argv)
            self.assertEqual((2, 3, 1), (command.failed, command.skipped, command.expected_failures))


if __name__ == "__main__":
    unittest.main()
