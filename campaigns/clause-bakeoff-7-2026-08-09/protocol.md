# Clause bakeoff 7 protocol (no-invented-numbers)

Date: 2026-08-09
Status: frozen before live calls

## Question

Does adding a conditioned no-invented-numbers clause on top of the proven
concision clause (guarded-subtractive v2) reduce fabricated numeric precision
without suppressing legitimate derivation, and without degrading v2's profile?

## Design rationale

Fabricated precision (cluster D3 in
`notes/next-rounds-defect-taxonomy-2026-08-09.md`) is the only defect cluster
containing an error that survived human adjudication across bakeoffs 4–6
(bakeoff-6 db-disk r5: an assumed "overnight ≈ 12h" presented as a derived
"~3 hours to full"). It is arm-neutral — control ≥ candidate in all three
campaigns — so it is an Opus 5 habit a new clause can target without
interacting with the concision clause. The external scan
(`sources/clause-addition-external-scan-2026-08-09.md`) found no existing
benchmark for this defect and two Anthropic-documented hazards that shape the
clause: blanket conservatism instructions are followed literally and hurt
recall, and verification instructions cause over-verification. The clause is
therefore conditioned (fires only when a quantity is unstated) and
permissive-by-labeling (an explicitly stated assumption is allowed), matching
the pattern in Anthropic's own deployed system prompt.

Protocol upgrades from the next-rounds plan, first applied here:

1. **Baseline is `v2-only`, not no-clause.** The question is incremental
   value on top of the recommended clause, and whether v2's profile survives
   composition.
2. **One new clause line per run** (documented adherence decay with
   instruction count).
3. **Same-defect confirmation:** cross-judge co-occurrence still auto-flags
   `confirmed`, but the analyzer now applies `human-review.json`
   adjudications to confirmed findings as well as disputed ones, so the
   frozen same-defect + material standard (per
   `notes/bakeoff-6-confirmed-error-adjudication-2026-08-06.md`) is applied
   through machinery rather than post-hoc notes.
4. **Comparative gates only** — bakeoff 6 showed absolute-zero gates fail
   even a no-treatment arm.
5. **Binary-copy CLI pins** (the auto-updater garbage-collected a symlinked
   pin mid-project).

## Arms

1. `v2-only`: `variants/guarded-subtractive-v2.md`, byte-identical to the
   bakeoff-6 winner.
2. `v2-plus-numbers`: `variants/v2-plus-numbers.md` — the identical v2 text
   plus one appended section:

   > ## Numbers
   >
   > Do not present a number you assumed or estimated as if it were given or
   > derived. When a quantity the answer depends on is not stated, say it is
   > unknown and, if useful, state your assumption explicitly before using it.

The only changed artifact per arm is `CLAUDE.md`. Isolated single-turn Opus 5
High sessions, no tools, no session persistence; every prompt ends with the
frozen no-tools line.

## Battery

Five fresh tasks (no prompt or topic reused from bakeoffs 2–6):

- Four **invention-tempting** tasks that supply partial quantities so a
  derived-sounding figure is seductive but underdetermined: queue-backlog
  triage (depth given, rates absent), campaign capacity sizing (no traffic
  numbers), backfill duration estimate (row count given, throughput absent),
  payment-incident correlation (rates given, times absent). Each carries a
  calibration rubric item ("does not present an assumed X as derived").
- One **derivable-numbers** task (log-retention arithmetic) where computing
  the figure IS the correct behavior — the over-suppression control. The
  external scan predicts calibration clauses over-fire; this task detects it.

5 repetitions × 2 arms = 50 Opus responses; 25 sets × 2 judges = up to 50
judge calls. Live-call ceiling: 100.

## Instrument changes (frozen)

- Judges additionally return `invented_precision` per answer: each instance
  where a specific quantity is presented as given or derived when it is
  neither, with explicitly labeled assumptions excluded.
- Analyzer reports a descriptive `median_novel_numerals` per arm (numeric
  tokens in the answer not present in the prompt). Descriptive only; no gate.
- Judge prompt, schema, blinding, preflight v2, and the dual-judge error rule
  otherwise unchanged from bakeoff 6.

## Hypotheses (pre-registered)

- H1 (the clause works): pooled `invented_precision` entries for
  `v2-plus-numbers` strictly below `v2-only`, and not above for either judge
  individually.
- H2 (no over-suppression): on the derivable task, `v2-plus-numbers` computes
  the ~60 GB steady-state figure in ≥4/5 repetitions (rubric item not listed
  missing by Sonnet in more than 1 rep).
- H3 (assumptions surfaced, not suppressed): on the backfill-estimate task,
  the explicit-assumption rubric item is satisfied in ≥4/5 `v2-plus-numbers`
  repetitions per Sonnet.
- H4 (v2 profile survives composition): all frozen gates pass — omissions,
  nuance (≥ −0.25), stalls not above baseline; median words ≤ 110% of
  baseline (the clause legitimately adds assumption-labeling text);
  `invented_precision` entries not above baseline per judge; no confirmed
  errors after same-defect review and no unresolved findings.

Realistic ceiling, pre-registered: external evidence (AbstentionBench,
config-adherence studies) shows instruction effects are partial. H1 asks for
a reduction, not elimination.

## Environment (recorded at freeze)

- Claude Code CLI `2.1.226 (Claude Code)`, binary copy at
  `~/.claude-eval-pins/bakeoff7/claude`.
- Codex CLI `codex-cli 0.147.0`, isolated npm prefix at
  `~/.claude-eval-pins/bakeoff7/codex`; judge model `gpt-5.6-sol`, effort
  high. (Judge versions differ from bakeoff 6 — 2.1.222/0.146.1 — which is
  acceptable because all comparisons are within-run.)
- Generator: Claude Opus 5, effort high, no tools, single turn.

If H1–H4 all pass, `v2-plus-numbers` becomes the recommended CLAUDE.md and
the round-8 baseline. If H2 or H3 fail, the conditioned phrasing
over-suppresses and the clause is revised, not shipped.
