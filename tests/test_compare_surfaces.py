"""Unit tests for scripts/compare_surfaces.py."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import compare_surfaces as cs  # noqa: E402


def make_capture(label="cap", blocks=("alpha\nbravo", "charlie"), mid="mid text",
                 user_chars=447, user_sha="u0", reminders=1,
                 tools=("Bash", "Read"), tool_schema_chars=(100, 200),
                 with_text=True):
    """Build a capture summary dict plus its text sidecar."""
    import hashlib

    def h(s):
        return hashlib.sha256(s.encode()).hexdigest()

    data = {
        "label": label,
        "system_blocks": [
            {"index": i, "chars": len(b), "sha256": h(b), "cache_control": i > 0}
            for i, b in enumerate(blocks)
        ],
        "system_joined_sha256": h("".join(blocks)),
        "tools": list(tools),
        "tools_sha256": h(json.dumps([list(tools), list(tool_schema_chars)])),
        "tool_schemas": {
            name: {"chars": c, "sha256": h(f"{name}:{c}")}
            for name, c in zip(tools, tool_schema_chars)
        },
        "messages": [
            {"role": "user", "chars": user_chars, "sha256": user_sha,
             "system_reminder_count": reminders},
            {"role": "system", "chars": len(mid), "sha256": h(mid),
             "system_reminder_count": 0},
        ],
        "system_reminder": {"message_index": 0, "role": "user",
                            "present": reminders > 0, "count": reminders},
    }
    text = {"system_blocks": list(blocks), "mid_turn_system": mid}
    if with_text:
        data["system_text_ref"] = f"{label}.text.json"
    return data, text


class CaptureFixture:
    """Writes capture summaries (and sidecars) into a temp dir."""

    def __init__(self, tmpdir):
        self.dir = Path(tmpdir)

    def write(self, data, text):
        path = self.dir / f"{data['label']}.json"
        path.write_text(json.dumps(data))
        if data.get("system_text_ref"):
            (self.dir / data["system_text_ref"]).write_text(json.dumps(text))
        return cs.Capture(path)


class TestRedaction(unittest.TestCase):
    def test_strips_api_key(self):
        out = cs.redact("key sk-ant-abc123DEF_ghi trailing")
        self.assertNotIn("sk-ant-abc123DEF_ghi", out)
        self.assertIn("<redacted:api-key>", out)

    def test_strips_authorization_header(self):
        self.assertNotIn("zzz9", cs.redact("Authorization: Bearer zzz9zzz9zzz9"))

    def test_strips_key_value_secret(self):
        out = cs.redact("--password=hunter2ology")
        self.assertNotIn("hunter2ology", out)

    def test_leaves_ordinary_text_alone(self):
        self.assertEqual(cs.redact("Primary working directory: /tmp/x"),
                         "Primary working directory: /tmp/x")


class TestBoundedDiff(unittest.TestCase):
    def test_caps_line_count(self):
        old = [f"line {i}" for i in range(200)]
        new = [f"changed {i}" for i in range(200)]
        diff = cs._bounded_diff(old, new, "a", "b")
        self.assertLessEqual(len(diff), cs.MAX_DIFF_LINES + 1)
        self.assertIn("suppressed", diff[-1])

    def test_clips_long_lines(self):
        diff = cs._bounded_diff(["short"], ["x" * 5000], "a", "b")
        self.assertTrue(all(len(ln) <= cs.MAX_LINE_CHARS + 20 for ln in diff))

    def test_redacts_diff_content(self):
        diff = cs._bounded_diff(["nothing"], ["token sk-ant-SECRETVALUE1"], "a", "b")
        self.assertFalse(any("SECRETVALUE1" in ln for ln in diff))


class TestSurfaceComparison(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fx = CaptureFixture(self._tmp.name)

    def test_identical_captures_match_on_all_four_surfaces(self):
        a = self.fx.write(*make_capture("a"))
        b = self.fx.write(*make_capture("b"))
        pair = cs.compare_pair(a, b)
        self.assertEqual(
            sorted(pair["identical_surfaces"]),
            ["mid_turn_system", "system", "system_reminder", "tools"])
        self.assertEqual(pair["differing_surfaces"], [])
        self.assertEqual(pair["indeterminate_surfaces"], [])

    def test_system_block_difference_reports_index_delta_and_bounded_diff(self):
        a = self.fx.write(*make_capture("a", blocks=("alpha\nbravo", "charlie")))
        b = self.fx.write(*make_capture("b", blocks=("alpha\nDELTA", "charlie")))
        res = cs.compare_system(a, b)
        self.assertFalse(res["identical"])
        joined = "\n".join(res["description"])
        self.assertIn("block 0: differs", joined)
        self.assertNotIn("block 1", joined)
        self.assertIn(" alpha", joined)  # unchanged context line
        self.assertIn("-bravo", joined)
        self.assertIn("+DELTA", joined)

    def test_system_difference_without_sidecar_degrades_to_hashes(self):
        a = self.fx.write(*make_capture("a", blocks=("alpha",), with_text=False))
        b = self.fx.write(*make_capture("b", blocks=("bravo!",), with_text=False))
        res = cs.compare_system(a, b)
        self.assertFalse(res["identical"])
        self.assertEqual(res["size_delta"], 1)
        self.assertIn("no text sidecar on both sides",
                      "\n".join(res["description"]))

    def test_mid_turn_system_difference(self):
        a = self.fx.write(*make_capture("a", mid="mid text"))
        b = self.fx.write(*make_capture("b", mid="mid text plus multi-agent line"))
        res = cs.compare_mid_turn_system(a, b)
        self.assertFalse(res["identical"])
        self.assertEqual(res["size_delta"], len("mid text plus multi-agent line") - len("mid text"))
        self.assertIn("multi-agent", "\n".join(res["description"]))

    def test_reminder_difference_reports_size_but_never_payload(self):
        a = self.fx.write(*make_capture("a", user_chars=447, user_sha="u0"))
        b = self.fx.write(*make_capture("b", user_chars=6541, user_sha="u1"))
        res = cs.compare_system_reminder(a, b)
        self.assertFalse(res["identical"])
        self.assertEqual(res["size_delta"], 6094)
        joined = "\n".join(res["description"])
        self.assertIn("6094", joined)
        self.assertIn("payload not retained", joined)
        self.assertNotIn("<system-reminder>", joined)

    def test_reminder_presence_change_is_reported(self):
        a = self.fx.write(*make_capture("a", reminders=1))
        b = self.fx.write(*make_capture("b", reminders=0, user_sha="u1"))
        res = cs.compare_system_reminder(a, b)
        self.assertFalse(res["identical"])
        self.assertIn("presence True -> False", "\n".join(res["description"]))

    def test_reminder_indeterminate_when_not_recorded(self):
        data, text = make_capture("a")
        del data["system_reminder"]
        del data["messages"][0]["system_reminder_count"]
        a = self.fx.write(data, text)
        b = self.fx.write(*make_capture("b"))
        res = cs.compare_system_reminder(a, b)
        self.assertIsNone(res["identical"])

    def test_tools_membership_change(self):
        a = self.fx.write(*make_capture("a", tools=("Bash", "Read"), tool_schema_chars=(100, 200)))
        b = self.fx.write(*make_capture("b", tools=("Bash", "WebFetch"), tool_schema_chars=(100, 300)))
        res = cs.compare_tools(a, b)
        self.assertFalse(res["identical"])
        joined = "\n".join(res["description"])
        self.assertIn("added: WebFetch", joined)
        self.assertIn("removed: Read", joined)

    def test_tools_schema_only_change_names_unchanged(self):
        a = self.fx.write(*make_capture("a", tools=("Bash", "Read"), tool_schema_chars=(2823, 200)))
        b = self.fx.write(*make_capture("b", tools=("Bash", "Read"), tool_schema_chars=(2725, 200)))
        res = cs.compare_tools(a, b)
        self.assertFalse(res["identical"])
        self.assertEqual(res["size_delta"], 0)
        joined = "\n".join(res["description"])
        self.assertIn("schema changed for: Bash (2823 -> 2725 chars, -98)", joined)
        self.assertNotIn("added:", joined)

    def test_tools_difference_without_schema_hashes(self):
        for label in ("a", "b"):
            data, text = make_capture(label, tools=("Bash", "Read"))
            del data["tool_schemas"]
            data["tools_sha256"] = f"sha-{label}"
            self.fx.write(data, text)
        a = cs.Capture(self.fx.dir / "a.json")
        b = cs.Capture(self.fx.dir / "b.json")
        res = cs.compare_tools(a, b)
        self.assertFalse(res["identical"])
        self.assertIn("no per-tool schema hashes are recorded", "\n".join(res["description"]))

    def test_tools_indeterminate_when_absent(self):
        data, text = make_capture("a")
        del data["tools"]
        del data["tools_sha256"]
        a = self.fx.write(data, text)
        b = self.fx.write(*make_capture("b"))
        self.assertIsNone(cs.compare_tools(a, b)["identical"])


def make_alt_shape_capture(label="cli", blocks=("alpha\nbravo", "charlie"),
                           mid_chars=8226, mid_sha="midsha", reminder=True,
                           tools=("Bash", "Read")):
    """The alternate capture layout used by the interactive-CLI arm.

    It carries block text inline, names the mid-turn message
    ``mid_turn_system_message``, records ``messages0`` instead of a messages
    array, and withholds the messages[0] hash entirely.
    """
    import hashlib

    def h(s):
        return hashlib.sha256(s.encode()).hexdigest()

    return {
        "label": label,
        "host": "interactive-cli",
        "system_blocks": [
            {"index": i, "chars": len(b), "sha256": h(b), "cache_control": i > 0, "text": b}
            for i, b in enumerate(blocks)
        ],
        "system_joined_sha256": h("".join(blocks)),
        "mid_turn_system_message": {"present": True, "chars": mid_chars, "sha256": mid_sha},
        "messages0": {"role": "user", "contains_system_reminder": reminder,
                      "chars": None, "sha256": None},
        "tools": list(tools),
        "tools_count": len(tools),
        "tools_sha256": h(json.dumps(list(tools))),
    }, None


class TestAlternateCaptureLayout(unittest.TestCase):
    """The comparator must read the interactive-CLI arm's key layout."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fx = CaptureFixture(self._tmp.name)

    def _alt(self, **kw):
        data, _ = make_alt_shape_capture(**kw)
        path = self.fx.dir / f"{data['label']}.json"
        path.write_text(json.dumps(data))
        return cs.Capture(path)

    def test_inline_block_text_is_used_as_a_sidecar(self):
        a = self._alt(label="cli_a", blocks=("alpha\nbravo",))
        self.assertEqual(a.text["system_blocks"], ["alpha\nbravo"])
        b = self._alt(label="cli_b", blocks=("alpha\nDELTA",))
        res = cs.compare_system(a, b)
        self.assertFalse(res["identical"])
        self.assertIn("+DELTA", "\n".join(res["description"]))

    def test_mid_turn_system_message_key_is_read(self):
        a = self._alt(label="cli_a", mid_chars=82, mid_sha="s1")
        b = self._alt(label="cli_b", mid_chars=8226, mid_sha="s2")
        res = cs.compare_mid_turn_system(a, b)
        self.assertFalse(res["identical"])
        self.assertEqual(res["size_delta"], 8144)

    def test_withheld_messages0_hash_is_indeterminate_not_a_difference(self):
        a = self._alt(label="cli_a")
        b = self._alt(label="cli_b")
        res = cs.compare_system_reminder(a, b)
        self.assertIsNone(res["identical"])
        joined = "\n".join(res["description"])
        self.assertIn("presence True -> True", joined)
        self.assertIn("byte identity cannot be established", joined)

    def test_reminder_presence_disagreement_still_differs(self):
        a = self._alt(label="cli_a", reminder=True)
        b = self._alt(label="cli_b", reminder=False)
        self.assertFalse(cs.compare_system_reminder(a, b)["identical"])

    def test_alt_shape_pairs_with_standard_shape(self):
        std = self.fx.write(*make_capture("sdk"))
        alt = self._alt(label="cli")
        pair = cs.compare_pair(std, alt)
        self.assertEqual(
            sorted(s["surface"] for s in pair["surfaces"]),
            ["mid_turn_system", "system", "system_reminder", "tools"])
        self.assertEqual(pair["indeterminate_surfaces"], ["system_reminder"])


class TestReportAndCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fx = CaptureFixture(self._tmp.name)

    def _paths(self, labels):
        for label in labels:
            self.fx.write(*make_capture(label))
        return [self.fx.dir / f"{label}.json" for label in labels]

    def test_three_captures_produce_three_pairs(self):
        report = cs.build_report(self._paths(["a", "b", "c"]))
        self.assertEqual(len(report["pairs"]), 3)
        self.assertEqual(len(report["captures"]), 3)

    def test_every_pair_reports_all_four_surfaces(self):
        report = cs.build_report(self._paths(["a", "b"]))
        names = [s["surface"] for s in report["pairs"][0]["surfaces"]]
        self.assertEqual(names, ["system", "mid_turn_system", "system_reminder", "tools"])

    def test_render_is_plain_text(self):
        text = cs.render(cs.build_report(self._paths(["a", "b"])))
        self.assertIn("[identical]", text)
        self.assertIn("=== a  vs  b", text)

    def test_cli_writes_report_and_exits_zero(self):
        paths = self._paths(["a", "b"])
        out = self.fx.dir / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cs.main([str(paths[0]), str(paths[1]), "--json", "--out", str(out)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out.read_text())["pairs"]), 1)

    def test_cli_reports_missing_file(self):
        paths = self._paths(["a"])
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cs.main([str(paths[0]), str(self.fx.dir / "absent.json")])
        self.assertEqual(rc, 2)

    def test_cli_rejects_single_capture(self):
        paths = self._paths(["a"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cs.main([str(paths[0])])


if __name__ == "__main__":
    unittest.main()
