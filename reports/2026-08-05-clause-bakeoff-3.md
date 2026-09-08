# Clause Bakeoff 3: Positive Recipe vs Control vs Complete Recipe, Dual-Judge

**Repository:** a private research monorepo
**Project:** [Opus 5 STE verbosity evaluation](../README.md)
**Frozen protocol:** [Bakeoff 3 protocol](../campaigns/clause-bakeoff-3-2026-08-05/protocol.md)
**Evaluation code:** [Promptfoo configuration](../campaigns/clause-bakeoff-3-2026-08-05/promptfooconfig.yaml), [Opus provider](../campaigns/clause-bakeoff-3-2026-08-05/provider.py), [dual-judge analyzer](../campaigns/clause-bakeoff-3-2026-08-05/analyze.py)
**Benchmarking data:** [Tasks and required ideas](../campaigns/clause-bakeoff-3-2026-08-05/tasks.jsonl)
**Candidate clauses:** [positive-recipe](../campaigns/clause-bakeoff-3-2026-08-05/variants/positive-recipe.md), [complete-recipe](../campaigns/clause-bakeoff-3-2026-08-05/variants/complete-recipe.md) (byte-identical to bakeoff 2, sha256 `ee8e6b55…`)
**Results:** [Machine-readable summary](../campaigns/clause-bakeoff-3-2026-08-05/out/bakeoff-20260805T071002Z/bakeoff-results.json), [raw run artifacts](../campaigns/clause-bakeoff-3-2026-08-05/out/bakeoff-20260805T071002Z/)
**Codex judge wiring notes:** [Probe findings](../notes/codex-judge-wiring-2026-08-05.md)
**Prior evaluation:** [Clause bakeoff 2](2026-08-05-clause-bakeoff.md)
**Follow-up evaluation:** [Clause bakeoff 4](2026-08-05-clause-bakeoff-4.md) — partially supersedes this report; read its contamination finding before trusting any comparative number below
**Presentation:** None

**Document version:** 1.0.0
**Owner:** Agent Systems Research maintainers
**Evaluation date:** 2026-08-05
**Deployment status:** N/A — no clause was approved for deployment

## Executive Summary

### Context

Bakeoff 2 rejected all three of its candidates but identified `complete-recipe` — a
positive "state what a correct answer must contain" clause — as the strongest direction,
recommending a shortened four-sentence version as the next candidate. This bakeoff tested
that shortened clause (`positive-recipe`) against a no-clause control and the original
`complete-recipe`, and introduced two methodology upgrades: a deterministic preflight gate
against agent-stall non-answers, and a second blind judge from a different model family
(OpenAI Codex, `gpt-5.6-sol`) alongside Sonnet 5, with material errors counted only when
both judges allege them.

### Findings

- **No candidate passed the frozen gates. Do not deploy any tested clause.**
- `positive-recipe` won 83.8% of pooled non-tied comparisons against control and raised
  nuance/safety by +2.0 (Sonnet) — but nearly doubled median length (+98% vs control) and
  carried one cross-family-confirmed material error. The length gate and the error gate
  both bind, so the human-review queue cannot change the outcome.
- `complete-recipe` was strictly worse: +121% length, two confirmed errors, more stalls.
- Shortening `complete-recipe` did not touch its length pathology. The growth comes from
  the completeness instruction itself, not from the words the shortening removed.
- **A post-hoc replay found 24 of 75 responses (32%) contained fake tool-call
  transcripts; only 6 were caught by this run's preflight.** Control was worst affected.
  See the Limitations section — this contaminates every comparative number in this report
  and motivated bakeoff 4, which re-measured on clean instruments and reversed the
  headline preference finding.
- The dual-judge instrument worked: 5 material errors were confirmed by both judges
  independently, 35 allegations came from a single judge, and pairwise agreement was
  64.9%. A single-judge design would have produced materially different error counts
  depending on the judge chosen.

### Next Steps

1. Read [bakeoff 4](2026-08-05-clause-bakeoff-4.md), which fixed both instrument defects
   and re-tested `positive-recipe` with two length-constrained variants.
2. Treat this run's judged metrics as upper bounds on candidate advantage: the weak,
   contaminated control inflated every candidate's win rate and nuance delta.

## Project Overview

### Evaluation question

Does the shortened positive clause keep `complete-recipe`'s preference and nuance/safety
advantages over control while producing zero confirmed material errors, no more omissions
than control, and a median length no longer than control?

### Arms

| Arm | Clause | Reason for inclusion |
| --- | --- | --- |
| `control` | No project `CLAUDE.md` | Baseline |
| `positive-recipe` | Four-sentence positive clause from the bakeoff-2 recommendation, verbatim | The candidate under test |
| `complete-recipe` | Byte-identical to bakeoff 2's clause | Bridge comparator the candidate was derived from |

### Hypotheses

1. `positive-recipe` beats control in pairwise preference at least as often as
   `complete-recipe` does.
2. `positive-recipe` keeps median words at or below control, repairing
   `complete-recipe`'s +66% length failure from bakeoff 2.
3. `positive-recipe` produces no confirmed material errors and no more missing
   requirements than control.
4. (Instrument) The two judges agree on a majority of pairwise outcomes, and single-judge
   error allegations are common enough to justify the dual-judge design.

## Data Collection

### Generation

Promptfoo 0.121.12 ran 75 isolated responses: 5 fresh tasks × 5 repetitions × 3 arms,
none of the prompts reused from earlier campaigns. Each response used Claude Code 2.1.222,
`opus` alias, High effort, no tools, no session persistence, in an isolated temporary
project containing only the arm's `CLAUDE.md`. Every response was provenance-hashed
(task, repetition, prompt hash, clause hash, CLI version, raw and parsed stream hashes)
and verified as `claude-opus-5`.

### Preflight gate (new in this run)

Before judging, each response was classified deterministically: `stalled` if under 40
words or if its final paragraph announced an intent to inspect the project. Stalled
responses were not judged; a set containing any stalled arm was skipped entirely.
Six of 25 sets were skipped (control 2, positive-recipe 1, complete-recipe 3).

_WARNING: this v1 preflight was insufficient. See Limitations — 18 additional
contaminated responses passed it and were judged._

### Dual blind judging (new in this run)

Each surviving set was graded by two independent blind judges from the identical rendered
prompt with identical label rotation:

- **Sonnet:** Claude Code `--model sonnet --effort high`, no tools, verified as
  `claude-sonnet-5` from the response stream.
- **Codex:** Codex CLI `exec` (codex-cli 0.146.0), model pinned to `gpt-5.6-sol`, high
  reasoning effort, read-only sandbox, empty working directory, per-call temporary
  `CODEX_HOME` seeded only with `auth.json`. The resolved model was verified from the
  persisted session rollout's `turn_context` record, preserved as a raw artifact.

A user-supplied interactive Codex session was deliberately **not** resumed for judging:
a resumed session carries prior context into every judgment, breaking blinding and
reproducibility. Wiring details and probe findings are in the
[wiring notes](../notes/codex-judge-wiring-2026-08-05.md).

### Material-error rule (frozen)

An error alleged by **both** judges for the same response is `confirmed` and counts
against eligibility. An error alleged by **exactly one** judge is `disputed` and queued
for human review; selection blocks on unresolved disputes. The manual audit may contest a
confirmed finding in prose but cannot flip the frozen result.

## Analysis and Findings

### Hypothesis 1: positive-recipe beats control at least as often as complete-recipe

Pooled non-tied win rate against control: `positive-recipe` 0.838 (Sonnet 17–2,
Codex 14–4–1), `complete-recipe` 0.733.

1: `positive-recipe` ≥ `complete-recipe` on pairwise preference → **TRUE**

_WARNING: both win rates are inflated by the contaminated control (see Limitations).
Bakeoff 4 re-measured `positive-recipe` against a clean control and found 0.531._

### Hypothesis 2: positive-recipe keeps median words at or below control

Median words: control 276, `positive-recipe` 546.5 (+98.0%), `complete-recipe` 609.5
(+120.8%). Word medians were computed over answered responses only.

2: median at or below control → **FALSE**

**The shortening did not touch the length pathology.** The four-sentence clause grew
answers almost exactly as much as the full clause it was cut from. The growth is driven
by the instruction to include facts, uncertainty, safety checks, validation, and rollback
— not by the prose the shortening removed.

_NOTE: control's 276-word median is itself unreliable — it is deflated by judged
non-answers (see Limitations). Bakeoff 4's clean control median was 579 words on
comparable task types._

### Hypothesis 3: no confirmed errors, omissions not above control

`positive-recipe` had one confirmed material error (`stale-version-triage` r1): both
judges independently flagged that its `kubectl get pods -o wide` instruction claims to
compare image tags (the flag does not display container images), alongside an uncaveated
`skipWaiting()` service-worker recommendation. `complete-recipe` had two confirmed
errors; control had two.

Missing-requirement totals were below control for both candidates under both judges
(Sonnet: 10 and 24 vs control 44; Codex: 9 and 21 vs control 41).

3a: no confirmed material errors → **FALSE** (1)
3b: omissions not above control → **TRUE**

### Hypothesis 4: the dual-judge instrument discriminates

Pairwise agreement was 64.9% (37/57). Error findings split 5 confirmed / 35 disputed
(27 Codex-only, 8 Sonnet-only). Codex alleged far more errors per arm than Sonnet
(e.g. 22 vs 3 entries on `positive-recipe`).

4: majority pairwise agreement, single-judge allegations common → **TRUE**

**Bottom Line:** the confirmed-by-both rule is doing real work. The five confirmed
findings are specific, checkable factual claims; the disputed pool is dominated by
Codex's much lower threshold for calling something a material error.

## Results

### Quality, length, and gates

| Arm | Pooled win rate vs control | Nuance Δ (Sonnet / Codex) | Median words | Confirmed errors | Stalls | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| Control | — | — | 276 | 2 | 2 | Baseline |
| Positive recipe | 0.838 | +2.00 / +1.21 | 546.5 (+98%) | 1 | 1 | **No** |
| Complete recipe | 0.733 | +1.32 / +0.63 | 609.5 (+121%) | 2 | 3 | **No** |

`positive-recipe` failed the confirmed-error and median-length gates.
`complete-recipe` failed those plus the stall gate. Formal selection status:
`needs_human_review` (23 unresolved candidate disputes), but both candidates are
ineligible regardless of how every dispute is adjudicated, so the effective result is
`no_eligible_candidate`.

**Bottom Line:** the candidate won decisively on measured quality and lost on the two
constraints the run existed to test.

### Cost

| Phase | Calls | Recorded cost |
| --- | ---: | --- |
| Opus 5 High generation | 75 | $5.47 |
| Sonnet 5 High judging | 25 (1 re-run after an interrupted call) | $2.48 |
| Codex judging | 25 + 2 wasted (instrument bugs) | ~434k tokens, subscription billing |

The frozen ceiling was 125 live calls; approximately 128 were issued. The overage is the
two wasted Codex calls and one re-run Sonnet call, all from instrument failures recorded
under Deviations.

## Limitations and Considerations

### The control arm was contaminated, and this poisons every comparison

After this run completed, the bakeoff-4 preflight (which adds fake-tool-transcript
signatures such as `<invoke name=`, `**Tool:` headers, and `ls -la` permission strings)
was replayed over all 75 responses. **It flagged 24 (32%), versus the 6 this run's
preflight caught.** Every spot-checked flag was a genuine non-answer — Opus, denied
tools, emitted textual imitations of tool calls, including fabricated command output and
in one case a fabricated `<system-reminder>` block. Contamination was concentrated in
control (11 responses) and `complete-recipe` (8).

Consequences: control's judged scores are dragged down by non-answers (inflating both
candidates' win rates and nuance deltas), and control's word median is deflated (making
the length gate harsher than intended). Bakeoff 4 fixed the instrument and found
`positive-recipe`'s advantage over a clean control collapsed to statistical noise. The
gate *failures* in this run survive the contamination — the confirmed errors are real and
the candidates' absolute lengths are real — but no comparative magnitude in this report
should be quoted without that caveat.

### Codex's material-error threshold differs from Sonnet's

Codex listed roughly four times as many error entries as Sonnet. Manual reading suggests
many Codex-only allegations are legitimate catches of overclaiming rather than noise, but
no human calibration of either judge's threshold was performed. The confirmed-by-both
rule is robust to this; disputed counts are not comparable across judges.

### Small samples, correlated comparisons, same-day scope

n=5 per task per arm; 19 judged sets. One four-answer judgment produces all pairwise
outcomes for that set, so comparisons are correlated. Everything is bound to Claude Code
2.1.222, codex-cli 0.146.0, the model aliases resolved on 2026-08-05, and these exact
clauses and tasks.

## Recommendation

Do not deploy either candidate. `positive-recipe` fails the brief on length and carries a
confirmed factual error; `complete-recipe` remains rejected and is now dominated by its
own derivative on every measured dimension.

The actionable output of this run is methodological: the dual-judge confirmed/disputed
rule, the Codex judge isolation pattern, and the discovery of the tool-transcript
contamination mode. All three carried into [bakeoff 4](2026-08-05-clause-bakeoff-4.md),
which should be read as the current word on the clause question.

## Future Research

Superseded — the items identified here (fix the preflight, re-test with a length
constraint, calibrate the judges) were executed as bakeoff 4 on the same day. Remaining
open questions live in that report.

## Versioning

| Version | Date | Change | Status |
| --- | --- | --- | --- |
| 1.0.0 | 2026-08-05 | Initial write-up, including post-hoc contamination finding | No eligible candidate |

## Appendix

### Deviations from the frozen protocol

Recorded here rather than absorbed silently:

1. **Codex rollout parser bug (1 wasted Codex call).** The model-identity check looked
   for the `turn_context` type inside the payload; the real rollout carries it on the
   outer record. Fixed, unit-tested against the real artifact, judging re-run.
2. **Unbounded Codex scoring schema (1 wasted Codex call).** The first Codex schema
   omitted the 1–5 integer bounds (fear of structured-output keyword rejection), and the
   judge prompt never states the scale; Codex scored on an inferred 10-point scale and
   failed validation. A live probe confirmed the API accepts `minimum`/`maximum`; bounds
   were restored. The judge prompt was left untouched to preserve the cached Sonnet
   judgment's provenance.
3. **Two host-session restarts** interrupted generation (at 43/75) and judging (at
   12/50). Hash-validated caching resumed both with no lost or double-counted data; one
   interrupted Sonnet call re-ran.
4. **P6-style grounding was out of scope**; no arm had repository access.

### Data manipulation decisions

- Stalled responses were excluded from judging and word medians per the frozen preflight;
  six full sets were skipped because a set is only judged when all three arms answered.
- No completed judgment was discarded or edited. The two failed Codex attempts produced
  no cached judgment (validation raised before write) and their raw streams are preserved
  in the output directory.
- The post-hoc contamination replay is reported in Limitations and was **not** used to
  re-score this run; re-measurement was done as bakeoff 4 instead, on fresh tasks.

### Note on statistical significance

No significance testing was performed. n=5 per cell, 19 judged sets, correlated pairwise
outcomes. The 0.838-vs-0.733 win-rate gap and all nuance deltas should be read as
descriptive, and additionally as upper bounds given the contaminated control.
