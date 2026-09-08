#!/usr/bin/env python3
"""Deterministic scans over the final assistant message of a coding session.

Every rule here is fixed so that a measurement can be recomputed from the
stored message bytes alone, and every rule is applied identically to every
arm. The scans measure the *shape* of the tail a model appends to an agentic
turn (appended sections, closing offers, an opener that narrates intent), not
writing quality. The frozen lists are the instrument; changing one changes the
plan hash of any campaign that seals this module.

Preprocessing, in this order:

1. `’` is replaced by `'`.
2. Fenced code blocks are removed (`prose_density.FENCE`), replaced by a blank
   line, for every field except `words` and the `REF` counts.
3. Lines are `str.splitlines()` of the result.

Fields:

- `words`: whitespace-delimited tokens of the original text, the same rule
  `clause_campaign.py` uses for `output.words`.
- `headings`: lines opening with one to six `#` and a space.
- `bullets`: lines matching `prose_density.LIST_MARKER`.
- `bold_leadins`: lines opening with a `**bold**` or `__bold__` run-in that
  ends in a colon or ends the line, whatever its title. The synonym-drift
  cross-check: a "Recap" lead-in escapes `TAIL_TITLES` but not this count.
- `tail_section_count`, `tail_section_titles`, `tail_first_line`,
  `tail_words`: heading or bold lead-in lines whose title begins with a
  frozen tail title; their titles, lowercased; the index of the first such
  line, or `None`; the words from that line to the end of the message.
- `closing_offer_count`, `closing_offer_phrases`, `closing_offer_last_block`:
  matches of the frozen offer phrases; the phrases, lowercased; whether a
  match lies in the last prose block (`prose_density.prose_blocks`).
- `narration_opener`: whether the first non-blank line, after stripping a
  leading heading, emphasis, blockquote, or list marker, opens with an
  intent phrase from `OPENER`.
- `file_refs`, `file_line_refs`: file references over the original text, and
  the subset carrying a `:line` or `:line-line` suffix.
- The `prose_density.measure` fields: `prose_words`, `paragraphs`, `items`,
  `sentences`, `mean_sentence_words`, `mean_paragraph_words`,
  `longest_paragraph_words`.

Booleans are returned as booleans; a threshold grader casts with `int()`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import prose_density

TAIL_TITLES = (
    r"(?:next steps?|changes? (?:needed|required)|summary|in summary|notes?|"
    r"what i did|what changed|recommendations?|follow[- ]?ups?|caveats?|"
    r"remaining work|open questions?|what'?s left|what is left|limitations?|"
    r"further work|future work|suggestions?|tl;?dr|conclusion|"
    r"other observations|additional notes?)"
)
# A heading line, or a line that opens with a bold lead-in, whose title begins
# with a frozen tail title: "## Summary", "**Next steps:** ...", "### Notes on
# testing", "__Notes__". Not "**Cause:**", not "**To unblock**", not
# "## Notebook". The title must end at a non-alphanumeric character or the
# line end (`\b` would reject the `_` that closes a `__bold__` run-in).
LEADIN = re.compile(r"^\s*(?:#{1,6}\s+|(?:\*\*|__))\s*(" + TAIL_TITLES + r")(?![A-Za-z0-9])", re.I)

# Any bold run-in label at the start of a line: "**Title:** rest",
# "**Title**: rest", "**Title**" alone. `\1` keeps the marker pair matched.
BOLD_LEADIN = re.compile(r"^\s*(\*\*|__)[^*_\n]+?(?::\1|\1:|\1\s*$)")

OFFER = re.compile(
    r"\b(?:let me know|happy to|want me to|shall i|if you'd like|"
    r"if you would like|feel free|would you like me to|i can also)\b", re.I)

# Same non-alphanumeric lookahead as LEADIN: `\b` would reject "First, run".
OPENER = re.compile(
    r"^(?:I'll|I will|I'm going to|I am going to|Let me|First,|Now I'll|"
    r"Now let me|I need to)(?![A-Za-z0-9])", re.I)

REF = re.compile(
    r"(?<![\w/])(?:[\w.\-]+/)*[\w\-]+\.(?:py|toml|md|json|txt|cfg|ini|yaml|yml|sh)"
    r"(?::\d+(?:-\d+)?)?")

HEADING = re.compile(r"^\s*#{1,6}\s+\S")
# Leading markers stripped before the opener test: heading, blockquote,
# emphasis, list marker, in any combination.
LEADING_MARKERS = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[*_]+|(?:[-*+]|\d+[.)])\s+)*")

BOOLEAN_FIELDS = ("closing_offer_last_block", "narration_opener")


def normalize(text: str) -> str:
    return text.replace("’", "'")


def without_fences(text: str) -> str:
    return prose_density.FENCE.sub("\n\n", text)


def first_line(prose: str) -> str:
    for line in prose.splitlines():
        if line.strip():
            return LEADING_MARKERS.sub("", line, count=1).strip()
    return ""


def scan(text: str) -> dict:
    original = normalize(text)
    prose = without_fences(original)
    lines = prose.splitlines()

    tail_lines = [(index, match.group(1).lower()) for index, match in
                  ((index, LEADIN.match(line)) for index, line in enumerate(lines)) if match]
    tail_first_line = tail_lines[0][0] if tail_lines else None
    tail_words = sum(len(line.split()) for line in lines[tail_first_line:]) if tail_lines else 0

    offers = [match.lower() for match in OFFER.findall(prose)]
    blocks = prose_density.prose_blocks(prose)
    last_block = blocks[-1][1] if blocks else ""

    refs = REF.findall(original)

    density = prose_density.measure(original)
    return {
        "words": len(original.split()),
        "headings": sum(1 for line in lines if HEADING.match(line)),
        "bullets": sum(1 for line in lines if prose_density.LIST_MARKER.match(line)),
        "bold_leadins": sum(1 for line in lines if BOLD_LEADIN.match(line)),
        "tail_section_count": len(tail_lines),
        "tail_section_titles": [title for _, title in tail_lines],
        "tail_first_line": tail_first_line,
        "tail_words": tail_words,
        "closing_offer_count": len(offers),
        "closing_offer_phrases": offers,
        "closing_offer_last_block": bool(OFFER.search(last_block)),
        "narration_opener": bool(OPENER.match(first_line(prose))),
        "file_refs": len(refs),
        "file_line_refs": sum(1 for ref in refs if ":" in ref),
        **{key: value for key, value in density.items() if key != "words"},
    }


def _load_text(path: Path) -> str:
    if path.suffix == ".json":
        payload = json.loads(path.read_text())
        output = payload.get("output")
        if isinstance(output, dict) and isinstance(output.get("text"), str):
            return output["text"]
    return prose_density._load_text(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path,
                        help="text files, sealed trial JSON (output.text), or JSON carrying result/response/text")
    args = parser.parse_args(argv)
    rows = []
    for path in args.paths:
        try:
            row = {"path": str(path), **scan(_load_text(path))}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        rows.append(row)
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
