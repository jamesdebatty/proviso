#!/usr/bin/env python3
"""Compare the four behavior-bearing request surfaces across capture summaries.

The four surfaces are the ones the bakeoff 9 preregistration hashes at
`campaigns/clause-bakeoff-9-2026-08-22/preregistration.md:245`:

  1. ``system``          -- the top-level system blocks
  2. ``mid_turn_system`` -- the mid-turn ``role: "system"`` message
  3. ``system_reminder`` -- ``messages[0]``'s ``<system-reminder>`` presence
  4. ``tools``           -- the tools array

Input is two or more capture summaries in the shape of
``campaigns/clause-bakeoff-9-2026-08-22/sources/2026-08-22-capture-control-preset-2.1.239-opus5.json``.
Newer captures may carry additive keys (``tool_schemas``, ``system_text_ref``,
``system_reminder``); they are used when present and degraded past when absent.

For every capture pair the report says, per surface, whether it is
byte-identical, and when it is not, the size delta plus a bounded, redacted
description of what differs. The ``system_reminder`` surface is never described
by content -- only presence, tag count, and size -- because reminder payloads
are not retained (preregistration `:258`).

Usage:
    python3 scripts/compare_surfaces.py A.json B.json [C.json ...]
    python3 scripts/compare_surfaces.py A.json B.json --json --out report.json
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import re
import sys
from pathlib import Path

MAX_DIFF_LINES = 20
MAX_LINE_CHARS = 160

_REDACTIONS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "<redacted:api-key>"),
    (re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._\-/+=]+", re.I), "<redacted:authorization>"),
    (re.compile(
        r"(?i)\b(api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd|"
        r"authorization|x-api-key|client[_-]?secret)\b(\s*[:=]\s*|\s+)\S+"),
     r"\1=<redacted>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "<redacted:token>"),
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "<redacted:long-hex>"),
]


def redact(text: str) -> str:
    """Strip credential-shaped and authorization-shaped substrings."""
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def _clip(line: str) -> str:
    line = redact(line)
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + " ...[clipped]"


def _bounded_diff(old: list[str], new: list[str], old_label: str, new_label: str) -> list[str]:
    lines = list(difflib.unified_diff(old, new, old_label, new_label, lineterm="", n=1))
    body = [ln for ln in lines if not ln.startswith(("---", "+++"))]
    out = [_clip(ln) for ln in body[:MAX_DIFF_LINES]]
    if len(body) > MAX_DIFF_LINES:
        out.append(f"...[{len(body) - MAX_DIFF_LINES} further diff lines suppressed]")
    return out


class Capture:
    """One capture summary plus its optional system-prompt text sidecar."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text())
        self.label = self.data.get("label") or path.stem
        self.text = self._load_text_sidecar()

    def _load_text_sidecar(self) -> dict:
        """Sidecar text if referenced, else any text carried inline on the blocks."""
        ref = self.data.get("system_text_ref")
        if ref:
            sidecar = (self.path.parent / ref).resolve()
            if sidecar.is_file():
                return json.loads(sidecar.read_text())
        blocks = self.data.get("system_blocks") or []
        inline = [b.get("text") for b in blocks]
        if inline and all(t is not None for t in inline):
            return {"system_blocks": inline}
        return {}

    # -- surface extraction -------------------------------------------------

    def system_blocks(self) -> list[dict]:
        return self.data.get("system_blocks") or []

    def system_identity(self) -> str | None:
        joined = self.data.get("system_joined_sha256")
        if joined:
            return joined
        blocks = self.system_blocks()
        return "|".join(b.get("sha256", "?") for b in blocks) if blocks else None

    def system_chars(self) -> int:
        return sum(b.get("chars", 0) for b in self.system_blocks())

    def _mid_turn_message(self) -> dict | None:
        for msg in self.data.get("messages") or []:
            if msg.get("role") == "system":
                return msg
        alt = self.data.get("mid_turn_system_message")
        if isinstance(alt, dict) and alt.get("present") is not False:
            return alt
        return None

    def mid_turn_identity(self) -> str | None:
        msg = self._mid_turn_message()
        return msg.get("sha256") if msg else None

    def mid_turn_chars(self) -> int:
        msg = self._mid_turn_message()
        return msg.get("chars", 0) if msg else 0

    def _first_message(self) -> dict | None:
        msgs = self.data.get("messages") or []
        if msgs:
            return msgs[0]
        alt = self.data.get("messages0")
        return alt if isinstance(alt, dict) else None

    def reminder_state(self) -> dict:
        """Presence facts only. Never the payload."""
        declared = self.data.get("system_reminder") or {}
        first = self._first_message() or {}
        count = declared.get("count", first.get("system_reminder_count"))
        if "present" in declared:
            present = declared["present"]
        elif "contains_system_reminder" in first:
            present = first["contains_system_reminder"]
        elif count is not None:
            present = count > 0
        else:
            present = None
        return {
            "present": present,
            "count": count,
            "message_role": declared.get("role", first.get("role")),
            "message_chars": first.get("chars"),
            "message_sha256": first.get("sha256"),
        }

    def tools_identity(self) -> str | None:
        return self.data.get("tools_sha256") or (
            "names:" + ",".join(self.data.get("tools") or []) if self.data.get("tools") else None
        )

    def tool_names(self) -> list[str]:
        return list(self.data.get("tools") or [])

    def tool_schemas(self) -> dict:
        return self.data.get("tool_schemas") or {}


# -- per-surface comparison ------------------------------------------------


def _result(name: str, identical: bool | None, delta, description) -> dict:
    return {
        "surface": name,
        "identical": identical,
        "size_delta": delta,
        "description": description,
    }


def compare_system(a: Capture, b: Capture) -> dict:
    ida, idb = a.system_identity(), b.system_identity()
    delta = b.system_chars() - a.system_chars()
    if ida is None or idb is None:
        return _result("system", None, delta, ["one or both captures record no system blocks"])
    if ida == idb:
        return _result("system", True, 0, [])

    desc = []
    ba, bb = a.system_blocks(), b.system_blocks()
    if len(ba) != len(bb):
        desc.append(f"block count {len(ba)} -> {len(bb)}")
    for i in range(max(len(ba), len(bb))):
        xa = ba[i] if i < len(ba) else None
        xb = bb[i] if i < len(bb) else None
        if xa is None or xb is None:
            desc.append(f"block {i}: {'added' if xa is None else 'removed'}")
        elif xa.get("sha256") != xb.get("sha256"):
            desc.append(
                f"block {i}: differs, {xa.get('chars')} -> {xb.get('chars')} chars "
                f"({xb.get('chars', 0) - xa.get('chars', 0):+d})"
            )

    ta = a.text.get("system_blocks")
    tb = b.text.get("system_blocks")
    if ta and tb:
        for i in range(min(len(ta), len(tb))):
            if i < len(ba) and i < len(bb) and ba[i].get("sha256") == bb[i].get("sha256"):
                continue
            diff = _bounded_diff(ta[i].splitlines(), tb[i].splitlines(),
                                 f"{a.label}:block{i}", f"{b.label}:block{i}")
            if diff:
                desc.append(f"block {i} diff:")
                desc.extend("  " + ln for ln in diff)
    else:
        desc.append("no text sidecar on both sides; hash/size comparison only")
    return _result("system", False, delta, desc)


def compare_mid_turn_system(a: Capture, b: Capture) -> dict:
    ida, idb = a.mid_turn_identity(), b.mid_turn_identity()
    delta = b.mid_turn_chars() - a.mid_turn_chars()
    if ida is None or idb is None:
        missing = [c.label for c, i in ((a, ida), (b, idb)) if i is None]
        return _result("mid_turn_system", None, delta,
                       [f"no role=system message in: {', '.join(missing)}"])
    if ida == idb:
        return _result("mid_turn_system", True, 0, [])

    desc = [f"{a.mid_turn_chars()} -> {b.mid_turn_chars()} chars ({delta:+d})"]
    ta, tb = a.text.get("mid_turn_system"), b.text.get("mid_turn_system")
    if ta is not None and tb is not None:
        desc.append("diff:")
        desc.extend("  " + ln for ln in _bounded_diff(
            ta.splitlines(), tb.splitlines(), f"{a.label}:mid", f"{b.label}:mid"))
    else:
        desc.append("no text sidecar on both sides; hash/size comparison only")
    return _result("mid_turn_system", False, delta, desc)


def compare_system_reminder(a: Capture, b: Capture) -> dict:
    sa, sb = a.reminder_state(), b.reminder_state()
    delta = None
    if sa["message_chars"] is not None and sb["message_chars"] is not None:
        delta = sb["message_chars"] - sa["message_chars"]

    if sa["present"] is None or sb["present"] is None:
        return _result("system_reminder", None, delta,
                       ["reminder presence not recorded in one or both captures"])

    counts_known = sa["count"] is not None and sb["count"] is not None
    shas_known = sa["message_sha256"] is not None and sb["message_sha256"] is not None
    differs = (
        sa["present"] != sb["present"]
        or (counts_known and sa["count"] != sb["count"])
        or (shas_known and sa["message_sha256"] != sb["message_sha256"])
        or bool(delta)
    )
    if not differs and shas_known:
        return _result("system_reminder", True, 0, [])

    desc = [f"presence {sa['present']} -> {sb['present']}"]
    if counts_known:
        desc.append(f"reminder tag count {sa['count']} -> {sb['count']}")
    if delta is not None:
        desc.append(f"messages[0] size {sa['message_chars']} -> {sb['message_chars']} ({delta:+d})")
    desc.append("payload not retained by either capture; no content description available "
                "(preregistration :258)")
    if not differs:
        desc.insert(0, "presence facts agree, but at least one capture withholds the "
                       "messages[0] hash, so byte identity cannot be established")
        return _result("system_reminder", None, delta, desc)
    return _result("system_reminder", False, delta, desc)


def compare_tools(a: Capture, b: Capture) -> dict:
    ida, idb = a.tools_identity(), b.tools_identity()
    na, nb = a.tool_names(), b.tool_names()
    delta = len(nb) - len(na)
    if ida is None or idb is None:
        return _result("tools", None, delta, ["one or both captures record no tools array"])
    if ida == idb:
        return _result("tools", True, 0, [])

    desc = []
    added, removed = sorted(set(nb) - set(na)), sorted(set(na) - set(nb))
    if added:
        desc.append(f"added: {', '.join(added)}")
    if removed:
        desc.append(f"removed: {', '.join(removed)}")
    if na != nb and not added and not removed:
        desc.append("same tool names in a different order")

    scha, schb = a.tool_schemas(), b.tool_schemas()
    if scha and schb:
        changed = []
        for name in sorted(set(scha) & set(schb)):
            if scha[name].get("sha256") != schb[name].get("sha256"):
                d = schb[name].get("chars", 0) - scha[name].get("chars", 0)
                changed.append(f"{name} ({scha[name].get('chars')} -> {schb[name].get('chars')} chars, {d:+d})")
        if changed:
            desc.append("schema changed for: " + "; ".join(changed))
        if not added and not removed and not changed:
            desc.append("tool names and per-tool schemas match; "
                        "tools_sha256 differs on array ordering or serialization")
    elif not added and not removed:
        desc.append("tool names match but tools_sha256 differs: schemas differ and no "
                    "per-tool schema hashes are recorded")
    if delta:
        desc.append(f"tool count {len(na)} -> {len(nb)} ({delta:+d})")
    return _result("tools", False, delta, desc)


SURFACES = (compare_system, compare_mid_turn_system, compare_system_reminder, compare_tools)


def compare_pair(a: Capture, b: Capture) -> dict:
    surfaces = [fn(a, b) for fn in SURFACES]
    return {
        "a": a.label,
        "b": b.label,
        "a_path": str(a.path),
        "b_path": str(b.path),
        "identical_surfaces": [s["surface"] for s in surfaces if s["identical"] is True],
        "differing_surfaces": [s["surface"] for s in surfaces if s["identical"] is False],
        "indeterminate_surfaces": [s["surface"] for s in surfaces if s["identical"] is None],
        "surfaces": surfaces,
    }


def build_report(paths: list[Path]) -> dict:
    captures = [Capture(p) for p in paths]
    return {
        "captures": [{"label": c.label, "path": str(c.path),
                      "host": c.data.get("host"),
                      "has_text_sidecar": bool(c.text)} for c in captures],
        "pairs": [compare_pair(x, y) for x, y in itertools.combinations(captures, 2)],
    }


def render(report: dict) -> str:
    out = ["captures:"]
    for c in report["captures"]:
        host = f" host={c['host']}" if c.get("host") else ""
        out.append(f"  {c['label']}{host} (text sidecar: {'yes' if c['has_text_sidecar'] else 'no'})")
    for pair in report["pairs"]:
        out.append("")
        out.append(f"=== {pair['a']}  vs  {pair['b']}")
        for s in pair["surfaces"]:
            if s["identical"] is True:
                out.append(f"  [identical]      {s['surface']}")
            elif s["identical"] is None:
                out.append(f"  [indeterminate]  {s['surface']}")
                out.extend(f"                     {line}" for line in s["description"])
            else:
                delta = "" if s["size_delta"] is None else f"  (size delta {s['size_delta']:+d})"
                out.append(f"  [differs]        {s['surface']}{delta}")
                out.extend(f"                     {line}" for line in s["description"])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("captures", nargs="+", type=Path, help="two or more capture summary JSON files")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable report")
    ap.add_argument("--out", type=Path, help="also write the JSON report to this path")
    args = ap.parse_args(argv)

    if len(args.captures) < 2:
        ap.error("need at least two captures to compare")
    missing = [str(p) for p in args.captures if not p.is_file()]
    if missing:
        print("missing capture file(s): " + ", ".join(missing), file=sys.stderr)
        return 2

    report = build_report(args.captures)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
