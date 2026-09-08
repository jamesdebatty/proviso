# Clause bakeoff 4 protocol

Date: 2026-08-05
Status: frozen before live calls

## Question

Can an explicit length constraint coexist with the positive completeness
clause? Bakeoff 3 showed `positive-recipe` wins decisively on preference and
nuance/safety but doubles median length. Two constraint mechanisms are tested:
a soft word budget and a structural cap.

## Arms

1. `control`: no project `CLAUDE.md`.
2. `positive-recipe`: byte-identical to bakeoff 3's candidate (sha256
   `55559442…`), the bridge comparator.
3. `budgeted-recipe`: the positive clause plus an explicit ~250-word budget
   with a frozen precedence rule — correctness before brevity, and when the
   budget forces a choice, decision-changing items survive and explanation is
   cut first.
4. `structured-recipe`: answer in at most three sentences, then at most six
   short bullets, each of which must change what the reader does; safety,
   validation, and rollback content claims bullets before anything else.

The only changed artifact per arm is `CLAUDE.md`. All arms use isolated,
single-turn Claude Opus 5 High sessions with no tools and no session
persistence.

## Changes from bakeoff 3

1. **Every task prompt now ends with "Answer from the information in this
   message; do not inspect files or use tools."** Bakeoff 3 replay showed 24 of
   75 responses (32%) contained fake tool-call transcripts; only 6 were caught
   by the v1 preflight. This instruction targets the failure at the source and
   applies identically to every arm.
2. **Preflight v2.** In addition to the v1 rules (under 40 words, or a final
   paragraph announcing inspection), a response is `stalled` if it contains
   fake tool-transcript signatures: `<invoke name=`, `<parameter name=`, a
   line starting `**Tool: `, a `total N` listing header line, or `drwx`
   permission strings. All five signatures were extracted from real bakeoff-3
   contamination and spot-verified as true positives.

## Hypotheses

- H1: both constrained variants keep median words at or below control.
- H2: at least one constrained variant retains a pooled non-tied win rate
  against control of 0.65 or higher (positive-recipe scored 0.838 in
  bakeoff 3 on different tasks).
- H3: the constraint mechanisms fail differently: the word budget degrades by
  cutting required content (omissions rise), the structural cap by cramming
  (long bullets), rather than both failing the same way.
- H4: with the no-tools instruction in prompts, stall rates fall to near zero
  in all arms, and control's scores rise relative to bakeoff 3.

## Battery

Five fresh tasks (none reused from bakeoffs 2 or 3): duplicate-invoice triage,
staged validation enforcement, error-rate diagnosis under uncertainty, a
connection-pool explainer, and an ambiguous observability request. Each task
runs five times per arm: 100 Opus responses. Each non-skipped set is graded by
both judges: up to 50 judge calls. Total live call ceiling: 150.

## Judges, material-error rule, and selection

Identical to bakeoff 3 (frozen there, unchanged here): Sonnet 5 High and Codex
`gpt-5.6-sol` High as independent blind graders with per-call isolation and
model-identity verification from artifacts; material errors confirmed only when
both judges allege them, single-judge allegations queued for human review;
eligibility requires no confirmed errors, no unresolved disputes,
per-judge omissions and nuance within bounds versus control, median words at or
below control, and stalls at or below control. Rank eligible candidates by
pooled non-tied win rate, then focus, then jargon discipline, then lower median
words.

This is a development battery. A winning clause still requires a later, newly
frozen holdout campaign with human review before deployment.
