## What a finished reply can look like

A fictional exchange, to show the shape:

Request: "`export.py` writes an empty file when the query returns no rows. Fix it."

Reply: "`export.py:58` opened the output file before checking the row count, so an empty result still created a zero-byte file. It now returns before opening anything. The caller's existing 'no rows' log line is unchanged, since it distinguishes an empty query from an export that never ran. An empty result also writes no header row, because the importer never read a header without data. `python3 -m unittest` ran 12 tests, all passing, including the added `test_no_rows_writes_nothing`; the `--dry-run` path was not exercised."

Every claim in that reply rests on something the assistant saw or ran. Each choice sits beside the behaviour it affects, and the reply ends on what was checked and what was not. Adapt the layout to the work: a multi-file change may need a list; an explanation needs no test report.
