# Clause Bakeoff 4: Length-Constrained Recipes on Clean Instruments

**Repository:** a private research monorepo
**Project:** [Opus 5 STE verbosity evaluation](../README.md)
**Frozen protocol:** [Bakeoff 4 protocol](../campaigns/clause-bakeoff-4-2026-08-05/protocol.md)
**Evaluation code:** [Promptfoo configuration](../campaigns/clause-bakeoff-4-2026-08-05/promptfooconfig.yaml), [Opus provider](../campaigns/clause-bakeoff-4-2026-08-05/provider.py), [dual-judge analyzer](../campaigns/clause-bakeoff-4-2026-08-05/analyze.py)
**Benchmarking data:** [Tasks and required ideas](../campaigns/clause-bakeoff-4-2026-08-05/tasks.jsonl)
**Candidate clauses:** [positive-recipe](../campaigns/clause-bakeoff-4-2026-08-05/variants/positive-recipe.md) (byte-identical to bakeoff 3, sha256 `55559442…`), [budgeted-recipe](../campaigns/clause-bakeoff-4-2026-08-05/variants/budgeted-recipe.md), [structured-recipe](../campaigns/clause-bakeoff-4-2026-08-05/variants/structured-recipe.md)
**Results:** [Machine-readable summary](../campaigns/clause-bakeoff-4-2026-08-05/out/bakeoff-20260805T163846Z/bakeoff-results.json), [raw run artifacts](../campaigns/clause-bakeoff-4-2026-08-05/out/bakeoff-20260805T163846Z/)
**Prior evaluation:** [Clause bakeoff 3](2026-08-05-clause-bakeoff-3.md) — this report's instrument fixes retroactively invalidate its comparative magnitudes
**Presentation:** None

**Document version:** 1.0.0
**Owner:** Agent Systems Research maintainers
**Evaluation date:** 2026-08-05
**Deployment status:** N/A — no clause was approved for deployment

## Executive Summary

### Context

Bakeoff 3 found that the positive completeness clause (`positive-recipe`) beat control
decisively on quality but doubled response length, and its post-run audit found 32% of
responses were fake-tool-transcript non-answers that its preflight missed — concentrated
in the control arm. This run had two goals: test whether an explicit length constraint
(a ~250-word soft budget, or a three-sentences-plus-six-bullets structural cap) can
coexist with the completeness clause, and re-measure everything on fixed instruments —
every task prompt now forbids project inspection, and the preflight detects
tool-transcript signatures.

### Findings

- **No candidate passed the frozen gates. Do not deploy any tested clause.**
- **The instrument fixes worked completely and rewrote bakeoff 3's story.** Zero stalled
  responses in 100. The clean control is strong: 579-word median, 4.88/5 Sonnet
  nuance, zero Sonnet-alleged errors. Against it, `positive-recipe`'s advantage collapsed
  from an 83.8% pooled win rate and +2.0 nuance delta to 53.1% and +0.04 — byte-identical
  clause, fresh tasks. **The positive clause is indistinguishable from no clause at all
  on a clean baseline.** Bakeoff 3's headline result was an instrument artifact.
- **Both length mechanisms delivered length and priced its cost.** The word budget held
  261 median words (−55%) with striking discipline; the structural cap held 269 (−54%).
  The bill, consistent across both judges and both candidates: nuance/safety drops
  0.3–0.6 points and judge-counted omissions roughly double versus control. Both fail the
  nuance and omissions gates.
- Four campaigns and ten-plus clause variants have now produced the same result from
  every direction: **length and completeness trade directly in Opus 5 responses, and no
  instruction wording has found a free lunch.**
- `structured-recipe` also produced the run's only cross-family-confirmed material error
  and lost to control outright on preference (46%). The word budget dominates the
  structural cap.

### Next Steps

1. Close the clause-search line of work unless the brief changes. The remaining
   defensible adoption is `budgeted-recipe` *as an explicitly priced trade* — half the
   length for a measurable quality cost — not as "concision without sacrificing quality,"
   which four runs failed to find.
2. If any future run happens, calibrate the judges first: Codex alleged 23 material
   errors against the strong control (Sonnet: 0), so its solo allegations gate nothing
   and human agreement rates are unmeasured.

## Project Overview

### Evaluation question

Can an explicit length constraint coexist with the positive completeness clause — and
with clean instruments, how much of bakeoff 3's quality signal survives?

### Arms

| Arm | Clause strategy | Reason for inclusion |
| --- | --- | --- |
| `control` | No project `CLAUDE.md` | Baseline, now uncontaminated |
| `positive-recipe` | Bakeoff 3's candidate, byte-identical | Bridge comparator; re-measures the prior result |
| `budgeted-recipe` | Positive clause + ~250-word soft budget with a frozen precedence rule (decision-changing items survive; explanation is cut first) | Tests a numeric constraint |
| `structured-recipe` | ≤3-sentence answer + ≤6 bullets, each required to change what the reader does; safety/validation/rollback claim bullets first | Tests a structural constraint |

### Hypotheses

1. Both constrained variants keep median words at or below control.
2. At least one constrained variant retains a pooled non-tied win rate ≥ 0.65 against
   control.
3. The constraint mechanisms fail differently: the budget by cutting required content,
   the cap by cramming.
4. (Instrument) With the no-tools prompt line, stall rates fall to near zero in all arms
   and control's scores rise relative to bakeoff 3.

## Data Collection

### Generation

Promptfoo 0.121.12, 100 isolated responses: 5 fresh tasks × 5 repetitions × 4 arms.
Tasks (none reused from bakeoffs 2 or 3): duplicate-invoice triage, staged
validation-rule enforcement, error-rate diagnosis under uncertainty, a connection-pool
explainer, and an ambiguous observability request — the last two extend coverage to
low-stakes work. **Every prompt ends with "Answer from the information in this message;
do not inspect files or use tools."** Claude Code 2.1.222, `opus` alias, High effort,
full provenance hashing, every response verified as `claude-opus-5`. Zero generation
errors.

### Preflight v2

The bakeoff-3 rules (under 40 words; final-paragraph inspection intent) plus
tool-transcript signatures extracted from real bakeoff-3 contamination: `<invoke name=`,
`<parameter name=`, lines starting `**Tool:`, `total N` listing headers, and `drwx`
permission strings. Replayed against bakeoff 3's 75 responses it flags 24 (spot-verified
as true positives); against this run's 100 responses it flags **zero** — the prompt-level
fix removed the failure at the source.

### Dual blind judging

Identical machinery to bakeoff 3: Sonnet 5 High and Codex `gpt-5.6-sol` High as
independent blind graders of the same rendered four-answer prompt, per-call isolation
(empty working directory; temporary `CODEX_HOME` seeded only with `auth.json`),
model identity verified from stream and rollout artifacts, confirmed/disputed
material-error rule. All 25 sets were judged by both judges: 50 judgments, all under
codex-cli 0.146.1 (see Deviations for the version-drift event).

## Analysis and Findings

### Hypothesis 1: both constrained variants hold length at or below control

Median words: control 579, `budgeted-recipe` 261 (−54.9%), `structured-recipe` 269
(−53.5%). The budget clause's spread was remarkably tight (267–288 on the first task).
`positive-recipe` landed at 575 (−0.7%) — at control's length, not double it as in
bakeoff 3, because control is no longer artificially short.

1: both constrained variants ≤ control → **TRUE**

### Hypothesis 2: a constrained variant keeps a ≥0.65 pooled win rate

Pooled non-tied win rates against control: `budgeted-recipe` 0.571, `positive-recipe`
0.531, `structured-recipe` 0.460.

2: any constrained variant ≥ 0.65 → **FALSE**

The more consequential number is the bridge arm's. `positive-recipe` at 0.531 with
nuance deltas of +0.04 (Sonnet) and −0.32 (Codex), on a byte-identical clause, means
bakeoff 3's 0.838 measured the contaminated control, not the clause.

**Bottom Line:** on a clean baseline, the positive completeness clause adds nothing —
same length, same quality, same errors as no clause.

### Hypothesis 3: the two constraint mechanisms fail differently

Both failed the same way: omissions roughly doubled versus control (Sonnet 16 and 18
entries vs 6; Codex 15 and 19 vs 13) and nuance dropped past the −0.25 gate for both
judges (−0.64/−0.36 budgeted, −0.56/−0.32 structured). No cramming signature appeared;
the structural cap additionally picked up the run's only confirmed material error
(`error-rate-diagnosis` r3: asserting that the two error classes "most likely share one
cause" as if established — both judges flagged it independently) and lost to control on
preference outright.

3: mechanisms fail differently → **FALSE** — both fail through dropped content, and the
budget strictly dominates the cap (better preference, no confirmed error, equal length).

### Hypothesis 4: the instrument fixes normalize the baseline

Stalls: 0/100 (bakeoff 3: 24/75 contaminated). Control's Sonnet nuance rose from 2.53 to
4.88, task completion from 3.0 to 4.8, Sonnet-alleged errors from 8 entries to 0.

4: stalls near zero and control rises → **TRUE**

**Bottom Line:** run 3 vs run 4 is a controlled demonstration that the "weak control"
in this project's earlier campaigns was an artifact of agent-mode non-answers, not a
property of un-prompted Opus 5.

## Results

### Quality, length, and gates

| Arm | Pooled win rate | Nuance Δ (Sonnet / Codex) | Focus (Sonnet) | Missing reqs (S / C) | Median words | Confirmed errors | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| Control | — | — | 3.52 | 6 / 13 | 579 | 0 | Baseline |
| Positive recipe | 0.531 | +0.04 / −0.32 | 3.80 | 9 / 9 | 575 (−1%) | 0 | **No** |
| Budgeted recipe | 0.571 | −0.64 / −0.36 | **4.72** | 16 / 15 | **261 (−55%)** | 0 | **No** |
| Structured recipe | 0.460 | −0.56 / −0.32 | 4.68 | 18 / 19 | 269 (−54%) | 1 | **No** |

Gate failures: `positive-recipe` — omissions (Sonnet) and nuance (Codex, −0.32 vs the
−0.25 margin); `budgeted-recipe` — omissions and nuance, both judges; `structured-recipe`
— those plus the confirmed error. Formal status is `needs_human_review` (64 disputed
allegations), but every candidate's binding gate failures are independent of the
disputed queue, so the effective result is `no_eligible_candidate` and is final.

**Bottom Line:** the constrained clauses bought exactly what they promised (−55% length,
sharply better focus) and paid for it in dropped required content — visible to both
judges, on fresh tasks, with a clean control.

### Judge agreement and error findings

Pairwise agreement: 64.0% (96/150) — essentially identical to bakeoff 3's 64.9%.
Error findings: 1 confirmed (both judges), 62 Codex-only disputed, 2 Sonnet-only
disputed. Codex alleged 23 error entries against control alone; Sonnet alleged 0.

_NOTE: Codex-only disputed counts are not evidence of arm quality. Codex's material-error
threshold is far lower than Sonnet's, and manual reading shows a mix of genuinely good
catches of overclaiming (e.g. "a two-week audit window covers a monthly billing cycle" —
arithmetically false) and defensible judgment calls. Un-calibrated, they gate nothing._

### Cost

| Phase | Calls | Recorded cost |
| --- | ---: | --- |
| Opus 5 High generation | 100 | $6.22 |
| Sonnet 5 High judging | 25 + 1 discarded (version drift) | $4.50 |
| Codex judging | 25 + 1 discarded (version drift) | ~594k tokens, subscription billing |

Frozen ceiling 150; approximately 152 issued including the two discarded
version-drift judgments (plus any partial billing from calls interrupted by host-session
restarts, which is not measurable from artifacts).

## Limitations and Considerations

### The strongest finding is a null, and nulls are hard to distinguish from insensitivity

`positive-recipe` ≈ control could mean the clause does nothing, or that these five tasks
sit where un-prompted Opus 5 already answers near ceiling (control's Sonnet nuance was
4.88/5, leaving almost no headroom to measure a positive effect). The bakeoff-2 and
bakeoff-3 task families showed more baseline spread. The safe claim is: no positive
effect was detectable here, and the burden of proof has shifted onto any claim that
response-style clauses improve quality.

### The nuance and omission gates rest on judge counts, not human ground truth

Both length-constrained candidates failed on judge-perceived nuance loss and
judge-counted omissions. If a human reader would call some of those omissions
appropriately cut explanation rather than lost substance, the true cost of the budget
clause is smaller than measured. No human calibration was performed; this is the
project's largest unmeasured quantity (raised in bakeoff 2, still open).

### Judges share task-format exposure, comparisons are correlated, samples are small

One four-answer judgment yields all six pairwise outcomes for a set; n=5 per task-arm;
64% cross-family agreement bounds but does not eliminate shared blind spots. All results
are bound to Claude Code 2.1.222, codex-cli 0.146.1, the aliases resolved 2026-08-05,
and these exact clauses, tasks, and prompts.

### The no-tools prompt line is now part of the measured system

Every task prompt carries the "answer from the information in this message" instruction.
Results generalize to prompts of that form; behavior on prompts without it (where
bakeoff 3 showed a 32% fake-transcript rate in agent-style contexts) is a separate,
unmeasured regime.

## Recommendation

Adopt no clause under the project's standing brief ("reduce verbosity without
sacrificing quality"). Four campaigns, ten-plus variants, and two judge families have
consistently shown that brief to be unsatisfiable by instruction wording: every
mechanism that cuts length drops content that at least one independent judge counts as
required, and the one clause that preserves quality no longer shortens anything once the
baseline is measured cleanly.

Two defensible paths remain, and they are decisions rather than experiments:

- **If quality is the goal:** run without a response-style clause and invest in
  grounding and context instead — the original study's P6 finding, now reinforced by the
  null result on `positive-recipe`.
- **If halving length is worth a real cost:** `budgeted-recipe` is the best-priced trade
  found (−55% words, +1.2 focus, −0.4 to −0.6 nuance, ~2× judge-counted omissions,
  zero confirmed errors). Adopt it with that price tag stated, not as a free win.

**Why the runner-up lost:** `structured-recipe` matched the budget's length but lost to
control on preference, doubled omissions with the worst counts in the run, and produced
the only cross-family-confirmed material error. Rigid structure appears to force content
decisions that a word budget lets the model make better.

**What would change this answer:** human calibration showing Codex/Sonnet omission
counts overstate real content loss (would soften both candidates' gate failures); a task
family with measurable baseline headroom showing a positive-recipe effect (would revive
the quality claim); or a revised brief that accepts an explicit quality-for-length trade
(makes `budgeted-recipe` adoptable as-is).

## Future Research

1. **Judge calibration:** sample the 64 disputed allegations, adjudicate by hand, and
   estimate each judge's material-error precision. This is the highest-leverage open
   item; it conditions every gate in this design.
2. **Headroom-sensitive task battery:** re-test `positive-recipe` on tasks where control
   demonstrably underperforms, to separate "no effect" from "no measurable headroom."
3. **Main-loop transfer:** all four campaigns used single-turn isolated sessions; whether
   any of this holds in long multi-turn agent sessions remains untested (open since
   bakeoff 1).
4. **The 250-word dial:** the budget clause held its target almost exactly; a small sweep
   (200/300/400) would map the length-quality curve rather than sampling one point.

## Versioning

| Version | Date | Change | Status |
| --- | --- | --- | --- |
| 1.0.0 | 2026-08-05 | Initial write-up | No eligible candidate; bakeoff-3 magnitudes retroactively corrected |

## Appendix

### Deviations from the frozen protocol

1. **Codex CLI drifted mid-campaign (0.146.0 → 0.146.1, auto-update).** The provenance
   layer refused to mix cached judgments across versions, as designed. The two judgments
   made under 0.146.0 were archived (`judgments-archived-codex-0.146.0/`, preserved, not
   deleted) and re-run; all 50 final judgments are version-uniform under 0.146.1.
2. **Three host-session restarts** interrupted generation (at 43/100 — note: this
   restart count includes one during bakeoff 3) and judging (at 19/50 and 40/50 for this
   run). Hash-validated caching resumed each with no lost or double-counted data.
3. Call ceiling exceeded by ~2 (152 vs 150) due to the version-drift discards.

### Data manipulation decisions

- No response or completed judgment was discarded or edited except the two
  version-drift judgments, which are archived intact with their raw streams.
- Word medians use all responses (no stalls occurred, so answered-only and all-response
  medians coincide).
- Ties were excluded from non-tied win-rate denominators, as frozen in the analyzer.

### Note on statistical significance

No significance testing was performed. n=5 per task-arm, 25 judged sets, correlated
pairwise outcomes. The win-rate gaps between candidates (0.571 / 0.531 / 0.460) are
within plausible sampling noise of each other; the findings this report leans on are the
large, cross-judge-consistent effects (−55% length, doubled omissions, the collapse of
the +2.0 nuance delta to +0.04) and the categorical gate outcomes (a confirmed error
exists or it does not).

### Cross-run comparison (context, not measurement)

Task families differ across runs, so these are trajectories, not controlled comparisons:

| | Bakeoff 2 | Bakeoff 3 | Bakeoff 4 |
| --- | --- | --- | --- |
| Control median words | 303 | 276 (contaminated) | 579 (clean) |
| Best candidate win rate | 76.9% | 83.8% (inflated) | 57.1% |
| Confirmed/verified error rule | single judge | dual, 5 confirmed | dual, 1 confirmed |
| Stall / non-answer rate | present, unmeasured | 32% (post-hoc) | 0% |
