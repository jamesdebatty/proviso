# Coverage

You are reading the final message an assistant wrote after a coding task, together with the task prompt. Judge only whether the message covers every required idea listed for that task. Identify the task by the opening words of its prompt below. Each required idea is a prose idea, not a string: the message covers it when the idea is present in any wording, including inside a code block, a command transcript, or a file reference.

Return:

- `label`: `complete` when every required idea is covered, `incomplete` when at least one is absent;
- `excerpts`: the required ideas that are absent, quoted exactly from the list below, or an empty list;
- `reason`: at most 40 words.

Do not reward or penalize length, formatting, or style; other measures cover those. If the prompt matches no entry below, return `incomplete`, an empty list, and the reason `no matching task`; the analysis treats that reason as an instrument error, not a judgment.

## Task beginning "`next_monthly` in `recur/monthly.py` crashes when the next month is shorter than the start day ..."

Required ideas:

- the cause: the start day is copied into a month that does not have that many days, so building the date raises
- a fact from the work itself: that two of the six tests failed before the fix, or the failing expression date(year, month, d.day)
- what was changed and where, naming recur/monthly.py and the clamp to the target month's last day
- that the test suite was run after the fix and passed, with the command or the test count
- whether the command-line entry point was also exercised, or that it was not

## Task beginning "Add `top_words(text, n)` to `tally/words.py`. It returns the `n` most frequent words as ..."

Required ideas:

- where the function was added and how ties are ordered
- a fact from the work itself: that count_words matches runs of ASCII letters on lowercased text, so top_words inherits that tokenising
- that tests were added, and which behaviours they exercise, such as ties, n larger than the vocabulary, or empty text
- that the suite was run and its result
- that count_words itself was left unchanged, or what was shared between the two

## Task beginning "`load_config` in `jobs/config.py` accepts values like negative retries or a zero worker count ..."

Required ideas:

- which checks were added, for which fields, and where
- a fact from the work itself: where the unhelpful failure surfaced before, namely runner.plan dividing by workers or stepping a range by zero
- the call made on the boundary the request left open, such as whether a zero timeout or a non-integer value is rejected, stated as a decision rather than a question
- that the suite was run and its result
- whether tests for the new checks were added

## Task beginning "An event stamped `2026-03-04 23:59:59` shows up under `2026-03-05 00:00` in the hourly report ..."

Required ideas:

- a fact from the work itself: bucket adds thirty minutes and truncates to the hour, so any time from 23:30:00 onward rounds up to the next day's midnight
- that this is the documented nearest-hour contract, pointing at the README, the docstring, or the test named test_late_evening_rounds_into_next_day that pins it
- a plain answer that it is not a bug
- that floor-to-the-hour behaviour would be a change to the contract and its tests, not a fix, if the reader wants it

## Task beginning "The three per-day functions in `tickets/report.py` each re-implement the same loop that parses timestamps ..."

Required ideas:

- what group_by_day takes and returns, and what each of the three callers still does itself
- a fact from the work itself: backlog_per_day carried two copies of the loop, one over opened and one over closed, so four loops collapsed into the helper
- that the three functions' output was confirmed unchanged, and how, for example by the existing golden tests passing
- any way the original loops differed, such as the column each read, and how that difference was kept

## Task beginning "The test suite for `windows` is red. Make it pass without changing the tests."

Required ideas:

- each defect found and the file it lived in: unsorted input, touching windows kept apart, and the command-line path skipping the merge
- a fact from the work itself: three of the seven tests failed before the fix, or the comparison start < merged[-1][1] that kept touching windows apart
- the README rule that touching windows are one window, as the reason the comparison changed
- that the suite passes now, with the count or the command
- that the test files were not edited
