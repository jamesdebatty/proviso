# Clause bakeoff 8 protocol (vocabulary clause + blank-slate anchor)

Date: 2026-08-11
Status: frozen before live calls

## Questions

1. **Vocabulary:** does an added `## Vocabulary` section stop Opus 5 from
   emitting self-coined terms as if they were shared vocabulary, without
   suppressing the reader's own established terms of art?
2. **Blank-slate anchor:** what does the recommended composite clause actually
   buy relative to no `CLAUDE.md` at all, measured directly in one battery
   rather than chained across bakeoffs 6 and 7?

## Design rationale

The vocabulary defect was observed in live use, not mined from judges: Opus
coins a term as a working-memory handle during long reasoning ("the
shadow-write path") and then emits it to the reader as if it were agreed
vocabulary — compression against a private codebook. The clause licenses the
private reasoning and constrains only the output, which follows the
conditioned pattern Anthropic's own deployed prompts use and avoids the
blanket-conservatism failure mode their Opus 5 prompting guidance warns about.

Bakeoffs 6–7 never measured no-clause against the composite in a single
battery; the `-35%` figure in
`reports/2026-08-11-baseline-vs-composite.md` is chained inference across two
batteries with different base rates. Adding `control` as a third arm converts
that inference into a measurement at the cost of 25 extra responses.

## Arms

1. `control`: no project `CLAUDE.md` (blank slate). **Baseline for all
   primary gates.**
2. `composite`: `variants/composite.md` — bakeoff 7's recommended clause
   (guarded-subtractive-v2 + Numbers), sha256 `f70f86a9…`.
3. `composite-plus-vocabulary`: `variants/composite-plus-vocabulary.md` —
   byte-identical to `composite` plus the `## Vocabulary` section, sha256
   `70e1ec9d…`.

The only changed artifact per arm is `CLAUDE.md`. All arms use isolated,
single-turn Claude Opus 5 High sessions with no tools and no session
persistence. Every prompt ends with the frozen no-tools line.

## Hypotheses (pre-registered)

- **H1 (the vocabulary clause works):** `undefined_coinage` entries for
  `composite-plus-vocabulary` strictly below `composite` for both judges.
- **H2 (no over-suppression):** on `terms-of-art-explainer`, the rubric item
  "use the standard names for these concepts rather than avoiding them" is not
  listed missing by Sonnet in more than 1 of 5 repetitions. This is the
  falsifier for the clause reading "avoid jargon" instead of "translate your
  own shorthand."
- **H3 (composition holds):** `composite-plus-vocabulary` stays within 110% of
  `composite` on median words, at or below it on omissions, and within −0.25
  on nuance, per judge.
- **H4 (blank-slate anchor):** `composite` reduces median words versus
  `control` by 20–40%, with omissions not above control and nuance within
  −0.25 — a direct re-measurement of the bakeoff-6/7 chained claim.

**Pre-registered power check.** If `control` averages under 1
`undefined_coinage` entry per answer for both judges, the battery failed to
provoke the defect; H1 is then reported as **underpowered**, not as evidence
of no effect. The analyzer computes and reports this automatically.

## Battery

Five fresh tasks (no prompt reused from bakeoffs 2–7), selected to force
extended reasoning about systems with no standard name — entitlement-drift
mechanism design, retry-storm component interaction, scheduler-ownership
tradeoff, tail-latency debugging narrative — plus one deliberate
over-suppression falsifier (`terms-of-art-explainer`) where established
vocabulary *is* the correct answer. 5 repetitions × 3 arms = 75 Opus
responses; 25 sets × 2 judges = 50 judge calls. Live call ceiling: 125.

## Instruments

- **Judge item (primary):** `undefined_coinage` — one entry per term used as
  established vocabulary that is neither in the task nor defined at first use;
  standard terms of art explicitly excluded in the judge prompt.
- **Programmatic (corroborating):** `novel_coinages` counts distinct
  coined-looking terms (quoted multi-word phrases, hyphenated compounds,
  title-case phrases) that are absent from the prompt and reused at least
  twice in the answer. Deliberately over-inclusive and applied identically to
  every arm; it measures relative coinage load and does not stand alone.
- Preflight v2, dual blind judging (Sonnet 5 High + Codex `gpt-5.6-sol` High),
  cross-judge material-error rule, and label rotation are unchanged from
  bakeoffs 6–7.

## Gates

Primary gates for each clause arm are computed against `control`: no confirmed
material errors, no unresolved disputes, omissions ≤ control per judge,
invented precision ≤ control per judge, undefined coinage ≤ control per judge,
nuance ≥ −0.25 per judge, median words ≤ 110% of control, stalls ≤ control.

A secondary comparison block reports `composite-plus-vocabulary` against
`composite` directly (coinage strictly below, nuance within margin, omissions
not above, words within 110%), because that is the pair H1–H3 are about.

**Known instrument defect, carried forward:** the zero-form error gates
(`no_confirmed_material_errors`, `no_unresolved_disputed_errors`) have failed
for every arm in every campaign including no-clause controls, and the
confirmed rule counts response-level co-occurrence rather than same-defect
agreement. They are retained unchanged for comparability; findings again route
to human review rather than being read as clause harm.

## Environment (recorded at freeze)

- Claude Code CLI and Codex CLI pinned as **binary copies** under
  `~/.claude-eval-pins/bakeoff8/` (the auto-updater garbage-collected a
  symlinked pin during bakeoff 6). Versions recorded in the results manifest.
- Generator: Claude Opus 5, effort high, no tools, single turn.
- Judges: Sonnet 5 High and Codex `gpt-5.6-sol` High, isolated, blind, with
  artifact-based model verification.
