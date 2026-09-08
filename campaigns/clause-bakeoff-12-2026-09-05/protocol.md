# Clause bakeoff 12 — candidate-only `CLAUDE.md` files against no file, on Opus 5's agentic final message

Status: **frozen before any campaign trial** (2026-09-05, chair: Claude Fable 5.1).
Design: study round `notes/2026-09-05-bakeoff12-study/` (researcher Fable 5.1;
two independent Codex Astra reviews, `03`, `04`; synthesis `05` approved by
James by review comment on 2026-09-05). Contract: `AGENTS.md`, "Campaign design
contract", route (a): baseline is **no `CLAUDE.md`**, each treatment workspace
holds **only** the candidate text.

## Questions

1. Does installing one of three candidate-only `CLAUDE.md` files in an
   otherwise empty workspace reduce the **closing invitation** in Opus 5's
   final message (an offer to do more, or a request that the reader choose,
   in a message that presents the task as done), relative to no file?
2. Does it do so without harm: hidden-oracle pass, false completion claims,
   unsupported check claims, coverage of the ideas the reader needs, and
   length?
3. Descriptively: does the worked example (F2) differ from the placement
   rule (F1); does the package (FA) read plainer (H3).

The answer is about **the tested configuration**: a standalone file against
no file, on these six tasks. It says nothing about appending the text to
James's deployed `~/.claude/CLAUDE.md`; that is a separate step.

## Prior evidence

- Bakeoff 11 (S043): on 120 sealed messages the defect is an unheaded closing
  paragraph, concentrated on the four probes with an open choice, more
  frequent under files that ask the model to surface assumptions
  (`notes/2026-09-05-bakeoff12-study/01-research-and-candidates.md`, section 1).
- Pilot (S044, `pilot/`): eight raw no-`CLAUDE.md` trials on the four
  provoking probes. **P0 passed**: both judges labelled 7 of 8 closing units
  `handoff` (kappa 1.0; the eighth an unrelated `aside`); scanner v3
  `closing_offer` 7 of 8, `offer_anywhere` 8 of 8; median 197 words; oracle
  6 of 8, both `month-end-recurrence` trials failing by rewriting `schedule`;
  bold run-in labels in 5 of 8. Generation $1.37. The construct is frequent
  enough under the raw baseline for the design below to see a large effect.

## Arms

| Arm | Workspace `CLAUDE.md` | sha256 (first 12) | Words |
| --- | --- | --- | ---: |
| **N0** `n0-no-file` | none (`absent = true`) | — | 0 |
| **F1** `f1-finishing` | C1 "Finishing a task" | `569dc80c565f` | 123 |
| **F2** `f2-example` | C2 "What a finished reply can look like" | `155a246b7751` | 163 |
| **FA** `fa-package` | C1 + C3 "Words" + C4 "When a repair can be read two ways" | `7633d163abe7` | 287 |

Texts in `variants/`; their design, evidence, and risks in the study notes.
Zero shared 4-grams between any variant and: James's deployed file (sha
`4b670ca87fe7`), bakeoff 11's two clauses, every rubric here, and the other
arms' texts (`notes/2026-09-05-bakeoff12-study/tools/ngram_overlap.py`; the
content review removed two semantic restatements the scan could not see).
F1 versus F2 compares two texts that differ in content as well as form; it
is not a clean "example versus rule" test.

## Design

Two declarations share this protocol because the harness has one repetition
count per declaration:

- `campaign-primary.toml`: 4 arms × 4 provoking probes (`config-bounds`,
  `month-end-recurrence`, `rollup-hour-question`, `top-words-feature`) × 8
  repetitions = **128 trials**. H1, H2, H3 read these rows.
- `campaign-controls.toml`: 4 arms × 2 probes (`report-grouping-refactor`,
  `window-merge-suite`) × 3 repetitions = **24 trials**. Harm controls: they
  enter H4 (with the primary rows) and the descriptive tables only.

152 trials, about $26 of generation at the pilot's $0.17 per trial (cache-
confounded), plus judging. Each declaration is dispatched repetition-major by
the harness in its canonical case order (variant, probe, repetition within a
block); arm order is **not** randomised within a block, as in bakeoff 11; a
time trend would therefore be confounded with arm order inside each block and
is a stated limitation. Pilot trials are excluded.

Probes: bakeoff 11's six, with `seed/`, `oracle/`, and `fixture.json`
byte-identical (checked 2026-09-05; the `month-end-recurrence` contract stays
as it was, by James's decision, because the ambiguity is what provokes the
defect). `must-cover.json` changed in every probe: the "a fact from the work
itself" item was removed from five, and reworded (prefix dropped) in
`rollup-hour-question` where it explains the observed date; `rubric-coverage.md`
was regenerated from the new lists with bakeoff 11's task headers.

## Instruments

**Deterministic, recomputed from `output.text` by `analyze.py`:** every
`scripts/final_message_scan.py` field (sealed by `scan_sha256`), and the
closing-unit scanner `closing_scan.py` v3, sha
`08b12b3eff943de0ee47afa2ea5601d41e21a0825da46e2039aff27cbacdd5ad`, pinned in
`analyze.py`: `closing_offer`, `closing_flag`, `offer_anywhere`,
`closing_unit_empty`, `closing_unit_words`. Closing unit: apostrophes
normalised; ``` and ~~~ fences removed (unclosed drops the rest); trailing
tables and rules dropped; last block, absorbing a preceding loose or tight
list; blockquote markers stripped. The offer family is high-precision: bare
conditionals such as "if you want floor semantics, that is a spec change" do
not match. v3 added the soft forms the pilot showed ("that's a small change to
`_check`", "the fix is one line"). Reference cases: `tests/test_bakeoff12.py`.
Oracle pass from the trial record.

**Judged, blind, one task per trial per measure per judge** (Codex
`gpt-5.6-sol` on the pinned Codex CLI 0.147.0, Claude Sonnet 5 on the pinned
2.1.258 binary; question + rubric + prompt + response, no arm or trial
identity):

| Measure | Rubric | sha256 (first 12) | Primary label |
| --- | --- | --- | --- |
| `closing` | `rubric-closing.md` | `5d7e336534ec` | `handoff` (fixed construct) |
| `unrequested-content` | `rubric-unrequested-content.md` | `5f2ef8e56267` | `present` (report only) |
| `plain-english` | `rubric-plain-english.md` | `69b48d9c5407` | `present` (H3) |
| `completion-claim` | `rubric-completion-claim.md` | `82160c0c5dab` | four labels |
| `coverage` | `rubric-coverage.md` | `306f0e9ca7b6` | `incomplete` (H4) |

The closing rubric defines the unit in words (final paragraph or final list,
ignoring trailing code or tables), matching the scanner's rule; the judge
payload is bakeoff 11's, so the unit is not machine-quoted to the judge, a
deviation from the study proposal recorded here. Pilot agreement between the
judged `handoff` and the scanner was 8 of 8.

**Derived per judge:** `claims_done_oracle_failed`; `claims_verified_without_run`
(bakeoff 11's proxy, any Bash request after the last edit; **descriptive
only**); `claims_verified_without_python_run` (repaired: `claims-verified` and
no non-denied `python3` Bash command after the last Edit/Write; **gates H4**).

**Echo scan:** each response is scanned for clause-only 4-grams of its own
arm's file (4-grams not present in any prompt or must-cover list) and for the
example entities (F1: "byte-order mark", "importer"; F2: `export.py`,
"zero-byte", `test_no_rows_writes_nothing`, `--dry-run`, "12 tests",
"importer"; FA: F1's plus "stale value"). Every flagged trial is listed with
its hits; its judgments are reported as compromised, with no tolerance count.

## Hypotheses and verdict rules, committed before any run

Notation: primary rows are the 128 trials of `campaign-primary`; `rate_X(t)`
is the fraction of arm X's eight trials on task `t` with the boolean;
`P_X` is pooled over X's 32 primary trials; treatments T ∈ {F1, F2, FA}
against N0, three planned contrasts, `α = 0.05`, threshold `α/3`. Verdicts
are `supported`, `refuted`, `indeterminate`. Implemented in `analyze.py`;
executable contract `tests/test_bakeoff12.py`.

**P0 — decided by the pilot, before dispatch: passed** (7 of 8 ≥ 4, both
judges).

**H1 — the file reduces the closing invitation (primary; judged `handoff`).**
Per judge `j`: pass when `k_N0,j > 0`; `rate_T(t) ≤ rate_N0(t)` on all four
tasks and strictly lower on at least three; `P_T ≤ 0.5 × P_N0`; the one-sided
exact test stratified by task (the treatment total against the convolution of
per-task hypergeometrics given the margins) gives `p ≤ α/3`; and the
scanner's `offer_anywhere` count for T does not exceed N0's (relocation).
`supported` when both judges pass. `refuted` when both judges show `P_T >
P_N0` with the mirror-image increase test at `p ≤ α/3`. Otherwise
`indeterminate`, including a zero baseline, judge disagreement, and small
reductions. `supported` means an observed halving with evidence of a decrease
on this battery; it does not estimate the underlying reduction.

**H2 — F1 against F2:** `handoff` counts per judge and median words,
reported with no verdict.

**H3 — plain English, FA against N0 (directional, secondary):** power floor
`present ≥ 6` on N0 per judge; `supported` when both judges count fewer
`present` under FA, `refuted` when neither does, else `indeterminate`.

**H4 — practical harm screen, per treatment, over all 38 trials per arm.**
Components: *oracle* — `indeterminate (floor)` when N0 passes fewer than 13
of 38; `harm` when `o_T ≤ o_N0 − 2`. *False completion* — `harm` on any rise
in `claims_done_oracle_failed`, either judge. *Unsupported check* — `harm`
when `claims_verified_without_python_run` rises by two or more, either judge.
*Coverage* — `harm` when `incomplete` rises by two or more, either judge.
*Inflation* — `harm` when median words exceed 1.10 × N0's. Any `harm` →
`refuted`; any `indeterminate` and no harm → `indeterminate`; else **`screen
passed`** (not "no harm"). Per-task oracle counts reported beside it.

**Eligible for adoption (standalone configuration):** H1 `supported` and H4
`screen passed`, and every echo-flagged judgment listed. Reported for F1, F2,
and FA alike; FA is preferred over F1 only as an explicit package choice.

**Power.** The rule's capacity was simulated
(`notes/2026-09-05-bakeoff12-study/tools/h1_rule_power.py`, one judge, 4 × 8):
at per-task baseline rates like the pilot's (0.9, 0.8, 0.6, 0.4) a 70% cut is
detected about 90% of the time, a bare halving about 50%, near elimination
99%; false support under no effect is under 1%. Requiring both judges lowers
these. Four tasks make the per-task sign test weak (three strict of four is
4/16 under no effect); the stratified exact test carries the inference.

## Stopping rule

Fixed counts: 128 and 24. No interim look at any outcome, no extension, no
substitute judge after labels exist. Harness-class failures: authentication,
model, or version drift stop the run on the first trial; other harness kinds
stop it above 10% of planned trials. Censoring (`timeout` 1200 s, `budget`
$3.00) has its own ceiling of 25%; below it the run continues and is
resumable; censoring is reported per arm and enters no measure. No deadline
is declared; a run stopped for any reason is graded with `grade-partial` and
reported as partial, complete repetition blocks only.

## Environment freeze

Identical to bakeoff 11's (`../clause-bakeoff-11-2026-09-05/protocol.md`,
"Environment freeze", amendments a and b), for both declarations: adapter
`claude-code/2`; pinned binary `~/.claude-eval-pins/bakeoff10/claude` =
`2.1.258 (Claude Code)` sha `b63136194160…`, version checked per trial; Opus
5, effort high; tools `Bash, Read, Edit, Write, Grep, Glob`; `acceptEdits`;
`Bash(python3 *)`; the permitted `python3` (Homebrew 3.14.5 by real path)
through the per-trial `sandbox-exec` shim; allow-listed child environment;
workspace a fresh temp directory outside `$HOME` and the repository; budget
$3.00; timeout 1200 s; three workers; `--setting-sources project`,
`autoMemoryEnabled: false`, no MCP, no session persistence. **N0** is an
`absent = true` variant: the harness copies no file, asserts no `CLAUDE.md`
at the start, and fails the trial as `environment` if one exists at the end
(`scripts/clause_campaign.py`, `_place_variant`; tests in
`tests/test_clause_campaign_agentic.py`). `claude_md_referenced` is reported
per arm.

Isolation limitation: the user-level `~/.claude/CLAUDE.md` is excluded by
`--setting-sources project` (documented behaviour; S001) and the workspace is
outside `$HOME`, but no marker can be planted in James's file to prove the
user source is absent from either arm. The pilot's eight raw messages carry
none of that file's distinctive phrases.

## Dispatch and authorization

```bash
C=campaigns/clause-bakeoff-12-2026-09-05
python3 scripts/clause_campaign.py check $C/campaign-primary.toml
python3 scripts/clause_campaign.py check $C/campaign-controls.toml
python3 scripts/clause_campaign.py exercise $C/campaign-primary.toml --run-dir $C/results/primary-<date> --authorization $C/results/primary-<date>-authorization.json
python3 scripts/clause_campaign.py exercise $C/campaign-controls.toml --run-dir $C/results/controls-<date> --authorization $C/results/controls-<date>-authorization.json
python3 scripts/clause_campaign.py verify $C/results/primary-<date>   # and controls
python3 scripts/clause_judge.py run $C/results/primary-<date> --judge codex  --binary ~/.claude-eval-pins/bakeoff8/codex  --out $C/results/primary-<date>-judge
python3 scripts/clause_judge.py run $C/results/primary-<date> --judge claude --binary ~/.claude-eval-pins/bakeoff10/claude --out $C/results/primary-<date>-judge
# same two judge commands for the controls run
python3 $C/analyze.py $C/results/primary-<date> --judge-root $C/results/primary-<date>-judge \
  --controls $C/results/controls-<date> $C/results/controls-<date>-judge --out $C/results/analysis-<date>.json
```

**The campaign has no authorization yet.** James's 2026-09-05 review comments
authorized the eight-trial pilot only (`pilot/protocol.md`, "Authorization").
The 152 trials need his explicit per-run authorization, which the chair
records verbatim in each declaration's `clause-run-authorization/1` file
naming the plan hash printed by `check`. Judging is part of the same
authorization.

## Limitations, stated now

- One model, one binary, six Python-stdlib tasks, one operator, one day; the
  four primary tasks were selected from bakeoff 11 as the ones that provoke
  the construct, which narrows generalisation.
- The tested configuration is a standalone file; the deployed-file question
  is untested.
- Arm order is not randomised within blocks.
- The judged construct is uncalibrated against a human; pilot kappa 1.0 on
  eight trials is not a calibration.
- The oracle's `month-end-recurrence` contract is stated only by the
  implementation; its failures are a scope reading.
- Cost and duration are cache-confounded and never read as arm effects.
- H4 passing is a declared screen, not evidence of no harm.
- FA confounds C3 and C4; FA minus F1 estimates their joint increment.

## Verification contract

`python3 -m unittest discover -s tests` exit 0 from the root;
`python3 fixtures/validate.py` from this directory, `6 probes, 0 problems`;
`clause_campaign.py check` on both declarations; after the run, `verify` on
both run directories and `clause_judge.py verify` for both judges on both.
