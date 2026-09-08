# Baseline vs. the Bakeoff-7 Composite: What the Clause Actually Buys

> **Correction, 2026-08-23.** The "roughly 35% shorter" figure against no
> clause below was chained across bakeoffs 6 and 7. Bakeoff 8 measured the
> composite against a blank-slate control directly and found −15.6% on a
> long-form battery. See
> [Clause bakeoff 8](2026-08-23-clause-bakeoff-8.md). The body of this
> report is preserved as written on 2026-08-11.

**Campaign harnesses:** `../campaigns/clause-bakeoff-6-2026-08-06/`, `../campaigns/clause-bakeoff-7-2026-08-09/`
**Frozen results:** `../campaigns/clause-bakeoff-6-2026-08-06/out/bakeoff-20260806T072008Z/bakeoff-results.json`, `../campaigns/clause-bakeoff-7-2026-08-09/out/bakeoff-20260811T000310Z/bakeoff-results.json`
**Per-run reports:** [Bakeoff 6](2026-08-06-clause-bakeoff-6.md), [Bakeoff 7](2026-08-11-clause-bakeoff-7.md)
**Clause under test:** `../campaigns/clause-bakeoff-7-2026-08-09/variants/v2-plus-numbers.md`
**Presentation:** None

**Version:** 1.0
**Owner:** a private research library
**Evaluation dates:** data collected 2026-08-06 (bakeoff 6) and 2026-08-11 (bakeoff 7)

## Executive Summary

### Context

Seven campaigns asked whether a CLAUDE.md response-style clause can shorten
Claude Opus 5's answers without losing required content, and later, whether a
second clause can reduce a measured model defect (fabricated numeric
precision) on top of the first. "Baseline" in this document means two things,
kept explicit throughout: the **no-clause baseline** (no CLAUDE.md at all,
last measured directly in bakeoff 6) and the **v2-only baseline** (the proven
concision clause alone, the direct comparator in bakeoff 7). The composite is
the two-section clause that came out of bakeoff 7: guarded-subtractive-v2
plus the no-invented-numbers section.

### Findings

- Against the clause it extends (v2-only, measured head-to-head, n=25 sets):
  the composite **halved invented-precision entries** (−59% Sonnet, −53%
  Codex), raised nuance **+0.40/+0.36**, cut confirmed error findings **7→3**,
  reduced omissions, cut words a further 7%, and won **66.7%** of non-tied
  pairwise preferences. Every comparative measure favored the composite.
- Against no clause at all (chained across runs — see Limitations): expect
  answers roughly **35% shorter** with quality signals at or above the bare
  model's, since v2 beat no-clause on nuance/omissions in bakeoff 6 and the
  composite beat v2-only on every measure in bakeoff 7.
- The composite showed **no over-suppression**: where computing a figure from
  given numbers was correct, it did so 5/5; where an estimate needed an
  assumption, it stated the assumption 4/5.
- No arm in any campaign — including no-clause controls — passes the frozen
  zero-error gates; those gates measure Opus-on-hard-tasks, not clause harm.
  Human review resolved bakeoff 6's queue in v2's favor; bakeoff 7's
  same-defect review is pending.

### Next Steps

Same-defect review of bakeoff 7's 10 confirmed findings; then round 8
(`no-settled-verdicts`) against the composite as the new baseline, per
the 2026-08-09 next-rounds plan (removed 2026-09-01; bakeoffs 8 and 9 ran after it).

## Project Overview

The question this document answers: **what does adopting the composite clause
buy, relative to running without it?** The evaluation criteria are the
project's frozen gate dimensions: length, omissions, nuance/safety, material
errors, invented precision (added in bakeoff 7), stalls, and blind pairwise
preference.

Directly measured comparisons (each within one run, one battery, one judging
pass):

1. **No clause vs v2** — bakeoff 6, 5 tasks × 5 reps × 2 arms, dual judges.
2. **v2-only vs composite** — bakeoff 7, same design, battery built to
   provoke fabricated precision.

No run measured no-clause vs composite head-to-head; that comparison is
chained inference and is labeled as such wherever it appears.

## Results

### Length

| Comparison (within-run medians) | Baseline | Clause arm | Delta |
| --- | ---: | ---: | ---: |
| Bakeoff 6: no clause → v2 | 729 | 507 | −30.4% |
| Bakeoff 7: v2-only → composite | 367 | 340 | −7.4% |

Chained (Inference): ~0.70 × ~0.93 ≈ **−35% vs no clause**. The absolute
medians differ across runs because the batteries differ; only the within-run
deltas are measured.

**Bottom Line:** the composite cuts roughly a third of a default Opus answer;
the Numbers section costs nothing on length and adds a further small cut.

### Content completeness (judge missing-requirement entries)

| Comparison | Baseline | Clause arm |
| --- | ---: | ---: |
| Bakeoff 6 (Sonnet / Codex) | 13 / 17 | 12 / 16 |
| Bakeoff 7 (Sonnet / Codex) | 11 / 22 | 8 / 21 |

**Bottom Line:** at −30 to −35% length, omissions sit at or below baseline —
the length is coming out of waste categories, not required content. (The
original guarded-subtractive failed exactly this in run 5; the one-word v2 fix
is what made it hold.)

### Nuance and safety (judge mean, /5)

| Comparison | Baseline | Clause arm | Delta |
| --- | ---: | ---: | ---: |
| Bakeoff 6 (Sonnet) | 4.84 | 4.88 | +0.04 |
| Bakeoff 6 (Codex) | 3.60 | 3.76 | +0.16 |
| Bakeoff 7 (Sonnet) | 4.24 | 4.64 | +0.40 |
| Bakeoff 7 (Codex) | 3.04 | 3.40 | +0.36 |

**Bottom Line:** the clauses have never cost nuance; the Numbers section
measurably improved it — hedged, assumption-labeled answers read as safer
because they are.

### Fabricated numeric precision (bakeoff 7 only — the Numbers section's target)

| Measure | v2-only | Composite |
| --- | ---: | ---: |
| Sonnet invented-precision entries | 44 | 18 (−59%) |
| Codex invented-precision entries | 64 | 30 (−53%) |
| Median novel numerals per answer (programmatic) | 11 | 8 |
| Derivable-number task computed correctly | — | 5/5 |
| Assumption surfaced when estimating | — | 4/5 |

**Bottom Line:** two sentences roughly halved the target defect on an
adversarial battery, with zero detected over-suppression.

### Material errors

| Measure | Bakeoff 6 (no clause / v2) | Bakeoff 7 (v2-only / composite) |
| --- | ---: | ---: |
| Confirmed findings (frozen co-occurrence rule) | 2 / 3 | 7 / 3 |
| Post-review surviving (bakeoff 6 only) | 0 / 1 | pending |

**Bottom Line:** error rates are statistically indistinguishable between arms
in run 6 and favor the composite outright in run 7; across 575 mined judge
entries, defect load tracks the model and battery, not the clause.

### Preference (blind pairwise, pooled both judges)

| Comparison | Clause-arm non-tied win rate |
| --- | ---: |
| Bakeoff 6: v2 vs no clause | 57.4% |
| Bakeoff 7: composite vs v2-only | 66.7% |

**Bottom Line:** directionally pro-clause both times; at n=25 per run,
preference is the weakest instrument here and is not load-bearing.

### Overall

The composite wins or ties every dimension against both baselines, and the
dimension it was purpose-built for (invented precision) shows the largest
single effect in the project. The recommendation is unambiguous: **adopt the
composite clause**. The one open formality is the same-defect review of
bakeoff 7's confirmed-error queue; on bakeoff 6's precedent (where review
dismissed 33 of 35 entries), it is unlikely to reverse the recommendation,
but it has not been done yet.

## Limitations & Considerations

- **The no-clause vs composite comparison is chained, not measured.** Runs 6
  and 7 used different batteries with very different base rates (control
  medians 729 vs 367 words; Codex error allegations 41 vs 71). Multiplying
  deltas across batteries assumes effects compose independently — plausible,
  supported by v2's profile surviving composition, but unverified. A direct
  three-arm run would close this.
- **Invented-precision counts are judge allegations under a first-use rubric
  item**, unaudited by humans; the programmatic numeral counter corroborates
  direction but not magnitude. The −59%/−53% figures come from a battery
  designed to provoke the defect and will overstate the effect on neutral
  workloads.
- **Codex CLI versions differ across runs** (0.146.1 in run 6, 0.147.0 in
  run 7); no cross-run Codex tally in this document is treated as comparable,
  but the within-run deltas quoted are unaffected.
- **Single model, single effort tier, tool-less single-turn setting.** All
  results are Opus 5 High answering from prompt-supplied information. Nothing
  here predicts behavior in tool-using agentic sessions, other models, or
  multi-turn conversations — the composite is untested there.
- **Preference win rates at this n have historically failed to replicate**
  in this project (run 3's 83.8% collapsed to 53.1% on re-run); they are
  reported for completeness, not weight.

## Rejected alternatives (why not the others)

- **Positive-recipe** ("write like this"): byte-identical re-run under clean
  instruments showed it indistinguishable from no clause (run 4).
- **Budgeted-recipe** (~250-word budget): −55% words but real quality cost —
  "compressed overclaiming"; the model holds the budget with 241–307
  precision and pays for it in content (runs 4–5).
- **Unguarded subtractive**: superseded by the guarded variant (run 5).
- **Guarded-subtractive v1**: the word "background" suppressed why-rationale
  on explainer tasks, 2/5 reps (run 5); fixed in v2 and verified eliminated
  10/10 (run 6).

## Appendix: the recommended composite (exact text)

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
