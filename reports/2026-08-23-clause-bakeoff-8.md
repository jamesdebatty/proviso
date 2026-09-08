# Clause bakeoff 8: the vocabulary clause and the blank-slate anchor

**Report date:** 2026-08-23. Data collected 2026-08-14 (generation 05:54 to 07:48 UTC, judging 07:49 to 09:41 UTC). Written nine days after the run; the headline numbers reached `projects/llm-wiki` as source S020 on 2026-08-14 before any report existed.
**Campaign:** `campaigns/clause-bakeoff-8-2026-08-11/`
**Artifacts:** `out/bakeoff-20260814T055452Z/` (75 responses, 50 judgments, `bakeoff-results.json`, generation and judging logs)
**Generator:** Claude Opus 5 High, no tools, single turn, isolated per-response project; CLI pinned `2.1.232 (Claude Code)` as a binary copy in `~/.claude-eval-pins/bakeoff8/`
**Judges:** Claude Sonnet 5 High (resolved `claude-sonnet-5`) and Codex `gpt-5.6-sol` High, blind, isolated, three-way label rotation; Codex CLI `0.147.0`
**Protocol:** `protocol.md`, frozen before live calls, H1 to H4 pre-registered. All nine input hashes in the results manifest re-verified against the working tree on 2026-08-23: all match.
**Baseline:** `control`, no `CLAUDE.md` at all. First direct measurement of the composite against a blank slate; bakeoff 6 measured the earlier v2 clause against one, and bakeoff 7 measured the composite only against v2.

## Executive summary

Bakeoff 8 asked two questions and answered one.

The **blank-slate anchor** (H4) is the answer. Against no `CLAUDE.md`, the
composite clause (bakeoff 7's Response style + Numbers, `f70f86a9`) cut median
words 1161 to 980, a 15.6% reduction, on a long-form design and debugging
battery. Invented-precision entries fell 70% (Sonnet, 46 to 14) and 63%
(Codex, 128 to 48). Nuance rose +0.24 and +0.60. Pooled blind preference went
41 to 9 for the composite, a 0.82 non-tied win rate, and the composite won
every task-by-judge cell, never worse than 3 to 2. Every comparative measure
favored it.

H4 is nonetheless **false as pre-registered**. The protocol committed to a
20 to 40% word reduction, restating the chained figure in
`reports/2026-08-11-baseline-vs-composite.md`. Direct measurement gave 15.6%.
The chained figure overstated the effect by about a factor of two, and that
synthesis report now carries a correction pointer.

The **vocabulary clause** (H1 to H3) got no answer. The pre-registered power
check fired: the control averaged 0.24 (Sonnet) and 0.16 (Codex)
undefined-coinage entries per answer against a floor of 1.0. The battery did
not provoke the defect, so H1 is reported as underpowered, not as a null. The
clause was not adopted; the live `~/.claude/CLAUDE.md` carries the composite's
two sections verbatim and no `## Vocabulary` section.

Formal status is `needs_human_review` with both clause arms `eligible: false`.
The composite fails three gates. Two are the zero-form error gates that have
failed every arm in every campaign, including this control, and that bakeoff
9 has since retired. The third, omissions, fails on one Sonnet entry out of
25 judgments. No human review of this run has been done.

## Pre-registered hypotheses

- **H1, the vocabulary clause reduces undefined coinage: UNDERPOWERED.**
  Sonnet logged 6 entries for the clause arm against 3 for the composite;
  Codex logged 0 against 2. The judges disagree on direction and the
  pre-registered power rule says the test never had a defect to measure.
  The programmatic `novel_coinages` median was 2 in all three arms.
- **H2, no over-suppression of terms of art: TRUE, 5/5.** On
  `terms-of-art-explainer`, Sonnet listed zero missing requirements and zero
  coinage entries against the clause arm in all five repetitions. Sonnet's
  `overall_best` on that task was the clause arm in 4 of 5.
- **H3, composition holds: PARTIAL, 2 of 4 secondary gates.** Words within
  110% of the composite (1023 vs 980, 104%): pass. Omissions not above: pass
  (2 vs 2 Sonnet, 7 vs 8 Codex). Coinage strictly below per judge: fail
  (Sonnet 6 vs 3). Nuance within −0.25 of the composite: fail by 0.03 (Sonnet
  −0.28; Codex −0.12 passes). Head to head, the clause arm against the
  composite: Sonnet 12 to 11 with 2 ties, Codex 11 to 14. No preference.
- **H4, the composite beats the blank slate by 20 to 40% on words with
  omissions not above and nuance within −0.25: FALSE on magnitude.** Words
  −15.6%. Nuance +0.24 and +0.60: pass. Omissions: Codex 8 vs 8 passes; Sonnet
  2 vs 1 fails.

## Results

All figures are from `bakeoff-results.json` unless marked *recomputed*, which
means derived from the judgment and response files in this report's
preparation and not part of the frozen analyzer output.

| Measure | control | composite | composite + vocabulary |
| --- | ---: | ---: | ---: |
| Median words | 1161 | **980 (−15.6%)** | 1023 (−11.9%) |
| Median novel numerals | 22 | **12** | 10 |
| Median novel coinages | 2 | 2 | 2 |
| Stalled responses (of 25) | 0 | 0 | 0 |
| Sonnet invented precision | 46 | **14** | 11 |
| Codex invented precision | 128 | **48** | 38 |
| Sonnet undefined coinage | 6 | 3 | 6 |
| Codex undefined coinage | 4 | 2 | 0 |
| Sonnet omissions | 1 | 2 | 2 |
| Codex omissions | 8 | 8 | 7 |
| Sonnet nuance (mean /5) | 4.68 | **4.92 (+0.24)** | 4.64 (−0.04) |
| Codex nuance (mean /5) | 2.96 | **3.56 (+0.60)** | 3.44 (+0.48) |
| Sonnet focus | 3.76 | **4.40** | 4.36 |
| Codex focus | 3.16 | 4.04 | **4.12** |
| Sonnet error allegations | 5 | 3 | 0 |
| Codex error allegations | 105 | 73 | 70 |
| Confirmed error findings | 5 | 3 | 0 |
| Unresolved disputed findings | 19 | 19 | 24 |
| Pooled preference vs control | | 41 to 9 (0.82) | 38 to 12 (0.76) |

Per judge, the composite won 20 to 5 (Sonnet) and 21 to 4 (Codex). Judge
pairwise agreement was 0.573 (43 of 75 pairs; three pairs per set), down from
0.68 in bakeoff 7.

### Words by task (*recomputed* with the analyzer's own word rule)

| Task | control | composite | composite + vocabulary |
| --- | ---: | ---: | ---: |
| entitlement-drift-mechanism | 1161 | 902 | 843 |
| retry-storm-interaction | 1306 | 993 | 1023 |
| scheduler-ownership-tradeoff | 1120 | 1013 | 1172 |
| tail-latency-narrowing | 1085 | 777 | 1007 |
| terms-of-art-explainer | 1465 | 1512 | 1189 |

The composite's cut is uneven: 28% on the debugging narrative, and on the
explainer it ran 3% longer than the blank slate. The overall 15.6% is a median
over that spread, not a rate to expect per task.

### Gate table (composite, control-relative per the frozen protocol)

| Frozen gate | Result |
| --- | --- |
| Invented precision ≤ control, per judge | PASS (14 ≤ 46, 48 ≤ 128) |
| Undefined coinage ≤ control, per judge | PASS (3 ≤ 6, 2 ≤ 4) |
| Nuance delta ≥ −0.25, per judge | PASS (+0.24, +0.60) |
| Median words ≤ 110% of control | PASS (84%) |
| Stalls ≤ control | PASS (0 vs 0) |
| Omissions ≤ control, per judge | FAIL (Sonnet 2 vs 1; Codex 8 vs 8) |
| No confirmed material errors | FAIL (3; control 5) |
| No unresolved disputed errors | FAIL (19; control 19) |

The omissions failure rests on one entry. Sonnet's two composite omissions are
the scheduler task's "migration and coordination cost across 30 teams" item
(r4), which Sonnet also charged against the control (r3), and a tail-latency
r3 note that the retry-with-long-timeout hypothesis was mentioned in passing
rather than developed. The second is the extra one. At n=25 that is
indeterminate, not a measured omission cost.

## What the error findings say

The frozen confirmation rule counts a finding as confirmed when both judges
allege any error on the same response. It does not check that they allege the
same error. Reading the eight confirmed findings for same-defect agreement, my
read, which is not the human review the protocol assigns:

| Response | Both judges name the same defect? |
| --- | --- |
| entitlement-drift r3 control | No. Sonnet: XOR digest cancellation. Codex: legacy-row provenance, outbox retention. |
| entitlement-drift r4 control | Yes. A counter-valued `source_version` compared against wall-clock time. |
| retry-storm r2 control | Yes. "84% of the pool" confuses share of in-use connections with share of capacity. |
| retry-storm r3 composite | Yes. Retries asserted at gateway, worker, and DB driver when the task gave only a client policy. |
| tail-latency r2 composite | Yes. `tcp_syn_retries=6` stated to give up at ~31 s. |
| tail-latency r5 composite | Yes. Same `tcp_syn_retries` claim. |
| tail-latency r5 control | Yes. Same `tcp_syn_retries` claim, presented as the default. |
| terms-of-art r4 control | No. Sonnet: Little's Law stated with throughput for arrival rate. Codex: outbox-as-WAL, idempotency key in the charge transaction. |

Same-defect count: control 3, composite 3, clause arm 0. Two of the
composite's three are one factual error about Linux SYN retransmission, and
the control made the same error. The `tcp_syn_retries` sysctl appears in six
of the fifteen tail-latency responses (*recomputed*): the "=6 gives ~31 s"
form in composite r2, composite r5, and control r5; the correct "=5 gives
31 s" form in control r3 and clause-arm r3; and composite r4 names the sysctl
and tells the reader to compute the ceiling rather than trust a figure. That
is a model-level error the battery happened to elicit, not something the
clause induced.

The clause arm's zero confirmed findings is structural. Sonnet alleged no
material error against it in any of 25 judgments while Codex alleged 70, and
confirmation needs both. It means Sonnet found nothing to allege, not that
the arm was audited clean.

Under bakeoff 9's replacement rule, same-defect matching expressed as "not
worse than control," the composite's confirmed count (3 vs 3) and disputed
count (19 vs 19) both pass. The omissions gate would be its only failure.

## Deviations and incidents (none affect validity)

- The first generation pass errored on 6 of 75 cells with a `RuntimeError`
  whose text the promptfoo table renderer truncated; the specific message is
  not recoverable from `generation.log`. The detached supervisor detected the
  stall at 69/75 and relaunched. The second pass regenerated exactly those six
  cells cold (scheduler-ownership r1 composite, r2 clause arm, r3 all three
  arms; terms-of-art r5 control, per response timestamps 07:43 to 07:48 UTC)
  and served the other 69 from the provider's hash-validated cache; the pass
  took 6 m 36 s. No partial `.failed-N` artifacts remain.
- All 75 responses record `claude_version` 2.1.232 and `answer_models`
  `["claude-opus-5"]`. All 50 judgments record their resolved judge model.
- The 2026-08-09 next-rounds plan slated round 8 as `no-settled-verdicts`.
  The campaign tested the vocabulary clause instead, on the protocol's stated
  rationale that the coinage defect was observed live rather than mined from
  judges. `no-settled-verdicts` has not been run.
- Cost (*recomputed* from artifacts): generation $10.30 across 75 responses;
  Sonnet judging $6.66 across 25 calls. Codex judging cost is not recorded in
  the artifacts and is unknown.

## Limitations

- Every count labelled error, omission, precision, or coinage is a judge
  allegation. No `human-review.json` exists for this run, so no adjudication
  has fed back into the analyzer. The same-defect table above is my reading
  of the allegation text and should be treated as low-trust until James
  reviews it.
- n=25 sets per arm. Preference at this n has not replicated within the
  project (bakeoff 3 collapsed on re-run); the length, precision, and nuance
  measures are the load-bearing ones here.
- The battery is long-form and reasoning-heavy by design. The 15.6% figure is
  a property of this battery. Bakeoff 6 measured 30% on a short-answer
  battery with the earlier clause; neither number transfers to the other's
  workload.
- The vocabulary clause result is silence, not evidence of no effect. A
  battery that reliably provokes coinage does not exist yet in this project.
- Judge agreement fell to 0.573 with three arms. Cross-run Codex tallies are
  not comparable; all comparisons here are within-run.
- Tool-less and single-turn, like bakeoffs 1 to 7. Bakeoff 9 is agentic and
  tools-enabled, and its preregistration declares itself non-comparable to
  this run. This is the last tool-less concision measurement in the series.
- Self-authored, single operator, one model family.

## What this changes downstream

- `reports/2026-08-11-baseline-vs-composite.md` states "roughly 35% shorter"
  against no clause, chained across bakeoffs 6 and 7. Refuted here by direct
  measurement (15.6%). That report now carries a dated correction pointer at
  its head; its body is preserved.
- Bakeoff 9's A1 arm is byte-identical to this run's `composite`
  (`f70f86a92e9f`, re-verified 2026-08-23), so the clause lineage from
  bakeoff 7 through 9 is unbroken. The vocabulary section is not in that
  lineage.
- The three gates the composite failed are the three that bakeoff 9's
  preregistration changed: two retired as instrument defects, one kept in
  comparative form. This run is the evidence for that change, with 5
  confirmed findings against a no-clause control.
- `projects/llm-wiki/wiki/sources/opus-5-clause-eval-campaigns.md` still
  says bakeoff 8's report is unwritten as of 2026-08-14. Updating it goes
  through the wiki's own `AGENTS.md` workflow and was not done here.

## Verified

`Verified`. Input-hash audit: all nine files named in
`bakeoff-results.json.input_hashes` re-hashed from the working tree on
2026-08-23 match the recorded sha256 values, so the protocol, tasks, variants,
provider, analyzer, and supervisor this report describes are the ones that
ran.

`Verified`. `python3 -m unittest discover -s tests` in
`projects/opus-5-ste-verbosity-eval`, exit 0, 134 tests, 0 failed, 0 skipped.
Scope: the analyzer rules quoted here (dual-judge confirmation, preflight
stall rule, gate arithmetic, power check) as exercised by `tests/test_bakeoff8.py`
and its siblings. It does not check this report's prose or arithmetic.

`Implemented-unverified`. The recomputed figures (per-task words, per-task
preference, cost sums, `tcp_syn_retries` spread, same-defect table) were
produced by ad-hoc scripts during preparation and are not committed as a
reproducible check. Re-running them means re-deriving from the judgment and
response files.

## The composite clause (exact text of `variants/composite.md`)

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

## The vocabulary section as tested (the diff from `composite.md` to `composite-plus-vocabulary.md`)

```markdown
## Vocabulary

Reason in whatever terms are useful to you. In your final response, do not
present a term you coined while working as if it were shared vocabulary — use
the words already in play in this conversation or codebase, or define the
coinage the first time it appears.

Established terms of art from the reader's own domain are not coinages; keep
them, and keep the precision they carry. This is a rule about translating your
shorthand, not about simplifying the subject.
```
