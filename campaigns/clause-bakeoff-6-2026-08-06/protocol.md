# Clause bakeoff 6 protocol (guarded-subtractive v2 holdout)

Date: 2026-08-06
Status: frozen before live calls

## Question

Does removing the single word "background" from the guarded-subtractive do-not
list restore why-rationale on explainer tasks while preserving the clause's
run-5 profile (about 20% shorter, no confirmed errors, control-level nuance)?

## Design rationale

Bakeoff 5's `guarded-subtractive` was the strongest candidate across five
campaigns: 0 confirmed material errors (control had 1), nuance within margin
for both judges, and a 20% median-word reduction. It failed exactly one gate —
Sonnet's raw missing-requirement count (15 vs 6) — and hand adjudication
(`notes/guarded-subtractive-omission-adjudication-2026-08-05.md`) traced the
only repeatable substantive loss to one mechanism: on the explainer task, the
answer never said *why* systems accept eventual consistency (2 of 5 reps). The
diagnosed cause is the word "background" in the do-not list suppressing
pedagogical rationale that the question implicitly asks for.

The v2 clause makes exactly one change: "add caveats, alternatives,
background, or adjacent topics" becomes "add caveats, alternatives, or
adjacent topics". Dropping the word entirely (rather than scoping it, e.g.
"background the reader does not need") was chosen because it is the smallest
change that removes the diagnosed cause, and scoped wording resembles the
bakeoff-1 v2 guard pattern that misfired. No other byte of the clause changes.

This is a two-arm holdout on five never-used tasks. The battery deliberately
carries **two** explainer tasks (bakeoffs 2–5 carried at most one) because the
fix targets explainer behavior and one task gives H1 too little power. The
diagnosis-under-uncertainty category is dropped this round to make room; the
other three categories are retained.

## Arms

1. `control`: no project `CLAUDE.md`.
2. `guarded-subtractive-v2`: `variants/guarded-subtractive-v2.md` — run-5
   `guarded-subtractive` (sha256 `b1233640…`) with "background," removed from
   the do-not list. No other change.

The only changed artifact per arm is `CLAUDE.md`. All arms use isolated,
single-turn Claude Opus 5 High sessions with no tools and no session
persistence. Every prompt ends with the frozen no-tools line.

## Hypotheses (pre-registered)

- H1 (the fix works): on each explainer task, the why-rationale rubric item
  (the "explain why systems accept…" / "explain why teams accept…" line) is
  absent from Sonnet's `missing_requirements` for `guarded-subtractive-v2` in
  at least 4 of 5 repetitions per task. Run-5 baseline: 3 of 5 on the one
  explainer task.
- H2 (eligibility): `guarded-subtractive-v2` passes all six frozen gates —
  no confirmed material errors, no unresolved disputes, omissions not above
  control per judge, nuance delta ≥ −0.25 per judge, median words ≤ control,
  stalls ≤ control.
- H3 (profile preserved): median word reduction versus control remains in the
  10–35% band (run 5: −20%). A reduction under 10% means the removed word was
  load-bearing for concision; that outcome counts as a failed replication of
  the v2 design goal even if H2 passes.

## Battery

Five fresh tasks (no prompt reused from bakeoffs 2–5): message-queue
explainer, feature-flag explainer, database-disk triage, database
major-version upgrade plan, audit-logging scoping. 5 repetitions × 2 arms =
50 Opus responses; up to 25 sets × 2 judges = 50 judge calls. Total live call
ceiling: 100.

## Preflight, judges, error rule, and selection

Identical to bakeoffs 4–5: preflight v2 (minimum 40 words, final-paragraph
inspection intent, fake-tool-transcript signatures); Sonnet 5 High and Codex
`gpt-5.6-sol` High as isolated blind judges with artifact-based model
verification; material errors confirmed only on cross-judge agreement; the
same six eligibility gates. Labels A–B rotate by set index; one pairwise key.

**Frozen omission gate note.** The primary omission gate remains the frozen
raw-count rule (per-judge entries ≤ control) for comparability with bakeoffs
2–5. As a pre-registered secondary reading, every missing-requirement entry
against either arm will additionally be hand-adjudicated substantive /
borderline / stylistic under the standard declared in
`notes/guarded-subtractive-omission-adjudication-2026-08-05.md`, and a
substantive-only gate reported alongside. The secondary reading cannot flip an
H2 pass to fail; it can only annotate a fail.

## Environment (recorded at freeze)

- Claude Code CLI pinned at `2.1.222 (Claude Code)` via `/tmp/claude-pin`
  PATH shim for generation and Sonnet judging; drift checks fail closed.
  If the pin must move to 2.1.223, the change is recorded and applied
  uniformly to all cells before any comparison.
- Codex CLI `codex-cli 0.146.1`, judge model `gpt-5.6-sol`, effort high.
- Generator: Claude Opus 5, effort high, no tools, single turn.

This is the holdout for the guarded-subtractive line. If H1 and H2 pass, the
v2 clause is the project's recommended candidate pending James's human review
of any disputed items; a further confirmation round is not planned under the
current brief.
