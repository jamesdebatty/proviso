# Clause bakeoff 6: the guarded-subtractive v2 holdout

**Date:** 2026-08-06
**Campaign:** `campaigns/clause-bakeoff-6-2026-08-06/`
**Artifacts:** `out/bakeoff-20260806T072008Z/` (50 responses, 50 judgments, `bakeoff-results.json`)
**Generator:** Claude Opus 5 High, no tools, single turn, isolated per-response project; CLI pinned `2.1.222 (Claude Code)`
**Judges:** Claude Sonnet 5 High + Codex `gpt-5.6-sol` High, blind A/B, isolated; Codex CLI pinned `0.146.1`
**Protocol:** frozen before live calls (`protocol.md`), hypotheses pre-registered

## Executive summary

The v2 clause — run-5 `guarded-subtractive` with the single word "background"
removed from its do-not list — **completely fixed the defect it targeted**: the
why-rationale omission on explainer tasks vanished (0 missing-requirement
entries in all 10 explainer repetitions, both judges; run-5 baseline was
missing in 2 of 5). It cut median answer length 30% (507 vs 729 words), scored
*above* control on nuance for both judges, passed the omission gate that
killed run 5, and won 57% of non-tied pairwise preferences. Zero stalls.

It is still not an automatic pass. The frozen error gates failed — 3 confirmed
material errors and 13 unresolved disputes — but **control failed the same
gates** (2 confirmed, 17 disputes). This round's harder technical battery
(PostgreSQL major-version upgrades, database disk mechanics) made Codex
dramatically more aggressive (41 error allegations against control, 29 against
v2; near zero in run 5), and the confirmed-error rule counts response-level
co-occurrence, not same-error agreement. The error findings measure Opus on
hard tasks, roughly arm-neutrally — not clause harm. Formal verdict:
`needs_human_review`. Practical verdict: v2 is the best candidate the project
has produced, pending James's review of the 5 confirmed findings.

## Pre-registered hypotheses

- **H1 — the fix restores why-rationale on explainers: TRUE.** Target:
  present ≥4/5 reps per explainer task. Result: 5/5 on both explainer tasks,
  and not just for the why item — *no* missing-requirement entries of any kind
  were logged against v2 explainer answers by either judge (10/10 reps clean).
- **H2 — v2 passes all six frozen gates: FALSE.** Four of six pass. The two
  failures (confirmed errors, unresolved disputes) are shared with control;
  see the analysis below.
- **H3 — concision profile preserved (10–35% reduction): TRUE.** −30.4%
  (deeper than run 5's −20%, on a battery with longer control answers).

## Results

| Measure | control | guarded-subtractive-v2 |
| --- | ---: | ---: |
| Median words | 729 | **507 (−30.4%)** |
| Stalled responses (of 25) | 0 | 0 |
| Sonnet nuance (mean /5) | 4.84 | **4.88 (+0.04)** |
| Codex nuance (mean /5) | 3.60 | **3.76 (+0.16)** |
| Sonnet omission entries | 13 | **12** |
| Codex omission entries | 17 | **16** |
| Sonnet error allegations | 2 | 3 |
| Codex error allegations | 41 | 29 |
| Confirmed material errors | 2 | 3 |
| Unresolved disputed errors | 17 | 13 |

Pooled pairwise preference: v2 wins 27, control 20, tie 3 — **57.4%** non-tied
win rate for v2. Judge pairwise agreement: 0.44.

### Gate table (guarded-subtractive-v2)

| Frozen gate | Result |
| --- | --- |
| Omissions ≤ control, per judge | **PASS** (12≤13, 16≤17) |
| Nuance delta ≥ −0.25, per judge | **PASS** (+0.04, +0.16) |
| Median words ≤ control | **PASS** |
| Stalls ≤ control | **PASS** |
| No confirmed material errors | **FAIL** (3) |
| No unresolved disputed errors | **FAIL** (13) |

The omission gate is the one run 5 failed 15-to-6. On this holdout v2 sits
*below* control for both judges. The adjudicated secondary omission reading
pre-registered in the protocol is moot.

## Why the error gates failed — and what that failure measures

Three observations bound the interpretation:

1. **Control fails the same gates.** 2 confirmed errors and 17 unresolved
   disputes against answers produced with *no clause at all*. A gate that the
   no-treatment arm cannot pass is measuring the environment, not the
   treatment.
2. **The battery, not the clause, changed the error rate.** Codex alleged ~70
   errors across both arms this round versus near zero in run 5. The new
   tasks (major-version database upgrades, WAL/disk-full mechanics) have many
   more falsifiable technical claims per answer, and most Codex allegations
   are "too categorical" qualifications (e.g. "treats reverse logical
   replication as generally lossless"). Both arms drew the same style of
   allegation on the same tasks.
3. **"Confirmed" here means co-occurrence, not agreement.** The frozen rule
   confirms an error when both judges allege *something* against the same
   response. With Codex alleging against most responses, nearly any Sonnet
   allegation auto-confirms. Inspection shows several confirmed pairs where
   the two judges describe different defects (e.g. db-disk-triage r5: Sonnet
   flags an invented elapsed-time figure; Codex flags a conflated
   transaction/WAL claim).

Arm difference in confirmed errors: 3 vs 2 on 25 responses per arm —
statistically indistinguishable. All five confirmed findings sit on the two
hardest tasks (db-disk-triage, db-major-upgrade), both arms represented.

## Bottom lines

- The one-word diagnosis from run 5 was correct: removing "background"
  eliminated the explainer why-rationale omission entirely, at zero cost to
  concision (the cut deepened to −30%).
- `guarded-subtractive-v2` is the first candidate in six campaigns to pass
  the omission, nuance, length, and stall gates simultaneously while winning
  pairwise preference.
- The remaining gate failures are shared with the no-clause control and trace
  to battery difficulty plus a co-occurrence artifact in the confirmed-error
  rule — evidence about Opus 5 answering hard database questions, not about
  the clause.
- Formal status: `needs_human_review`. The queue for James: 5 confirmed
  findings (3 v2, 2 control; check whether each judge pair alleges the same
  defect) and 30 disputed entries (13 v2, 17 control). If review dismisses or
  equalizes them, v2 is the recommended clause for deployment.

## Limitations

- The confirmed-error rule's co-occurrence weakness was exposed, not
  corrected, this round; the 3-vs-2 comparison above is my framing, not a
  frozen gate. A same-defect matching rule would need to be frozen before a
  future run.
- Codex's mean scores sit a full point below Sonnet's on this battery and its
  allegation volume swung ~40× between runs 5 and 6 on the same rubric —
  judge calibration is battery-sensitive, so cross-run score comparisons are
  unreliable; only within-run arm deltas are used here.
- n=25 sets; the 57.4% preference win rate is within noise (runs 1–5
  precedent: preference at this n does not replicate reliably). The length,
  omission, and nuance findings are the load-bearing results.
- Model adjudications (including the run-5 omission adjudication that
  motivated v2) remain recommendations pending James's sign-off.

## Deviations and incidents (none affect validity)

- Host-session restarts orphaned the judging job twice; each relaunch resumed
  losslessly from hash-validated caches. The final relaunch ran detached
  (`nohup`/`setsid`) to survive further restarts.
- Codex CLI auto-updated 0.146.1 → 0.147.0 after 48 of 50 judge calls; the
  provenance check failed closed as designed. Codex 0.146.1 was reinstalled
  in an isolated prefix (`/tmp/codex-pin`) and the final call ran under it.
  **All 50 judgments were produced under codex-cli 0.146.1.**
- Generation completed in one pass: 28m26s, 50/50, zero failures, zero stalls.

## Postscript: human review outcome (added after initial publication)

James reviewed the error queue in-session after this report was first
written. Outcomes, recorded in
`notes/bakeoff-6-confirmed-error-adjudication-2026-08-06.md` and in the out
dir's `human-review.json`:

- **The 30 disputed entries were dismissed as a class** (single-judge
  "too categorical" qualification allegations hitting both arms at similar
  rates; below the judge prompt's material bar). Applied via
  `human-review.json`; the recomputed `bakeoff-results.json` now shows the
  disputes gate **PASS** — five of six frozen gates green.
- **The 5 confirmed findings were adjudicated** under a same-defect +
  material standard, with James's concurrence: three dissolve as
  co-occurrence artifacts, one (gh-ost analogy) falls below the material bar
  both judges assigned it, and **one survives — the fabricated time estimate
  in db-disk-triage r5 (v2)**. Adjudicated tally: v2 = 1, control = 0, with
  the caveat that Codex flagged the identical invention in a control answer.
- The frozen confirmed-error gate still reads FAIL (it counts the raw 5 and
  cannot be reclassified by design), so the machine verdict is
  `no_eligible_candidate`. The reviewed verdict is: **v2 recommended**, with
  one residual, clause-independent Opus habit (invented quantitative
  precision on urgency tasks) noted as a separate mitigation candidate.

Additional deviation: by the time the review was applied, the auto-updater
had garbage-collected the pinned 2.1.222 binary, so the final summary was
recomputed offline (`resummarize.py`) from the cached artifacts, every one
revalidated by hash against its recorded capture-time versions. No live
calls; any missing or tampered artifact would still fail closed.

## The clause (v2, exact text)

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
```
