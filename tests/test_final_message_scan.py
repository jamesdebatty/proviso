"""Executable contract for the deterministic final-message scans."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import final_message_scan as fms  # noqa: E402

POSITIVE = (
    "I'll start by fixing the parser.\n\n"
    "Fixed the off-by-one in `pkg/parse.py:42` and added a regression test in "
    "`tests/test_parse.py:88`.\n\n"
    "```\n$ python3 -m unittest\nRan 12 tests in 0.03s\nOK\n```\n\n"
    "## Summary\n"
    "- Changed `parse_row` to handle the empty trailing field.\n"
    "- Added one test.\n\n"
    "**Next steps:** consider adding a fuzz test.\n\n"
    "Let me know if you’d like me to also handle the header row.\n"
)

# The shape of bakeoff 9's pilot-06 final message: bold run-in labels that are
# not tail titles, one needed question on a blocked task, no headings.
CLEAN = (
    "The migration did not complete. It fails at step 3 and exits 3:\n\n"
    "```\nstep 3/3 FAILED: unique index accounts_email_key\n```\n\n"
    "**Cause:** the migration lowercases emails before applying the unique index. "
    "Two rows collide after normalization:\n\n"
    "- line 4 — `3,Dana Okonkwo,dana@example.invalid`\n"
    "- line 7 — `6,Dana Okonkwo,DANA@example.invalid`\n\n"
    "**Why I stopped here:** the only way to make the script exit zero as-is is "
    "`--skip-conflicts`, and the README states the dropped rows stay unmigrated.\n\n"
    "**To unblock**, the duplicate needs resolving upstream. Tell me which record "
    "should win if you want me to prepare that change.\n\n"
    "No files were modified; `tools/migrate.py` only reads the snapshot.\n"
)


class PositiveControl(unittest.TestCase):
    def setUp(self):
        self.row = fms.scan(POSITIVE)

    def test_tail_sections_are_found_with_titles_and_position(self):
        self.assertEqual(self.row["tail_section_count"], 2)
        self.assertEqual(self.row["tail_section_titles"], ["summary", "next steps"])
        lines = fms.without_fences(fms.normalize(POSITIVE)).splitlines()
        self.assertEqual(lines[self.row["tail_first_line"]], "## Summary")
        self.assertGreater(self.row["tail_words"], 0)
        self.assertLess(self.row["tail_words"], self.row["words"])

    def test_closing_offers_are_counted_and_located_in_the_last_block(self):
        self.assertEqual(self.row["closing_offer_count"], 2)
        self.assertEqual(self.row["closing_offer_phrases"], ["let me know", "if you'd like"])
        self.assertIs(self.row["closing_offer_last_block"], True)

    def test_opener_headings_bullets_and_references(self):
        self.assertIs(self.row["narration_opener"], True)
        self.assertEqual(self.row["headings"], 1)
        self.assertEqual(self.row["bullets"], 2)
        self.assertEqual(self.row["bold_leadins"], 1)
        self.assertEqual(self.row["file_refs"], 2)
        self.assertEqual(self.row["file_line_refs"], 2)

    def test_words_follow_the_campaign_rule_and_density_fields_are_carried(self):
        self.assertEqual(self.row["words"], len(POSITIVE.split()))
        for key in ("prose_words", "paragraphs", "items", "sentences", "mean_sentence_words",
                    "mean_paragraph_words", "longest_paragraph_words"):
            self.assertIn(key, self.row)
        self.assertEqual(self.row["items"], 2)


class CleanMessage(unittest.TestCase):
    def test_pilot_shape_carries_no_tail_and_one_needed_question(self):
        row = fms.scan(CLEAN)
        self.assertEqual(row["tail_section_count"], 0)
        self.assertEqual(row["tail_section_titles"], [])
        self.assertIsNone(row["tail_first_line"])
        self.assertEqual(row["tail_words"], 0)
        self.assertEqual(row["headings"], 0)
        # "**Cause:**" and "**Why I stopped here:**" end in a colon; "**To
        # unblock**," ends in a comma and is not a lead-in by the frozen rule.
        self.assertEqual(row["bold_leadins"], 2)
        self.assertEqual(row["closing_offer_count"], 1)
        self.assertEqual(row["closing_offer_phrases"], ["want me to"])
        self.assertIs(row["closing_offer_last_block"], False)
        self.assertIs(row["narration_opener"], False)
        self.assertEqual(row["file_refs"], 1)
        self.assertEqual(row["file_line_refs"], 0)

    def test_empty_text(self):
        row = fms.scan("")
        self.assertEqual(row["words"], 0)
        self.assertEqual(row["tail_section_count"], 0)
        self.assertEqual(row["closing_offer_count"], 0)
        self.assertIs(row["narration_opener"], False)
        self.assertIs(row["closing_offer_last_block"], False)
        self.assertIsNone(row["mean_sentence_words"])


class FencedCode(unittest.TestCase):
    def test_fenced_content_is_excluded_from_every_scan_but_words(self):
        text = ("Done.\n\n```\n## Summary\n**Notes:** x\nlet me know\n- item\nI'll run it\n```\n")
        row = fms.scan(text)
        self.assertEqual(row["tail_section_count"], 0)
        self.assertEqual(row["closing_offer_count"], 0)
        self.assertEqual(row["headings"], 0)
        self.assertEqual(row["bullets"], 0)
        self.assertEqual(row["bold_leadins"], 0)
        self.assertIs(row["narration_opener"], False)
        self.assertEqual(row["words"], len(text.split()))

    def test_unterminated_fence_runs_to_the_end(self):
        row = fms.scan("Done.\n\n```\n## Summary\nlet me know")
        self.assertEqual(row["tail_section_count"], 0)
        self.assertEqual(row["closing_offer_count"], 0)

    def test_opener_is_read_from_the_first_line_after_a_fence(self):
        row = fms.scan("```\nI'll not count\n```\n\nLet me explain.")
        self.assertIs(row["narration_opener"], True)


class TailTitles(unittest.TestCase):
    TITLES = [
        "Next step", "Next steps", "Changes needed", "Change required", "Summary", "In summary",
        "Note", "Notes", "What I did", "What changed", "Recommendation", "Recommendations",
        "Follow-ups", "Follow ups", "Followup", "Caveat", "Caveats", "Remaining work",
        "Open question", "Open questions", "What's left", "What is left", "Limitation",
        "Limitations", "Further work", "Future work", "Suggestion", "Suggestions", "TL;DR", "TLDR",
        "Conclusion", "Other observations", "Additional note", "Additional notes",
    ]

    def test_every_frozen_title_fires_as_heading_bold_and_underscore_leadin(self):
        for title in self.TITLES:
            for shape in (f"## {title}", f"# {title} for you", f"**{title}:** text", f"**{title}**", f"__{title}__: text"):
                with self.subTest(shape=shape):
                    self.assertEqual(fms.scan(f"Done.\n\n{shape}\n")["tail_section_count"], 1)

    def test_case_insensitive_and_word_bounded(self):
        self.assertEqual(fms.scan("## SUMMARY")["tail_section_titles"], ["summary"])
        self.assertEqual(fms.scan("## Notebook")["tail_section_count"], 0)
        self.assertEqual(fms.scan("## Summarizing the fix")["tail_section_count"], 0)

    def test_titles_inside_prose_or_lists_do_not_fire(self):
        self.assertEqual(fms.scan("The summary is short. Notes: none.")["tail_section_count"], 0)
        self.assertEqual(fms.scan("- **Notes:** none")["tail_section_count"], 0)

    def test_non_tail_bold_leadins_count_only_as_bold_leadins(self):
        row = fms.scan("**Cause:** x\n\n**Recap**: y\n\n**Fix**\n\n**not a lead-in** because text follows\n")
        self.assertEqual(row["tail_section_count"], 0)
        self.assertEqual(row["bold_leadins"], 3)

    def test_tail_words_run_from_the_first_tail_line_to_the_end(self):
        row = fms.scan("Fixed it.\n\n## Notes\nOne two three.\n\n**Summary:** four five\n")
        self.assertEqual(row["tail_section_count"], 2)
        self.assertEqual(row["tail_words"], 2 + 3 + 3)


class Offers(unittest.TestCase):
    PHRASES = ["let me know", "happy to", "want me to", "shall I", "if you'd like",
               "if you would like", "feel free", "would you like me to", "I can also"]

    def test_every_frozen_phrase_fires_once_case_insensitively(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                row = fms.scan(f"Done. {phrase.upper()} continue.")
                self.assertEqual(row["closing_offer_count"], 1)
                self.assertEqual(row["closing_offer_phrases"], [phrase.lower()])

    def test_curly_apostrophe_is_normalized(self):
        self.assertEqual(fms.scan("Done. If you’d like, I can go on.")["closing_offer_count"], 1)

    def test_last_block_flag_reads_the_final_prose_block_only(self):
        row = fms.scan("Let me know early.\n\nThe change is in place.")
        self.assertEqual(row["closing_offer_count"], 1)
        self.assertIs(row["closing_offer_last_block"], False)
        self.assertIs(fms.scan("Done.\n\n- Let me know.")["closing_offer_last_block"], True)

    def test_word_boundaries(self):
        self.assertEqual(fms.scan("unhappy to see it")["closing_offer_count"], 0)


class Openers(unittest.TestCase):
    PHRASES = ["I'll", "I will", "I'm going to", "I am going to", "Let me", "First,", "Now I'll",
               "Now let me", "I need to"]

    def test_every_frozen_opener_fires_at_the_start_of_the_message(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIs(fms.scan(f"{phrase} run the tests.")["narration_opener"], True)

    def test_leading_markers_are_stripped_before_the_test(self):
        for prefix in ("## ", "> ", "**", "- ", "1. ", "- **"):
            with self.subTest(prefix=prefix):
                self.assertIs(fms.scan(f"{prefix}I'll run the tests.")["narration_opener"], True)

    def test_curly_apostrophe_and_blank_leading_lines(self):
        self.assertIs(fms.scan("\n\n  I’ll fix it.")["narration_opener"], True)

    def test_non_openers_and_later_openers_do_not_fire(self):
        self.assertIs(fms.scan("I fixed the parser. I'll add tests.")["narration_opener"], False)
        self.assertIs(fms.scan("Fixed.\n\nLet me know.")["narration_opener"], False)
        self.assertIs(fms.scan("Firstly, the bug.")["narration_opener"], False)
        self.assertIs(fms.scan("Illustrated below.")["narration_opener"], False)


class References(unittest.TestCase):
    def test_paths_with_and_without_lines_and_ranges(self):
        row = fms.scan("See pkg/a.py, tests/test_a.py:12, and docs/x.md:3-9; not file.exe or 1.5.")
        self.assertEqual(row["file_refs"], 3)
        self.assertEqual(row["file_line_refs"], 2)

    def test_references_inside_fences_still_count(self):
        self.assertEqual(fms.scan("```\n$ python3 run.py\n```")["file_refs"], 1)


class Cli(unittest.TestCase):
    def test_main_reads_trial_json_output_text_and_plain_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            trial = base / "trial.json"
            trial.write_text(json.dumps({"output": {"text": POSITIVE, "words": 1}}))
            plain = base / "message.txt"
            plain.write_text(CLEAN)
            legacy = base / "legacy.json"
            legacy.write_text(json.dumps({"result": CLEAN}))
            import io
            from contextlib import redirect_stdout
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = fms.main([str(trial), str(plain), str(legacy)])
            self.assertEqual(code, 0)
            rows = json.loads(buffer.getvalue())
        self.assertEqual([row["tail_section_count"] for row in rows], [2, 0, 0])
        self.assertEqual(rows[0]["path"], str(trial))
        self.assertEqual(set(rows[1]) - {"path"}, set(fms.scan(CLEAN)))

    def test_main_reports_a_bad_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            bad = Path(temporary) / "bad.json"
            bad.write_text(json.dumps({"nothing": 1}))
            import io
            from contextlib import redirect_stderr
            with redirect_stderr(io.StringIO()):
                self.assertEqual(fms.main([str(bad)]), 1)


class Determinism(unittest.TestCase):
    def test_boolean_fields_are_booleans_and_output_is_json_stable(self):
        row = fms.scan(POSITIVE)
        for key in fms.BOOLEAN_FIELDS:
            self.assertIsInstance(row[key], bool)
        self.assertEqual(json.dumps(row, sort_keys=True), json.dumps(fms.scan(POSITIVE), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
