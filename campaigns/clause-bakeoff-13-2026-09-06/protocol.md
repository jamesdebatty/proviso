# Clause bakeoff 13 — size-anchored candidate files against no file, on Opus 5's agentic final message

Status: **frozen before any campaign trial** (2026-09-06, chair: Claude Fable 5.1).
Design: study round `notes/2026-09-05-bakeoff13-study/` (researcher Fable 5.1;
two independent Codex Astra reviews, `03`, `04`; gate document `05` approved
by James by review comment on 2026-09-06: G1, G2, and F2R approved; route (a)
approved; probe set, instruments, and no pilot confirmed; GA deferred).
Contract: `AGENTS.md`, "Campaign design contract", route (a): baseline is
**no `CLAUDE.md`**, each treatment workspace holds **only** the candidate text.

## Questions

1. Bakeoff 12 (S045) showed that three candidate-only files removed the
   closing invitation and lengthened every message by expanding content the
   raw message already had; none of the files set a size. Does a file that
   adds a size signal — a compressed worked example (G1) or a rule with
   per-sentence and per-message anchors (G2) — still remove the invitation
   **without** lengthening the message, relative to no file?
2. Does it do so without harm: hidden-oracle pass, false completion claims,
   unsupported check claims, coverage of the ideas the reader needs, and
   length on the controls and on every task?
3. Does bakeoff 12's F2 result replicate on a concurrent run (F2R), and how
   does G1, which differs from F2R in the quoted reply only, compare with it?

The answer is about **the tested configuration**: a standalone file against
no file, on these six tasks. It says nothing about appending the text to
James's deployed `~/.claude/CLAUDE.md`; that is a separate step.

## Prior evidence

- Bakeoff 12 (S045, `../clause-bakeoff-12-2026-09-05/`, report
  `reports/2026-09-05-clause-bakeoff-12.md`): 152 trials plus an 8-trial
  pilot. H1 supported for F1, F2, FA (both judges); H4 refuted for all three
  on length (primary median ratios 1.29–1.44 over all 38 trials; F2's primary
  ratio 1.21), F1 and FA also on coverage and the check proxy. Under no file
  the judged `handoff` rate on the four provoking probes was high enough for
  the H1 rule (S045; the pilot S044 showed 7 of 8).
- Where the words went (`notes/2026-09-05-bakeoff13-study/01-research-and-candidates.md`,
  section 2): verification sentences grew from a few words to the example's
  30–40-word shape (F2's frame "ran N tests, all passing" in 25 of 38 F2
  messages, 0 of 114 others); scope-negative closings appeared; F1's rule
  became a four-bullet decisions list; on the two control tasks body prose
  more than doubled under every file.

## Arms

| Arm | Workspace `CLAUDE.md` | sha256 (first 12) | Words | Role |
| --- | --- | --- | ---: | --- |
| **N0** `n0-no-file` | none (`absent = true`) | — | 0 | baseline (route (a)) |
| **F2R** `f2r-example` | bakeoff 12's F2, byte-identical | `155a246b7751` | 163 | replication; within-run reference for G1 |
| **G1** `g1-terse-example` | "What a finished reply can look like", reply compressed 81 → 45 words | `afec88c177b3` | 127 | treatment |
| **G2** `g2-diff-reader` | "The message after the work" | `477903c748a0` | 97 | treatment |

Texts in `variants/`; their design, evidence, and risks in the study notes.
G1 differs from F2R in the quoted reply only, so F2R–G1 is a one-edit
contrast that changes content and size together. Zero shared 4-grams
between G1 or G2 and: James's deployed file (sha `4b670ca87fe7`), bakeoff
11's texts, every rubric here, and each other; G1 and F2R share 93 4-grams
by construction (`01`, section 5; the content review's semantic rulings are
recorded there). GA (G1 + G2) is deferred by James's decision.

## Design

Two declarations share this protocol because the harness has one repetition
count per declaration:

- `campaign-primary.toml`: 4 arms × 4 provoking probes (`config-bounds`,
  `month-end-recurrence`, `rollup-hour-question`, `top-words-feature`) × 8
  repetitions = **128 trials**. H1, H2, and H3 read these rows.
- `campaign-controls.toml`: 4 arms × 2 probes (`report-grouping-refactor`,
  `window-merge-suite`) × 3 repetitions = **24 trials**. Harm controls: they
  enter H4 (with the primary rows) and the descriptive tables only.

152 trials, about $26–29 of generation at bakeoff 12's $0.17–0.19 per trial
(cache-confounded), plus judging on subscription. No generation pilot: the
construct rate under N0 is known (S045) and a concurrent N0 shows any drift;
a low N0 `handoff` rate is handled by H1's `k_N0 > 0` and indeterminate
outcomes. N0 is re-run, not reused: a non-concurrent baseline would confound
the arm contrast with any server-side change.

**Dispatch order.** Both declarations carry `dispatch_seed = 13`. The harness
dispatches repetition-major and, inside each repetition block, shuffles the
case order by `random.Random(seed * 1000 + repetition)`
(`scripts/clause_campaign.py`, `dispatch_order`; test
`test_dispatch_seed_shuffles_within_blocks_and_is_reproducible_from_the_plan`).
The plan's case order stays canonical; the order actually dispatched is
reproducible from the sealed plan and is recorded by each trial's
`started_utc`. This removes the arm-with-time confound inside a block that
bakeoffs 11 and 12 carried.

Probes: bakeoff 12's six, with `seed/`, `oracle/`, `fixture.json`, and
`must-cover.json` byte-identical (tree shas checked at declaration; the
`month-end-recurrence` contract stays as it was, by James's decision in
bakeoff 12). `tests/test_bakeoff13.py` asserts the probe trees, the five
rubrics, the closing scanner, and `fixtures/validate.py` are byte-identical
to bakeoff 12's, and that F2R is byte-identical to bakeoff 12's F2.

## Instruments

**Deterministic, recomputed from `output.text` by `analyze.py`:** every
`scripts/final_message_scan.py` field (sealed by `scan_sha256`); the
closing-unit scanner `closing_scan.py` v3, sha
`08b12b3eff943de0ee47afa2ea5601d41e21a0825da46e2039aff27cbacdd5ad`, pinned in
`analyze.py`: `closing_offer`, `closing_flag`, `offer_anywhere`,
`closing_unit_empty`, `closing_unit_words` (reference cases carried in
`tests/test_bakeoff13.py`); `words` = the sealed `output.words` (whitespace
tokens of the final message; code and tables count; a zero-word trial is
excluded from H2 and reported); the frame count (`ran N tests, all
passing`); the word-role decomposition (a keyword heuristic that assigns
whole sentences to `offer`, `verification`, `scope_negative`, `decision`,
`test_enum`, `code`, or `body`; descriptive only). Oracle pass from the
trial record.

**Judged, blind, one task per trial per measure per judge** (Codex
`gpt-5.6-sol` on the pinned Codex CLI 0.147.0, Claude Sonnet 5 on the pinned
2.1.258 binary; question + rubric + prompt + response, no arm or trial
identity), the bakeoff 12 rubrics unchanged:

| Measure | Rubric | sha256 (first 12) | Primary label |
| --- | --- | --- | --- |
| `closing` | `rubric-closing.md` | `5d7e336534ec` | `handoff` (fixed construct) |
| `unrequested-content` | `rubric-unrequested-content.md` | `5f2ef8e56267` | `present` (report only) |
| `plain-english` | `rubric-plain-english.md` | `69b48d9c5407` | `present` (report only) |
| `completion-claim` | `rubric-completion-claim.md` | `82160c0c5dab` | four labels |
| `coverage` | `rubric-coverage.md` | `f91951b709ac` | `incomplete` (H3, H4); `excerpts` name the missing items |

**Derived per judge:** `claims_done_oracle_failed`; `claims_verified_without_run`
(bakeoff 11's proxy, any Bash request after the last edit; descriptive
only); **`no_python_command_after_last_edit`** — a `claims-verified` label
with no non-denied Bash command after the last Edit or Write in which
`python3` (or `python3.N`) is the first word of a simple command (split on
`&&`, `||`, `;`, `|`, newline; leading `VAR=value` stripped). This is
bakeoff 12's `claims_verified_without_python_run` repaired for compound
commands and renamed to what it measures (re-counted on bakeoff 12: FA 5 → 3
on both judges, other arms unchanged, no verdict changes). **It is a
command-presence proxy**, not a check-honesty measure: it splits quoted text
as if it were shell syntax, ignores short-circuit execution, counts `python3
--version`, and misses edits made through Bash. It gates H4 under this name.

**Echo scan:** each response is scanned for clause-only 4-grams of its own
arm's file (4-grams not present in any prompt or must-cover list) and for
the example entities (F2R: `export.py`, "zero-byte",
`test_no_rows_writes_nothing`, `--dry-run`, "12 tests", "importer"; G1:
`export.py`, `--dry-run`, "12 tests", "empty query", "missing header", "row
count"; G2: clause-only 4-grams only). Every flagged trial is listed with
its hits, and every flagged trial enters the sensitivity analysis below.

## Hypotheses and verdict rules, committed before any run

Notation: primary rows are the 128 trials of `campaign-primary`; `rate_X(t)`
is the fraction of arm X's eight trials on task `t` with the boolean; `P_X`
is pooled over X's 32 primary trials; treatments T ∈ {G1, G2}; the
replication arm is F2R; all against N0; `α = 0.05`. Verdicts are
`supported`, `refuted`, `indeterminate` (H1); `shorter`, `longer`,
`indeterminate` plus the `non_inferior` flag (H2). Implemented in
`analyze.py`; executable contract `tests/test_bakeoff13.py`.

**Multiplicity, declared.** The confirmatory claims are one direction per
family: H1 "T reduces the invitation" and H2 "T shortens the message", each
tested one-sided at α/2 per treatment (two treatments per family; Bonferroni
within family). The opposite-direction verdicts (`refuted` in H1, `longer`
in H2) are harm findings reported at nominal one-sided α/2 with no family
guarantee; over-detecting harm is the intended asymmetry. H3 is a
descriptive replication checklist whose only inferential component is H1's
rule applied to F2R. H4 is a screen with no α. There is no campaign-wide 5%
guarantee and none is claimed.

**H1 — the file reduces the closing invitation (judged `handoff`; T vs N0).**
Bakeoff 12's rule with threshold α/2. Per judge `j`: pass when `k_N0,j > 0`;
`rate_T(t) ≤ rate_N0(t)` on all four tasks and strictly lower on at least
three; `P_T ≤ 0.5 × P_N0`; the one-sided exact test stratified by task (the
treatment total against the convolution of per-task hypergeometrics given
the margins) gives `p ≤ α/2`; and the scanner's `offer_anywhere` count for T
does not exceed N0's (relocation). `supported` when both judges pass.
`refuted` when both judges show `P_T > P_N0` with the mirror-image increase
test at `p ≤ α/2`. Otherwise `indeterminate`, including a zero baseline,
judge disagreement, and small reductions. The same rule is applied to F2R
for H3.

**H2 — length (T vs N0; primary rows with `words > 0`).** Effect estimate:
the **geometric-mean ratio** `GMR = exp(mean over tasks of (mean log-words_T
− mean log-words_N0))`, tasks weighted equally. Test: permutation of arm
labels within each task (stratified), `B = 20,000`, seed 13,
`p = (extreme + 1) / (B + 1)` for each tail. Non-inferiority: `U` = the
one-sided 97.5% upper percentile-bootstrap bound of GMR (resample within
task and arm, 10,000 draws, seed 131). Any task cell with fewer than two
trials makes H2 `indeterminate (incomplete)` with `non_inferior` false.

- `shorter`: `GMR ≤ 0.90` and `p_lower ≤ α/2`.
- `longer`: `GMR ≥ 1.10` and `p_upper ≤ α/2`.
- otherwise `indeterminate` on direction.
- `non_inferior` (separate flag): `U < 1.10`.

Medians, per-task ratios, and the mean word difference are reported beside
GMR, descriptively. An `indeterminate` with `non_inferior` is read as "no
length harm detected at the 10% margin", never as "no cost". The same
estimate is computed for F2R (H3, H4) and, descriptively, F2R against G1.

**Power** (`notes/2026-09-05-bakeoff13-study/tools/h2_length_power.py` v2,
baseline resampled within task from S045's 32 N0 primary trials): the
`shorter` verdict fires 0.92 at ×0.85 and 1.00 at ×0.80; `longer` fires
0.99 at ×1.21 (F2's primary ratio) and 1.00 on the empirical F2 pattern;
a file that truly holds length (×1.00) is `non_inferior` 0.67 of the time
and produces a false directional verdict about 1% of the time; opposing
per-task effects (×1.30, ×1.30, ×0.75, ×0.75) pass non-inferiority 0.78 of
the time on GMR, which is why H4 adds a per-task cap. Eight observations
per task carry no information about future dispersion or response modes;
the table is conditional on N0's 2026-09-05 sample.

**H3 — F2 replicates (F2R vs N0), a descriptive checklist.** Components,
each with a fixed reference from S045: (a) H1's rule at α/2 passes for F2R
on both judges; (b) primary `GMR_F2R ≥ 1.10` (bakeoff 12 primary median
ratio 1.21; all-38 ratio 1.29); (c) coverage `incomplete` for F2R ≤ N0's on
all 38 trials, on both judges. Outcome: `replicated` when all three hold;
`not replicated (component …)` naming each failing component; `not
evaluable` when F2R or N0 is incomplete (below). Failure to reproduce a
component is a non-confirmation on this run, not a refutation of the
bakeoff 12 result. F2R vs G1 is reported descriptively: `handoff`, `aside`,
`result` counts per judge, GMR, verification-role words, and the frame
count.

**H4 — practical harm screen, per screened arm (F2R, G1, G2), over all 38
trials per arm unless stated.** Components: *oracle* — `indeterminate
(floor)` when N0 passes fewer than 13 of 38; `harm` when `o_T ≤ o_N0 − 2`.
*False completion* — `harm` on any rise in `claims_done_oracle_failed`,
either judge. *Check proxy* — `harm` when `no_python_command_after_last_edit`
rises by two or more, either judge. *Coverage* — `harm` when `incomplete`
rises by two or more, either judge, with the per-task missing items listed
from the judges' `excerpts`. *Inflation*, three parts reported separately:
primary `U ≥ 1.10` (H2's non-inferiority bound failing) → `harm`; controls
(6 trials) median ratio `> 1.10` → `harm (n = 6)`; any single primary task
median ratio `> 1.30` → `harm (task)`. Any `harm` → `refuted`; else
`indeterminate` if a floor fired or a part could not be computed; else
**`screen passed`**, which means no harm detected by these instruments.
Per-task oracle counts reported beside it.

**Completeness.** An arm is complete when every planned trial for it and
for N0 is recorded and neither arm has any censored (`timeout`, `budget`) or
harness-failed record, including records of trials later re-run. An
incomplete arm is `not evaluable` for adoption; its hypotheses are still
reported and labelled partial.

**Echo sensitivity.** H1 and H4 are recomputed with every echo-flagged
trial's judged labels set to the worst case for the arm (`handoff` → true;
coverage → `incomplete`) on both judges. If either verdict changes,
eligibility is withheld and both computations are reported.

**Eligible for adoption (standalone configuration):** H1 `supported`; H2 not
`longer` and `non_inferior`; H4 `screen passed`; complete; echo sensitivity
unchanged. H2 `shorter` is reported beside it as the shortening claim and is
not required. Reported for F2R, G1, and G2 alike; F2R is a replication arm,
not a candidate.

**How a null is read.** If G1 or G2 removes the invitation and is
non-inferior on length with the screen passed, it is eligible in the tested
configuration and the report says "no length harm detected", with the
descriptive set showing where the words sit. If it is `longer`, the role
allocation and per-task distributions say where the words went, as
allocation, not mechanism. If it is `shorter` but H4 refutes on coverage,
the report lists the must-cover items that went missing per task. A null on
direction with non-inferiority failing (`U ≥ 1.10`) is reported as
underpowered on that margin, not as harm.

**Descriptive set (no verdict reads it):** per-role word means per arm;
per-task word distributions (median, mean, 90th percentile, max); GMR and
median ratios; absolute word differences; upper-tail words; the chronology
of words by `started_utc` (dispatch index); cross-tabs of length with
coverage, oracle, closing label, and echo flag; `mean_sentence_words`,
`paragraphs`, `items`, `bold_leadins`, `headings`; the frame count; the
per-task list of must-cover items the judges marked missing; judge
agreement (kappa) and the scanner's agreement with the judged `handoff`.

## Stopping rule

Fixed counts: 128 and 24. No interim look at any outcome, no extension, no
substitute judge after labels exist. Harness-class failures: authentication,
model, or version drift stop the run on the first trial; other harness kinds
stop it above 10% of planned trials. Censoring (`timeout` 1200 s, `budget`
$3.00) has its own ceiling of 25%; below it the run continues and is
resumable; censoring is reported per arm and makes the affected arm
incomplete. No deadline is declared; a run stopped for any reason is graded
with `grade-partial` and reported as partial, complete repetition blocks
only.

## Environment freeze

Identical to bakeoff 12's (`../clause-bakeoff-12-2026-09-05/protocol.md`,
"Environment freeze"), for both declarations: adapter `claude-code/2`;
pinned binary `~/.claude-eval-pins/bakeoff10/claude` = `2.1.258 (Claude
Code)` sha `b63136194160…`, version checked per trial; Opus 5, effort high;
tools `Bash, Read, Edit, Write, Grep, Glob`; `acceptEdits`;
`Bash(python3 *)`; the permitted `python3` (Homebrew 3.14.5 by real path)
through the per-trial `sandbox-exec` shim; allow-listed child environment;
workspace a fresh temp directory outside `$HOME` and the repository; budget
$3.00; timeout 1200 s; three workers; `--setting-sources project`,
`autoMemoryEnabled: false`, no MCP, no session persistence. **N0** is an
`absent = true` variant: the harness copies no file, asserts no `CLAUDE.md`
at the start, and fails the trial as `environment` if one exists at the end.
`claude_md_referenced` is reported per arm. The harness itself changed
since bakeoff 12 by the `dispatch_seed` addition only (sealed as
`harness_sha256` in each plan).

Isolation limitation: the user-level `~/.claude/CLAUDE.md` is excluded by
`--setting-sources project` (documented behaviour; S001) and the workspace is
outside `$HOME`, but no marker can be planted in James's file to prove the
user source is absent from either arm.

## Dispatch and authorization

```bash
C=campaigns/clause-bakeoff-13-2026-09-06
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

**Authorization.** James's review comments of 2026-09-06 on
`notes/2026-09-05-bakeoff13-study/05-candidates-for-james.md` approved G1,
G2, F2R, route (a), the unchanged probe set and instruments with no pilot,
and GA deferred; his accompanying message read, verbatim: "Notes added.
Approved for runs." The chair records this in each declaration's
`clause-run-authorization/1` file naming the plan hash printed by `check`.
Judging is part of the same authorization.

## Limitations, stated now

- One model, one binary, six Python-stdlib tasks, one operator, one day; the
  four primary tasks were selected from bakeoff 11 as the ones that provoke
  the construct; the length claim generalises within this battery and no
  further.
- The tested configuration is a standalone file; the deployed-file question
  is untested, and G2's one-sentence consequence cap would sit beside a ban
  in James's file if ever appended there.
- The judged construct is uncalibrated against a human; `words` treats code
  as prose; the role decomposition is a keyword heuristic.
- Cost and duration are cache-confounded and never read as arm effects.
- H4 passing is a declared screen, not evidence of no harm; a truly
  length-neutral file passes non-inferiority about two thirds of the time.
- G1 versus F2R isolates one edit that changes content and size together;
  it does not separate the two.

## Verification contract

`python3 -m unittest discover -s tests` exit 0 from the root;
`python3 fixtures/validate.py` from this directory, `6 probes, 0 problems`;
`clause_campaign.py check` on both declarations; after the run, `verify` on
both run directories and `clause_judge.py verify` for both judges on both.
