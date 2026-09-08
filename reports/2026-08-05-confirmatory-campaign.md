# Confirmatory campaign: provisional report

Date: 2026-08-05  
Run: `results/runs/opus5-ste-20260805T042413Z`  
Status: automated result complete; human review pending

## Result

The supplied treatment achieved its surface writing goals but failed the
preregistered quality gates. The automated verdict is `refuted`. The formal
verdict remains `indeterminate` until the required human review is complete.

All 60 responses completed with zero run errors. Every answer model resolved to
`claude-opus-5`. All 30 blind judgments completed with zero judge errors and
resolved to `claude-sonnet-5`. Claude Code stayed at version 2.1.222 throughout
both phases.

## Main outcomes

| Measure | Control | STE | Result |
|---|---:|---:|---:|
| Median words | 354 | 234 | -33.9% |
| Mean focus | 3.833 | 4.400 | +0.567 |
| Mean jargon discipline | 3.867 | 4.667 | +0.800 |
| Mean task completion | 4.667 | 4.567 | -0.100 |
| Mean nuance/safety | 4.667 | 4.167 | -0.500 |
| Material errors | 4 | 3 | — |
| Missing requirements | 9 | 12 | — |

Blind pairwise results were 18 control wins, 7 STE wins, and 5 ties. STE's
non-tied win rate was 28%, below the 70% threshold.

## Gate outcome

Passed:

- median word reduction was within the supporting -45% to -15% range;
- focus improved by at least 0.5;
- jargon discipline improved by at least 0.5;
- task completion remained within the -0.25 non-inferiority margin.

Failed:

- STE non-tied win rate was below 70%;
- nuance/safety fell below the -0.25 non-inferiority margin;
- STE had material errors;
- STE omitted required content;
- STE did not pass all three repetitions for every prompt.

## Human review

The validated review packet is
`results/runs/opus5-ste-20260805T042413Z/human-review.json`. It contains 14
pairs: the six frozen sample pairs plus all additional flagged pairs, with
duplicates removed. The packet is bound to the exact reviewed responses and
judgments.

Because the automated result is already `refuted`, human review cannot produce
a supported final verdict under the frozen decision rule. It is still required
to confirm or challenge the model grader's material-error and safety findings
and to close the preregistered study.
