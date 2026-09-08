"""Executable contract for the deterministic prose-density rules."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prose_density as pd  # noqa: E402

SAMPLE = (
    "# Heading is not prose\n\n"
    "First sentence here. Second one! Third?\n\n"
    "- item one is short.\n"
    "1. numbered item\n\n"
    "```\ncode. is. not. prose.\n```\n\n"
    "| col | col |\n|---|---|\n\n"
    "Last paragraph spans\ntwo lines. Done."
)


class Blocks(unittest.TestCase):
    def test_blocks_skip_headings_tables_and_fences_and_split_list_items(self):
        self.assertEqual(pd.prose_blocks(SAMPLE), [
            ("paragraph", "First sentence here. Second one! Third?"),
            ("item", "item one is short."),
            ("item", "numbered item"),
            ("paragraph", "Last paragraph spans two lines. Done."),
        ])

    def test_unterminated_fence_is_dropped_to_end_of_text(self):
        self.assertEqual(pd.prose_blocks("Real. Prose.\n\n```\nnever closed"),
                         [("paragraph", "Real. Prose.")])

    def test_sentences_end_at_terminal_punctuation_followed_by_space(self):
        self.assertEqual(pd.sentences("One. Two! Three? Four e.g. five"),
                         ["One.", "Two!", "Three?", "Four e.g.", "five"])


class Measure(unittest.TestCase):
    def test_measure_reports_every_field_from_fixed_rules(self):
        self.assertEqual(pd.measure(SAMPLE), {
            "words": 37,
            "prose_words": 18,
            "paragraphs": 2,
            "items": 2,
            "sentences": 7,
            "mean_sentence_words": 2.57,
            "mean_paragraph_words": 6.0,
            "longest_paragraph_words": 6,
        })

    def test_means_are_null_when_nothing_of_that_kind_exists(self):
        empty = pd.measure("")
        self.assertIsNone(empty["mean_sentence_words"])
        self.assertIsNone(empty["mean_paragraph_words"])
        items_only = pd.measure("- only\n- items")
        self.assertEqual(items_only["mean_sentence_words"], 1.0)
        self.assertIsNone(items_only["mean_paragraph_words"])
        self.assertEqual(items_only["paragraphs"], 0)

    def test_paragraph_mean_excludes_list_items_but_sentence_mean_includes_them(self):
        text = "Ten words in this single paragraph sentence right here now.\n\n- two words\n- two more"
        result = pd.measure(text)
        self.assertEqual(result["mean_paragraph_words"], 10.0)
        self.assertEqual(result["sentences"], 3)
        self.assertEqual(result["mean_sentence_words"], round(14 / 3, 2))


class CommandLine(unittest.TestCase):
    def test_cli_reads_text_and_json_result_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            text = Path(temporary) / "a.md"
            text.write_text("One two. Three.")
            payload = Path(temporary) / "b.json"
            payload.write_text(json.dumps({"result": "Four five six."}))
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = pd.main([str(text), str(payload)])
        self.assertEqual(code, 0)
        rows = json.loads(out.getvalue())
        self.assertEqual([row["sentences"] for row in rows], [2, 1])
        self.assertEqual(rows[1]["path"], str(payload))


if __name__ == "__main__":
    unittest.main()
