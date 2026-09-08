# Clause bakeoff 10: the Fable 5.1 writing-density instruction on Opus 5

**Report date:** 2026-09-02. Data collected 2026-09-02 (generation 16:31 to 16:58 UTC; Claude judging 16:58 to 17:12 UTC; Codex judging 17:06 to 17:14 UTC). Written the same day.
**Campaign:** `campaigns/clause-bakeoff-10-2026-09-01/`, frozen by `protocol.md` before any live call; H1 to H4 pre-registered with verdict rules.
**Artifacts:** `results/run-2026-09-01/` (75 sealed trials with raw streams, `grades.json`, blind `judgments.json`, `summary.json`), `results/run-2026-09-01-judge/{codex,claude}/` (150 sealed records each, with raw streams and Codex rollouts), `results/run-2026-09-01-analysis.json` (the verdicts below, produced by `analyze.py`).
**Generator:** Claude Opus 5, effort high, no tools, single turn, one fresh workspace outside `$HOME` per trial; Claude Code pinned as a binary copy `2.1.258 (Claude Code)`, sha256 `b6313619…`. All 75 trials record `claude-opus-5` as both init and answer model.
**Judges:** Codex `gpt-5.6-sol` effort high (Codex CLI 0.147.0, bakeoff 8's pinned copy) and Claude Sonnet 5 effort high (the bakeoff 10 pinned binary, `--json-schema`, no tools). Blind, one task at a time, no arm or trial identity. All 300 records resolve to the frozen model identifiers.
**Baseline:** A1, the composite `CLAUDE.md` (Response style + Numbers, `f70f86a92e9f`), byte-identical to bakeoff 8's composite arm and bakeoff 9's A1.

## Executive summary

Neither writing-density instruction from the Fable 5.1 prompting guide does
on Opus 5 what the page says it does on Fable 5.1. Appended to the composite
`CLAUDE.md`, the full "mannered prose" definition (D1) and the one-line
"Please remove all mannered prose." (D2) left sentence length, paragraph
length, and total length where A1 had them, and D1 moved the pooled medians
the wrong way. Both blind judges labelled mannered prose *present* more
often under D1 than under A1. The short instruction cost coverage on one
judge. **Recommendation: do not add either instruction to the Opus 5
`CLAUDE.md`.** The composite stays as it is.

All four pre-registered hypotheses reached a verdict; no power check fired.
The battery provoked the judged defect abundantly (A1 `present` on 15 of 25
by Sonnet and 22 of 25 by Codex), so H3 is a real null-or-worse, not
silence.

## Pre-registered hypotheses

- **H1, the full instruction reduces density (D1 vs A1): REFUTED.** Pooled
  median mean-words-per-sentence rose 17.50 to 18.75 (+7.1%); pooled median
  mean-words-per-paragraph rose 46.82 to 49.71 (+6.2%). Task medians were
  lower in D1 on 3 of 5 tasks for each measure, and not the same three.
  The rule refutes on a pooled rise in either measure.
- **H2, the short instruction reduces density (D2 vs A1): REFUTED.**
  Sentences 17.50 to 18.24 (+4.2%); paragraphs 46.82 to 46.53 (−0.6%).
  Task medians lower on 3 of 5 for each measure. The rule refutes on a
  pooled rise (sentences) and on a fall under 5% with tasks split 3–2
  (paragraphs).
- **H3, mannered prose is judged less often (D1 vs A1): REFUTED.** Power
  check passed for both judges. `present` rate, A1 to D1: Sonnet 0.60 to
  0.72 (15 to 18 of 25); Codex 0.88 to 1.00 (22 to 25 of 25). Neither judge
  read D1 as lower. D2 was flat: Sonnet 0.60, Codex 0.92.
- **H4, no harm: SUPPORTED for D1, REFUTED for D2.** D1: pooled median words
  1052 vs 993 (105.9%, within the 110% cap); `incomplete` 3 vs 3 (Sonnet)
  and 3 vs 5 (Codex), neither above A1. D2: words 1022 (102.9%), pass;
  Codex `incomplete` 5 vs 5, pass; Sonnet `incomplete` 5 vs 3, fail. One
  failing cell refutes the arm on harm, as the rule says.

## Results

All figures are from `results/run-2026-09-01-analysis.json` unless marked
*recomputed*, which means derived from the sealed trial and judge files
during report preparation by ad-hoc scripts that are not committed.

### Pooled medians over 25 responses per arm

| Measure | A1 | D1 (full instruction) | D2 (short instruction) |
| --- | ---: | ---: | ---: |
| Mean words per sentence | 17.50 | 18.75 | 18.24 |
| Mean words per paragraph | 46.82 | 49.71 | 46.53 |
| Words | 993 | 1052 | 1022 |
| Paragraphs | 15 | 15 | 15 |
| List items | 11 | 9 | 11 |
| Passes, sentence split ≤18 (of 25) | 14 | 11 | 12 |
| Passes, paragraph split ≤42 (of 25) | 11 | 8 | 10 |
| Passes, words ≤1093 (of 25) | 15 | 16 | 17 |
| Sonnet mannered prose `present` (of 25) | 15 | 18 | 15 |
| Codex mannered prose `present` (of 25) | 22 | 25 | 23 |
| Sonnet coverage `incomplete` (of 25) | 3 | 3 | 5 |
| Codex coverage `incomplete` (of 25) | 5 | 3 | 5 |

Live A1 landed close to the bakeoff 8 base rates the descriptive splits
were cut at (18.36 words per sentence, 41.71 per paragraph, 994 words on
Claude Code 2.1.232): 17.50, 46.82, and 993 on 2.1.258. The splits are
reported as declared; the arm contrast does not depend on them.

### Task medians over five repetitions

Words per sentence / words per paragraph / words.

| Task | A1 | D1 | D2 |
| --- | --- | --- | --- |
| entitlement-drift-mechanism | 16.54 / 41.78 / 957 | 16.48 / 39.58 / 1052 | 16.34 / 41.56 / 925 |
| retry-storm-interaction | 21.77 / 62.25 / 1100 | 19.57 / 73.08 / 1038 | 21.72 / 78.25 / 984 |
| scheduler-ownership-tradeoff | 17.48 / 54.47 / 989 | 20.97 / 53.00 / 1088 | 18.74 / 42.50 / 1033 |
| tail-latency-narrowing | 17.42 / 40.88 / 946 | 16.66 / 33.56 / 811 | 17.22 / 34.80 / 898 |
| terms-of-art-explainer | 17.50 / 48.50 / 1389 | 19.91 / 49.71 / 1363 | 18.58 / 48.89 / 1400 |

The one task where both instructions shortened everything is
`tail-latency-narrowing`; the one where paragraphs got much longer is
`retry-storm-interaction`, where the median response under D1 and D2 used no
list items at all against A1's two (*recomputed*). That is the formatting
shift the protocol warned about: text that leaves lists joins paragraphs and
lifts the paragraph mean. It is visible, and it does not rescue H1 or H2,
whose sentence measure is not affected by it in the same direction.

### Judged labels by task and arm (*recomputed* from the analysis rows)

`present` counts, Sonnet / Codex, of 5 per cell:

| Task | A1 | D1 | D2 |
| --- | --- | --- | --- |
| entitlement-drift-mechanism | 2 / 3 | 4 / 5 | 2 / 3 |
| retry-storm-interaction | 4 / 4 | 3 / 5 | 3 / 5 |
| scheduler-ownership-tradeoff | 3 / 5 | 4 / 5 | 3 / 5 |
| tail-latency-narrowing | 3 / 5 | 3 / 5 | 2 / 5 |
| terms-of-art-explainer | 3 / 5 | 4 / 5 | 5 / 5 |

`incomplete` counts, Sonnet / Codex, of 5 per cell: every A1 and D1 entry is
on `scheduler-ownership-tradeoff` (3 / 5, 3 / 3, and for D2 3 / 4). D2's two
extra Sonnet entries are one each on `entitlement-drift-mechanism` (Sonnet
only) and `retry-storm-interaction` (both judges). The H4 refutation of D2
rests on those two responses.

Judge exact agreement: coverage 0.92, mannered prose 0.68 (n = 75 each).
Codex applies the mannered-prose rubric far more readily than Sonnet (70
against 48 `present` of 75), which is why the two are reported separately and
never averaged.

What the judges flagged under D1 is the same register they flagged under A1:
"reconciliation is papering over it indefinitely", "It is the safety net,
not the primary mechanism", "every field you move out of it is a class of bug
you delete". None of the D1 excerpts echo the clause's own wording, so the
blinding limitation the protocol recorded (a response quoting its clause
back) did not materialize in the excerpts.

## Deviations and incidents

- **Two discarded dispatch attempts, no response retained.** Recorded before
  this run in protocol amendments 2026-09-01d and 2026-09-01e, with their
  failure records preserved under `results/run-2026-09-01-attempt{1,2}/`.
  Both were a 401 from a stale `CLAUDE_CODE_OAUTH_TOKEN` in the dispatching
  shell; attempt 1's guard hid it. The adapter now strips that variable and
  the three Anthropic key and base-URL variables from every trial, and each
  of the 75 trials here records `stripped_env: ["CLAUDE_CODE_OAUTH_TOKEN"]`,
  values never read. The run billed the pinned binary's subscription login.
- **The judge's sanitizer was changed after generation and before any
  Codex record existed.** `scripts/clause_judge.py` refused every Codex
  rollout because Codex 0.147.0's built-in instructions contain the phrase
  "basic confirmations", which the capture spine's case-insensitive
  `Basic <token>` pattern reads as an authorization value. That is the same
  word-keyed-sanitizer defect amendment 2026-09-01d fixed for model prose.
  The judge now applies the campaign's strict credential scan (unmistakable
  key shapes only, still refusing reminder payloads) to its streams and
  rollouts; `tests/test_clause_judge.py` covers the accepted phrase and a
  refused bearer value. The first Codex pass was stopped after roughly four
  minutes with zero records written; the number of subscription calls it
  wasted is not recorded. Sonnet's 148 records written before the change
  pass the new check too, since the strict scan is a subset of the old one.
  `clause_judge.py` is not covered by the plan hash, so the sealed run is
  unaffected.
- **Two Sonnet judge tasks exited 1 with empty stderr** on the first pass
  and succeeded on resume; no record was written for the failed calls.
- **Codex saw James's skill catalogue.** Every Codex rollout carries a
  developer message listing the 49 skills under `~/.agents/skills`, which
  Codex reads regardless of `CODEX_HOME`. The judge was told to use no tools
  and ran read-only in a temp directory, and the catalogue contains no
  treatment vocabulary (zero occurrences of "mannered" or "density";
  "writing" appears eight times in ordinary skill descriptions), so this is
  an isolation gap in the transport rather than a blinding break. Sonnet's
  sessions used `--setting-sources project` in an empty directory and saw
  nothing of the kind. The rollouts also carry those skill paths under the operator's home
  directory; no credential and no email address appears in any retained
  artifact (scanned before commit).
- **`summary.json` says `synthetic-integration-only`.** The harness writes
  that label for every adapter; T-024 records the defect. Evidence class here
  is read from `plan.execution.adapter` (`claude-code/1`), not from the label.
- **Cost.** Generation $9.60 across 75 responses (median $0.134, 251k input
  and 281k output tokens, *recomputed* from the trial usage records). Judge
  cost is not recorded by either transport.

## Limitations

- Five long-form systems-design prompts in English, five repetitions each,
  one model, one operator. The result is a property of this battery. A
  sign-test reading needs 5 of 5 tasks in one direction; no measure got
  past 3 of 5 in either direction, so the deterministic result is "no
  detectable shift", not a measured effect size.
- The mannered-prose rubric labels most technical prose `present` for one
  judge (Codex 0.88 at baseline), so H3 reads direction only. A calibrated
  reference set for that class does not exist in this project.
- Structural proxies move with formatting. The `retry-storm-interaction`
  paragraph means show how; the counts are reported so it is visible.
- A null on Opus 5 says nothing about Fable 5.1, for which the instruction
  is published. It is evidence only that the instruction does not transfer
  to this model on this battery.
- Judge two shares a vendor with the generator (amendment 2026-09-01b).

## What this changes downstream

- The live `~/.claude/CLAUDE.md` does not change. Claim C047 in
  `sources/claim-ledger.csv` moves from `indeterminate` to `refuted`.
- The `claude-code/1` adapter has now carried one authorized campaign end to
  end and its output has been consumed by `analyze.py`; T-023 closes on this
  run. T-024 is opened for the summary label.
- `scripts/clause_judge.py` and the adapter both now scan model-facing
  text for credential shapes only. Any future transport whose own
  instructions or rollouts reach a sanitizer should expect the same class of
  false positive.

## Verified

`Verified`. `python3 scripts/clause_campaign.py verify campaigns/clause-bakeoff-10-2026-09-01/results/run-2026-09-01`, exit 0, on 2026-09-02: 75 trials, every sealed hash rederives, every raw stream matches its trial.

`Verified`. `python3 scripts/clause_judge.py verify … --judge codex` and `--judge claude`, exit 0: 150 records each, 0 missing, every judgment rederives from its raw stream, every Codex rollout names `gpt-5.6-sol`, every Sonnet stream names `claude-sonnet-5`.

`Verified`. `python3 campaigns/clause-bakeoff-10-2026-09-01/analyze.py … --out results/run-2026-09-01-analysis.json`, exit 0; the verdicts above are its output.

`Verified`. `python3 -m unittest discover -s tests`, exit 0, 731 tests, 0 failed, 0 skipped, after the judge sanitizer change. `python3 scripts/clause_campaign.py check campaigns/clause-bakeoff-10-2026-09-01/campaign.toml` still materializes plan `1b8cbcf9…`, the hash the run's authorization names.

`Implemented-unverified`. The *recomputed* figures (per-task label counts, list-item medians, token and cost sums, excerpt sampling) came from ad-hoc scripts during preparation and are not committed as a reproducible check.

## The instructions as tested

D1 appends this paragraph to A1 (`variants/density-clause-long.md`); D2 appends only the final sentence, "Please remove all mannered prose." (`variants/density-clause-short.md`). Both texts are verbatim from the Fable 5.1 prompting guide's Writing density section (source S039).

> Mannered prose substitutes metaphor and flourish for direct statement. Instead of "a parameter worth varying," the mannered writer produces "a dial worth turning." Instead of "this point still matters," they write "this point earns its keep." The phrases exist to display the writer, not to convey the idea, and readers can tell. That is why mannered prose irritates: it makes the reader work harder so the writer can perform. It is also imprecise. Metaphors drag in connotations the writer did not choose and cannot control. The fix is to say what you mean. When a literal phrase is available, use it.
