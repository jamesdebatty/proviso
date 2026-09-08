# Clause bakeoff 7: the no-invented-numbers addition

**Date:** 2026-08-11
**Campaign:** `campaigns/clause-bakeoff-7-2026-08-09/`
**Artifacts:** `out/bakeoff-20260811T000310Z/` (50 responses, 50 judgments, `bakeoff-results.json`)
**Generator:** Claude Opus 5 High, no tools, single turn, isolated per-response project; CLI pinned `2.1.226 (Claude Code)` (binary copy in `~/.claude-eval-pins/bakeoff7/`)
**Judges:** Claude Sonnet 5 High + Codex `gpt-5.6-sol` High, blind A/B, isolated; Codex CLI pinned `0.147.0` (binary copy)
**Protocol:** frozen before live calls (`protocol.md`), H1–H4 pre-registered
**Baseline:** `v2-only` — the bakeoff-6 recommended clause. This round's question is compositional: does an addition help *on top of* the proven clause, and does the v2 profile survive?

## Executive summary

The `no-invented-numbers` clause — two sentences appended to guarded-subtractive-v2
as a `## Numbers` section — produced the strongest candidate-vs-control result
of the project's seven campaigns. On a battery built to provoke fabricated
numeric precision, it cut invented-precision entries **59% (Sonnet) and 53%
(Codex)** versus the v2-only baseline, without suppressing legitimate
arithmetic: on the task where computing a figure from given numbers is
*correct*, the candidate derived it cleanly in 5/5 repetitions. Nuance rose
+0.40 (Sonnet) and +0.36 (Codex); confirmed error findings fell from 7 to 3;
pooled preference went 66.7% to the candidate. Median words dropped a further
7%, so the concision clause survives composition intact.

Formal status is `needs_human_review` — the frozen error gates again require
what no arm achieves (zero findings) — but every comparative measure,
including both error measures, favors the candidate. Pending James's
same-defect review, the recommended CLAUDE.md is the composite:
**v2 + no-invented-numbers**.

## Pre-registered hypotheses

- **H1 — the clause reduces invented precision: TRUE.** Pooled
  invented-precision entries 48 vs 108; per judge 18 vs 44 (Sonnet), 30 vs 64
  (Codex) — strictly below on both, far past the pre-registered bar. The
  programmatic instrument agrees: median novel numerals (numerals not present
  in or trivially derived from the prompt) 8 vs 11.
- **H2 — no over-suppression of derivable numbers: TRUE, 5/5.** On
  `log-retention-derivable` (the ~60 GB steady-state figure is computable from
  given quantities), Sonnet logged zero missing-requirement entries against
  the candidate in all five repetitions. The clause distinguishes "don't
  invent" from "don't compute."
- **H3 — assumptions surfaced, not silenced: TRUE, 4/5.** On
  `backfill-estimate`, the explicit-assumption rubric item was satisfied in
  4 of 5 candidate repetitions (r2 flagged), exactly the pre-registered
  threshold.
- **H4 — the v2 profile survives composition: PARTIAL.** Five of seven frozen
  gates pass; the two error gates fail formally, pending the same-defect
  human review the protocol assigns to that step.

## Results

| Measure | v2-only | v2-plus-numbers |
| --- | ---: | ---: |
| Median words | 367 | **340 (−7.4%)** |
| Median novel numerals | 11 | **8** |
| Stalled responses (of 25) | 0 | 0 |
| Sonnet invented-precision entries | 44 | **18 (−59%)** |
| Codex invented-precision entries | 64 | **30 (−53%)** |
| Sonnet nuance (mean /5) | 4.24 | **4.64 (+0.40)** |
| Codex nuance (mean /5) | 3.04 | **3.40 (+0.36)** |
| Sonnet task completion | 4.44 | **4.68** |
| Codex task completion | 3.84 | **4.28** |
| Sonnet error allegations | 10 | **3** |
| Codex error allegations | 71 | **52** |
| Sonnet omission entries | 11 | **8** |
| Codex omission entries | 22 | **21** |
| Confirmed material-error findings | 7 | **3** |
| Unresolved disputed findings | 17 | 20 |

Pooled pairwise preference: candidate 32, baseline 16, tie 2 — **66.7%**
non-tied win rate (Sonnet 65.2%, Codex 68.0%). Judge pairwise agreement:
0.68 (bakeoff 6: 0.44).

### Gate table (v2-plus-numbers, baseline-relative per this round's frozen protocol)

| Frozen gate | Result |
| --- | --- |
| Invented precision ≤ baseline, per judge | **PASS** |
| Omissions ≤ baseline, per judge | **PASS** (8≤11, 21≤22) |
| Nuance delta ≥ −0.25, per judge | **PASS** (+0.40, +0.36) |
| Median words ≤ 110% of baseline | **PASS** (93%) |
| Stalls ≤ baseline | **PASS** (0 vs 0) |
| No confirmed material errors | **FAIL** (3; baseline: 7) |
| No unresolved disputed errors | **FAIL** (20; baseline: 17) |

## The battery worked as an instrument

The five fresh tasks were designed to tempt fabricated precision, and the
baseline obliged. Its confirmed findings are the target defect verbatim:
confidence stated as "maybe 60/40 in favor," capacity advice as "provision to
3× that" and "2–3× estimated load" presented as derived rules, "40,000
messages is small for a healthy consumer fleet — typically…," a backfill
recast as "500M inserts," and a mislabeled "the other 300 GB." Seven baseline
findings were confirmed against three for the candidate — the clause arm
mostly declined the bait, and H2/H3 show it did so without refusing legitimate
computation or hiding its assumptions.

The error-gate failures repeat bakeoff 6's structural lesson: the zero-findings
gates fail every arm ever tested, including no-treatment controls, and the
disputed queue is again dominated by single-judge Codex "too categorical"
allegations of the class James dismissed wholesale in the bakeoff-6 review.
This round's protocol moved the omission/precision/word gates to
baseline-relative form; the error gates remain zero-form and remain the
project's known instrument defect.

## Bottom lines

- Two sentences of conditioned, subtractive instruction measurably halved
  Opus 5's fabricated-precision behavior on a battery built to provoke it —
  with zero over-suppression cost detected and the concision profile intact.
- This is the project's first *compositional* result: clauses can be stacked
  without the earlier clause's gains degrading (words −7%, nuance up,
  omissions down).
- The candidate beat the baseline on every comparative measure recorded,
  including both error tallies. The formal `needs_human_review` status is a
  property of the zero-form error gates, not of the candidate's performance.
- Pending the same-defect review of 10 confirmed findings (7 baseline, 3
  candidate), the recommended CLAUDE.md is the composite v2 +
  no-invented-numbers, reproduced below.

## Limitations

- All invented-precision counts are judge allegations under a new rubric item
  used here for the first time; no human audit of that item's precision has
  been performed yet. The programmatic novel-numeral counter corroborates the
  direction but counts numerals, not claims.
- The battery was adversarial toward the target defect by design; the −59%/−53%
  effect size should not be quoted as an expected rate on neutral workloads.
- n=25 sets; the 66.7% preference result is directionally consistent with
  every other measure but at this n preference has not historically
  replicated; the precision, nuance, and length measures are load-bearing.
- Codex judged under 0.147.0 here vs 0.146.1 in bakeoff 6; cross-run Codex
  tallies are not comparable (its allegation volume is battery- and
  version-sensitive). All comparisons in this report are within-run.
- The composite has been tested against v2-only, not against a no-clause
  control; the concision deltas versus "no CLAUDE.md at all" rest on bakeoff
  6's result.

## Deviations and incidents (none affect validity)

- One generation cell hit the 10-minute provider timeout; the run completed
  49/50, and an identical relaunch backfilled the missing cell from a cold
  start with the other 49 replayed from hash-validated cache (final:
  50/50, exit 0).
- Host-session restarts orphaned the monitoring watchers repeatedly; the
  generation and judging jobs themselves ran detached (`nohup`, out-of-tree
  process group) and survived every restart — the hardening adopted after
  bakeoff 6.
- `/tmp` was wiped mid-campaign (machine reboot), taking the out-dir pointer
  file and the old symlink-based CLI pins; the binary-copy pins in
  `~/.claude-eval-pins/` (adopted this round after the auto-updater
  garbage-collected the 2.1.222 binary during bakeoff 6) were unaffected.
  All 50 judgments ran under the frozen pinned versions.

## The composite clause (exact text of `variants/v2-plus-numbers.md`)

```markdown
## Response style

Answer the question asked, then stop.

Do not: open with a preamble or a restatement of the question; narrate what you
are about to do; close with a summary of what you just said; repeat a point you
have already made; or add caveats, alternatives, or adjacent topics the
question did not ask about.

Keep every fact, risk, precondition, check, and step the reader needs to act
correctly — cutting the items above must never remove these. This is a rule
about what to remove, not an instruction to add anything.

## Numbers

Do not present a number you assumed or estimated as if it were given or
derived. When a quantity the answer depends on is not stated, say it is
unknown and, if useful, state your assumption explicitly before using it.
```
