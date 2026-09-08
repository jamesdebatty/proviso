#!/usr/bin/env python3
"""Closing-unit scanner, revision 3 (2026-09-05).
v3 adds the soft offer forms the raw-baseline pilot exposed ("that's a small
change to `_check`", "that's a one-line change in the loop", "the fix is one
line"), which name the labour without asking for the word. Revision 2 was
written after the measurement review; v1 (`closing_scan.py` under the study
notes) is the artifact the reviews cite.

Revision 2 notes:
v1 (`closing_scan.py`) is kept as the artifact the review cites.

Changes from v1:
- Fences: ``` and ~~~ (any info string), unclosed fence drops the rest.
- Closing unit: after removing fences and trailing tables (lines starting
  with `|`) or rules, the last block; if that block is a list item, every
  preceding list-item block separated by single blank lines is absorbed, so
  loose and tight lists are one unit. Blockquote markers are stripped.
- Normalisation: ’→' on the whole text before both fields; fences are
  detected before backticks are blanked, for both fields.
- OFFER narrowed to explicit hand-backs (a verb that asks the reader to
  speak or offers the assistant's labour). Bare conditionals such as
  "if you want floor semantics, that's a spec change" are NOT matched; they
  are left to the judged label. Precision over recall: the deterministic
  field is a floor and a cross-check, not the primary.
- Empty closing unit is reported as `closing_unit_empty`.
"""
import glob, json, re, sys, collections

FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})", re.M)
OFFER = re.compile(
    r"(say the word|say so(,)? (and|if)|say if|tell me (which|if|whether|what|and|when)|let me know|"
    r"(want|would you like|like) me to|happy to (add|make|do|change|switch|revert|apply|write|extend|wire|clamp|guard|handle|update)|"
    r"shall i|do you want (me|it|that|this|the)|"
    r"i('ll| will| can| could|'d) (make|add|do|apply|change|switch|revert|wire|clamp|guard|handle|extend|write|update) (that|it|the|those|both|them|this)|"
    r"revert (it|that|this|the .{0,20}) if you|if you('d| would)? (rather|prefer|want)[^.]{0,60}(say|tell|let me know|i'll|i can)|"
    r"that'?s a (small|one[- ]line|quick|trivial|simple) (change|revert|edit|tweak)|(one|a) (small|one[- ]line|quick) change (to|in|if)|"
    r"the fix is (a )?one[- ]line)", re.I)
FLAG = re.compile(
    r"^\W*(one|two|three|a|the|another) (thing|things|behaviou?rs?|judgment calls?|decisions?|assumptions?|"
    r"changes?|caveats?|notes?|hazards?|consequences?|items?|points?) (worth|to|i|you|beyond|outside|that|the|left|which|"
    r"i'?d|not|about|in|on|where)|^\W*worth (knowing|flagging|noting|a look)|^\W*(also|note that|nb|one more)\b|"
    r"^\W*the (real|one|only) (caveat|hazard|thing|risk)|^\W*(behaviou?r|assumption)s? (i|you|worth)", re.I)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

def normalise(text):
    # apostrophes only; backticks are removed after fence detection
    return text.replace("’", "'")

def strip_fences(text):
    out, i = [], 0
    lines = text.splitlines()
    fence = None
    for ln in lines:
        m = re.match(r"^\s*(`{3,}|~{3,})", ln)
        if fence is None and m:
            fence = m.group(1)[0] * len(m.group(1)); out.append(""); continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue          # inside a fence (or after an unclosed one)
        out.append(ln)
    return "\n".join(out)

def blocks_of(text):
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]

def is_table(b): return all(l.strip().startswith("|") for l in b.splitlines())
def is_rule(b): return re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", b) is not None
def is_list(b): return all(LIST_ITEM.match(l) or l.startswith((" ", "\t")) for l in b.splitlines())

def closing_unit(text):
    bl = blocks_of(strip_fences(text))
    while bl and (is_table(bl[-1]) or is_rule(bl[-1])):
        bl.pop()
    if not bl:
        return ""
    unit = [bl.pop()]
    if is_list(unit[0]):
        while bl and is_list(bl[-1]):
            unit.insert(0, bl.pop())
    return re.sub(r"^\s*>\s?", "", "\n".join(unit), flags=re.M)

def scan(text):
    t = normalise(text)
    cu = closing_unit(t).replace("`", " ")
    body = strip_fences(t).replace("`", " ")
    return {
        "closing_offer": bool(OFFER.search(cu)),
        "closing_flag": bool(FLAG.search(cu)),
        "offer_anywhere": bool(OFFER.search(body)),
        "closing_unit_empty": cu == "",
        "closing_unit_words": len(cu.split()),
        "closing_unit": cu,
    }

def main(root, dump=False):
    per = collections.defaultdict(collections.Counter)
    for p in sorted(glob.glob(f"{root}/trials/*.json")):
        t = json.load(open(p)); s = scan(t["output"]["text"])
        k = (t["variant_id"][:3], t["probe_id"]); per[k]["n"] += 1
        for f in ("closing_offer", "closing_flag", "offer_anywhere", "closing_unit_empty"):
            per[k][f] += s[f]
        if dump and (s["closing_offer"] or s["offer_anywhere"]):
            print(f"## {k[0]} | {k[1]} | r{t['repetition']} | offer={int(s['closing_offer'])} anywhere={int(s['offer_anywhere'])}\n{s['closing_unit'][:240]}\n")
    arms = sorted({k[0] for k in per}); probes = sorted({k[1] for k in per})
    for field in ("closing_offer", "closing_flag", "offer_anywhere", "closing_unit_empty"):
        print(f"\n{field} (of 5 per probe; total of 30)")
        for a in arms:
            print(f"  {a:4s}", " ".join(f"{pr[:12]}={per[(a,pr)][field]}" for pr in probes), f" total={sum(per[(a,pr)][field] for pr in probes)}")

if __name__ == "__main__":
    main(sys.argv[1], dump="--dump" in sys.argv[2:])
