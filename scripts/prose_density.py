#!/usr/bin/env python3
"""Deterministic prose-density measurements over a response text.

The rules are fixed so that a measurement can be recomputed from the stored
response bytes alone. They are deliberately simple and are applied identically
to every arm; they measure relative density, not writing quality.

Text handling:

- Fenced code blocks are removed before measuring.
- Headings (`#` lines) and table rows (`|` lines) are not prose and are skipped.
- A paragraph is a run of non-blank prose lines separated by blank lines.
- A list item (a line starting with `-`, `*`, `+`, or `1.`/`1)`) is a block of
  its own and is never part of a paragraph.
- A sentence ends at `.`, `!`, or `?` followed by whitespace or end of block.
- A word is a whitespace-delimited token, the same rule `clause_campaign.py`
  uses for `output.words`.

`mean_sentence_words` is taken over every prose block, paragraphs and list
items alike, because both carry sentences. `mean_paragraph_words` is taken over
paragraphs only, because the guidance under test concerns paragraph breaks in
running prose and a bulleted answer would otherwise satisfy it by construction.
Both are `null` when no block of that kind exists; a threshold measure treats
`null` as a failure to measure, not as a pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
HEADING = re.compile(r"^\s*#{1,6}\s+")
TABLE_ROW = re.compile(r"^\s*\|")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def prose_blocks(text: str) -> list[tuple[str, str]]:
    """Return `(kind, text)` blocks where kind is `paragraph` or `item`."""
    blocks: list[tuple[str, str]] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append(("paragraph", " ".join(current)))
            current.clear()

    for line in FENCE.sub("\n\n", text).splitlines():
        stripped = line.strip()
        if not stripped or HEADING.match(line) or TABLE_ROW.match(line):
            flush()
            continue
        if LIST_MARKER.match(line):
            flush()
            blocks.append(("item", LIST_MARKER.sub("", line, count=1).strip()))
            continue
        current.append(stripped)
    flush()
    return blocks


def sentences(block: str) -> list[str]:
    return [part for part in SENTENCE_END.split(block.strip()) if part.strip()]


def measure(text: str) -> dict:
    blocks = prose_blocks(text)
    paragraphs = [body for kind, body in blocks if kind == "paragraph"]
    items = [body for kind, body in blocks if kind == "item"]
    sentence_count = sum(len(sentences(body)) for _, body in blocks)
    prose_words = sum(len(body.split()) for _, body in blocks)
    paragraph_words = sum(len(body.split()) for body in paragraphs)
    return {
        "words": len(text.split()),
        "prose_words": prose_words,
        "paragraphs": len(paragraphs),
        "items": len(items),
        "sentences": sentence_count,
        "mean_sentence_words": (
            round(prose_words / sentence_count, 2) if sentence_count else None
        ),
        "mean_paragraph_words": (
            round(paragraph_words / len(paragraphs), 2) if paragraphs else None
        ),
        "longest_paragraph_words": max((len(body.split()) for body in paragraphs), default=0),
    }


def _load_text(path: Path) -> str:
    if path.suffix == ".json":
        payload = json.loads(path.read_text())
        for key in ("result", "response", "text"):
            if isinstance(payload.get(key), str):
                return payload[key]
        raise ValueError(f"{path}: no result, response, or text string")
    return path.read_text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path,
                        help="text files, or JSON files carrying result/response/text")
    args = parser.parse_args(argv)
    rows = []
    for path in args.paths:
        try:
            row = {"path": str(path), **measure(_load_text(path))}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        rows.append(row)
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
