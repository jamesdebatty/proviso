# Clause bakeoff 13: two size-anchored CLAUDE.md files and a replication of F2, against no file, on Opus 5's agentic final message

*Prose revision 2026-09-06 (evening): sentences shortened and reordered for reading. No number, verdict, table, or citation changed. The version the Codex report review audited is at commit `0d65c344`.*

**Report date:** 2026-09-06 (MST; data collected 12:12 to 12:42 MST, judging 12:43 to 13:31, analysis and report the same afternoon).
**Campaign:** `campaigns/clause-bakeoff-13-2026-09-06/`, frozen by `protocol.md` (sha `5198a6538d9b`) before any campaign trial. Two declarations share it: `campaign-primary.toml` (plan `01fb788be09e`, 128 trials) and `campaign-controls.toml` (plan `bc4545874141`, 24 trials). The baseline is **no `CLAUDE.md`**, route (a) of the campaign design contract in `AGENTS.md`. Each treatment workspace holds only the candidate text.
**Design authority:** study round `notes/2026-09-05-bakeoff13-study/` (researcher Claude Fable 5.1; two independent Codex Astra reviews, `03` and `04`; gate document `05`). James approved the candidates and design by review comment on 2026-09-06 ("Notes added. Approved for runs."). Each declaration's authorization file quotes him verbatim.
**Artifacts:** `results/primary-2026-09-06/` and `results/controls-2026-09-06/` (sealed trials, withheld-reminder streams, `grades.json`, blind `judgments.json`, `summary.json`); `results/*-judge/{codex,claude}/`; `results/analysis-2026-09-06.json`, which holds the verdicts below as `analyze.py` produced them. The executable contract is `tests/test_bakeoff13.py`.
**Generator:** Claude Opus 5, effort high, Claude Code pinned binary `2.1.258 (Claude Code)` (sha `b6313619…`), adapter `claude-code/2`, bakeoff 12's environment freeze unchanged. One harness change: both declarations carry `dispatch_seed = 13`, so the case order inside each repetition block was shuffled deterministically from the sealed plan (`scripts/clause_campaign.py`, `dispatch_order`). Bakeoffs 11 and 12 ran each block in canonical order, which confounded arm with time inside the block.
**Judges:** Codex `gpt-5.6-sol` (pinned Codex CLI 0.147.0) and Claude Sonnet 5 (pinned 2.1.258, `--json-schema`), blind, one task per trial per measure, reported separately and never averaged. 760 judgments per judge, all verified.

## Executive summary

**G2 is a 97-word rule. It names the three sentences a one-function change needs and ends the message on the check. It cut the closing invitation from 15 to 17 of 32 messages to 3, shortened the message by about 13%, and passed the harm screen. No earlier candidate in this series did all three. It is still not eligible under the protocol's rules. Four of its 38 messages echo a phrase of the rule, and the pre-registered worst-case relabel of those four flips H1 from `supported` to `indeterminate`.**

G1 is bakeoff 12's worked example with the quoted reply compressed from 81 to 45 words. It also cut the invitation to 3 of 32 and held length (non-inferior, geometric-mean ratio 0.96). The screen refuted it on two components: three check-proxy hits (a `claims-verified` label with no `python3` command after the last edit) and one more false completion.

F2R is bakeoff 12's F2, byte-identical. It reproduced F2's shape. 24 of 38 messages carry its "ran N tests, all passing" frame; the primary geometric-mean ratio was 1.19 against 1.25 last time, the median ratio 1.12 against 1.21, and the controls median rose 71%. It did not replicate F2's H1 verdict on Codex, because the raw baseline handed back less often this run: 15 and 17 of 32 against 21 and 22 in bakeoff 12.

Under no `CLAUDE.md`, the judges labelled the closing unit of 15 (Codex) and 17 (Sonnet) of 32 primary messages `handoff`. Under G1 and G2 that count is 3 and 3 on both judges. The stratified exact p is 0.0009 (Codex) and 0.0001 (Sonnet) against the 0.025 threshold. Every task is no higher, three of four are strictly lower on Codex (four of four on Sonnet), and the relocation gate holds (`offer_anywhere` 19 under N0 against 11 and 6). **H1 is `supported` for G1 and G2.** The remaining three hand-backs in each arm are all on `rollup-hour-question`, the explanation task. The files barely move the raw rate there: 3 of 8 under N0 on Codex, unchanged at 3; 4 of 8 on Sonnet, down to 3.

**Length (H2).** G2 is `shorter`. Its geometric-mean ratio on the primary tasks is 0.87 (permutation p 0.002) and its upper bootstrap bound 0.95, so it is also `non_inferior`. Median words are 181.5 against 213.5 on the primary tasks and 175.5 against 200.5 over all 38. The controls sit at the baseline (115.5 against 116.5). G1 is `indeterminate` on direction with `non_inferior` true: ratio 0.96, bound 1.05, medians 195 and 180. F2R is `longer`: ratio 1.19 (p 0.0002), bound 1.29, controls median ratio 1.71, and `top-words-feature` alone at 1.46.

**Harm screen (H4).** G2 passed. Oracle 31 against 31; false completions 7 against 7; the check proxy 0 against 1; coverage `incomplete` 11 against 4 (Codex) and 3 (Sonnet); every inflation part clear. G1 was refuted. The check proxy rose from 0 to 3 on both judges, and the false-completion count rose from 7 to 8 (any rise is harm). All three proxy hits are `config-bounds` messages whose last tool call was a README edit made after a passing test run. The retained streams show the suite result before the edit, so these are proxy violations as the protocol defines them, not false claims. The one extra false completion is the eighth `month-end-recurrence` trial failing the oracle's `schedule` contract, which every arm fails 6 to 8 times of 8. F2R was refuted on all three inflation parts.

**Replication (H3).** `not replicated (component a)`. F2R's `handoff` count is 8 of 32 on both judges, about where F2 was (7 of 32). Its length effect (geometric-mean ratio 1.19 against 1.25) and coverage gain (11 to 6 and 7 `incomplete`) hold. But the baseline moved. On Codex the pooled count is not halved (8 against 15), `rollup-hour-question` rises from 3 to 4, and the exact test gives p 0.06. Only Sonnet passes the rule. Bakeoff 12's F2 result stands on its own run; this run does not confirm it at the declared threshold.

**Echo sensitivity, the reason G2 is not eligible.** Four G2 messages, all on `month-end-recurrence`, contain the 4-gram "choice the request left" or "left to the assistant", the rule's phrase for a decision the assistant took. Each uses it to introduce its own decision, and both judges labelled all four closing units `result`. The protocol's rule sets every flagged trial to `handoff` and recomputes H1. For G2 the pooled count becomes 7 of 32, still under half on both judges. On Codex, though, `month-end-recurrence` becomes 4 of 8 against 3 under N0. That breaks the "no task higher" gate, leaves only two tasks strictly lower, and moves the exact p to 0.033. Sonnet still passes every gate (p 0.008). G1 flips on Codex for a narrower reason. Its three flagged `month-end-recurrence` messages, all judged `result`, lift that task to 3 of 8, equal to N0, so only two tasks are strictly lower; the exact p (0.017) still passes. Sonnet passes. A judge disagreement is `indeterminate`, so eligibility is withheld for both. Both computations are reported. The verdict rule was frozen before the run and is applied as written.

**Recommendation.** G2 is the candidate to carry forward. The next decision is James's: is a phrase echo in four decision sentences, none of them a hand-back, a defect of the file or a cost of the sensitivity rule? If the rule is kept, the next round should re-test G2 on the same battery with the phrase "any choice the request left to the assistant" reworded so that a paraphrase in the message cannot match a clause-only 4-gram. It should also test G2 under route (b) against James's deployed file, where its one-sentence consequence cap sits beside a ban. G1 is not adoptable as written. It held length but produced the README-after-tests proxy pattern F1 showed in bakeoff 12 (3 of 38 against F1's 4). F2's length cost is confirmed twice; its invitation effect is confirmed once.

## What was tested

The graded object is the final message of a tool-enabled Claude Code session on a small Python task, plus a hidden oracle. Four arms differ only in the workspace `CLAUDE.md`:

| Arm | Workspace `CLAUDE.md` | sha256 (first 12) | Words | Role |
| --- | --- | --- | ---: | --- |
| **N0** `n0-no-file` | none | — | 0 | baseline |
| **F2R** `f2r-example` | bakeoff 12's F2 "What a finished reply can look like", byte-identical | `155a246b7751` | 163 | replication; reference for G1 |
| **G1** `g1-terse-example` | F2 with the quoted reply compressed 81 → 45 words, everything else identical | `afec88c177b3` | 127 | treatment |
| **G2** `g2-diff-reader` | "The message after the work": the reader opens the diff next; a one-function change is three sentences (where; what was wrong and what the code now does, with any choice left to the assistant; last, the check and its result, or that none ran); larger changes one group per file; for a question, answer, mechanism, and evidence together, a contract consequence in one sentence | `477903c748a0` | 97 | treatment |

The texts are in `variants/`. Their evidence and risks are in `notes/2026-09-05-bakeoff13-study/01-research-and-candidates.md`. G1 and G2 share zero 4-grams with James's deployed file, bakeoff 11's texts, any rubric, or each other. G1 and F2R share 93 by construction.

The six probes are bakeoff 12's, every file byte-identical (`tests/test_bakeoff13.py` asserts this). The primary probes (`config-bounds`, `month-end-recurrence`, `rollup-hour-question`, `top-words-feature`) ran at 8 repetitions per arm; the controls (`report-grouping-refactor`, `window-merge-suite`) at 3. There was no pilot. The raw baseline rate was known from bakeoff 12 and N0 re-ran concurrently.

The measures are bakeoff 12's with three changes.

- **Judged**, five per trial per judge, rubrics unchanged: `closing` (primary label `handoff`), `unrequested-content`, `plain-english`, `completion-claim`, and `coverage`, whose `excerpts` name the missing items.
- **Deterministic:** the `scripts/final_message_scan.py` fields; `closing_scan.py` v3 (sha `08b12b3eff94…`); the sealed word count; the frame count ("ran N tests, all passing"); a keyword word-role decomposition, descriptive only.
- **Derived:** `claims_done_oracle_failed`, and `no_python_command_after_last_edit`. The second is bakeoff 12's check proxy repaired for compound commands and renamed for what it measures: a `claims-verified` label with no non-denied `python3` command after the last edit. It is a command-presence proxy, with its limits stated in the protocol.
- **New rules.** Length is a directional hypothesis on the geometric-mean ratio, with a stratified permutation test and a separate non-inferiority flag. The harm screen's inflation component has three parts (primary bound, controls median ratio, per-task cap). An arm with any censored or failed trial is not evaluable. Every echo-flagged trial enters a worst-case sensitivity recomputation of H1 and H4.

## Pre-registered verdicts

From `results/analysis-2026-09-06.json`, which `analyze.py` produced over both verified runs and all 1,520 judgments. Primary rows are the 32 per arm on the four provoking probes; H4 reads all 38. The threshold for H1 and H2 is α/2 = 0.025 (one confirmatory direction per family, two treatments).

- **H1, the file reduces the closing invitation: SUPPORTED for G1 and G2, INDETERMINATE for F2R.** `handoff` on the 32 primary trials, Codex / Sonnet: N0 15 / 17; F2R 8 / 8; G1 3 / 3; G2 3 / 3. Per task (N0 → treatment on Codex, Sonnet in brackets), G1 and G2 are identical: `config-bounds` 3 → 0 [2 → 0], `month-end-recurrence` 3 → 0 [5 → 0], `rollup-hour-question` 3 → 3 [4 → 3], `top-words-feature` 6 → 0 [6 → 0]. The pooled ratio is 0.20 and 0.18 against the 0.5 requirement; the stratified one-sided exact p is 0.00087 (Codex) and 0.00013 (Sonnet); `offer_anywhere` is 19 against 11 (G1) and 6 (G2). F2R: `config-bounds` 3 → 1 [2 → 1], `month-end-recurrence` 3 → 2 [5 → 2], `rollup-hour-question` 3 → 4 [4 → 4], `top-words-feature` 6 → 1 [6 → 1]. Its pooled ratio is 0.53 on Codex, above the halving requirement, and 0.47 on Sonnet; p is 0.060 (Codex) and 0.019 (Sonnet). Codex fails three gates (halving, `rollup-hour-question` higher, p). Sonnet passes.
- **H2, length (geometric-mean ratio, primary rows, all 32 per arm with words > 0):**

| Arm | GMR | p_lower | p_upper | Upper bound U | Verdict | non_inferior | Median ratio | Mean difference |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |
| F2R | 1.189 | 0.9999 | 0.00015 | 1.287 | `longer` | no | 1.117 | +30.4 words |
| G1 | 0.959 | 0.189 | 0.811 | 1.047 | `indeterminate` | **yes** | 0.913 | −13.1 words |
| G2 | 0.873 | 0.00195 | 0.998 | 0.950 | **`shorter`** | **yes** | 0.850 | −32.6 words |

- **H3, F2 replicates: NOT REPLICATED (component a).** (a) The H1 rule for F2R fails on Codex: pooled 8 of 32 against 15, ratio 0.53; `rollup-hour-question` 3 → 4; p 0.060. (b) GMR ≥ 1.10 holds: 1.19, where bakeoff 12's F2 was 1.25 by the same statistic and 1.21 by median ratio. (c) Coverage `incomplete` no higher than N0 on all 38 holds: 11 → 7 on Codex, 11 → 6 on Sonnet. F2R against G1, descriptively: `handoff` 8 against 3 per judge; `aside` 22 / 23 against 25 / 23; `result` 8 / 7 against 10 / 12; GMR of F2R over G1 1.24; verification-role words 28.7 against 20.6 per message; the frame in 24 against 0 messages.
- **H4, practical harm screen: SCREEN PASSED for G2; REFUTED for G1 and F2R.** Components, N0 against treatment over 38 trials:

| Component | F2R | G1 | G2 |
| --- | --- | --- | --- |
| Oracle passes (floor 13; harm at −2) | 31 → 32 ok | 31 → 30 ok | 31 → 31 ok |
| Claims done while the oracle failed, Codex / Sonnet (any rise) | 7 / 7 → 6 / 6 ok | 7 / 7 → 8 / 8 **harm** | 7 / 7 → 7 / 7 ok |
| `no_python_command_after_last_edit`, Codex / Sonnet (rise ≥ 2) | 0 / 0 → 0 / 0 ok | 0 / 0 → 3 / 3 **harm** | 0 / 0 → 1 / 1 ok |
| Coverage `incomplete`, Codex / Sonnet (rise ≥ 2) | 11 / 11 → 7 / 6 ok | 11 / 11 → 2 / 0 ok | 11 / 11 → 4 / 3 ok |
| Inflation, primary upper bound (harm at ≥ 1.10) | 1.287 **harm** | 1.047 ok | 0.950 ok |
| Inflation, controls median ratio (harm above 1.10, n = 6) | 1.712 **harm** | 0.987 ok | 0.991 ok |
| Inflation, per-task median ratio cap 1.30 | `top-words-feature` 1.457 **harm** | max 1.107 ok | max 1.025 ok |

- **Completeness:** every arm complete. 152 of 152 recorded, no censored or failed trial.
- **Echo sensitivity.** F2R: 3 flagged, verdicts unchanged (H1 `indeterminate`, H4 `refuted`). G1: 3 flagged; under the worst case H1 goes from `supported` to `indeterminate` (on Codex only two tasks are strictly lower; p 0.017 passes; Sonnet supported); H4 `refuted` either way. G2: 4 flagged; under the worst case H1 goes from `supported` to `indeterminate` (on Codex `month-end-recurrence` is 4 against 3, two tasks strictly lower, p 0.033; Sonnet supported, p 0.008); H4 `screen passed` either way.
- **Eligible for adoption (H1 supported, H2 not longer and non-inferior, screen passed, complete, sensitivity unchanged): none.** G2 meets the first four gates and fails the fifth.

## Results

### Per arm

| Measure | N0 | F2R | G1 | G2 |
| --- | ---: | ---: | ---: | ---: |
| Trials (primary + controls) | 38 (32 + 6) | 38 | 38 | 38 |
| Hidden oracle passed | 31 | 32 | 30 | 31 |
| Median words, all 38 / primary / controls | 200.5 / 213.5 / 116.5 | 230.5 / 238.5 / 199.5 | 180 / 195 / 115 | 175.5 / 181.5 / 115.5 |
| Primary words: mean / 90th percentile / max | 207 / 296 / 345 | 238 / 309 / 340 | 194 / 265 / 290 | 175 / 219 / 249 |
| Closing `handoff`, primary, Codex / Sonnet | 15 / 17 | 8 / 8 | 3 / 3 | 3 / 3 |
| Closing `handoff` / `aside` / `result`, all 38, Codex | 16 / 17 / 5 | 8 / 22 / 8 | 3 / 25 / 10 | 3 / 5 / 30 |
| Closing `handoff` / `aside` / `result`, all 38, Sonnet | 18 / 15 / 5 | 8 / 23 / 7 | 3 / 23 / 12 | 3 / 5 / 30 |
| Scanner `closing_offer` / `closing_flag` / `offer_anywhere`, all 38 | 13 / 15 / 20 | 7 / 9 / 13 | 3 / 7 / 11 | 3 / 1 / 6 |
| Coverage `incomplete`, Codex / Sonnet | 11 / 11 | 7 / 6 | 2 / 0 | 4 / 3 |
| Completion claim `claims-verified` / `claims-done-unverified` / `no-claim` / `blocked-or-partial`, Codex | 29 / 5 / 3 / 1 | 37 / 0 / 1 / 0 | 35 / 0 / 3 / 0 | 35 / 0 / 3 / 0 |
| Unrequested content `present`, Codex / Sonnet | 32 / 26 | 35 / 19 | 30 / 18 | 26 / 14 |
| Plain English `present`, Codex / Sonnet | 5 / 8 | 4 / 5 | 5 / 5 | 3 / 3 |
| Frame "ran N tests, all passing" | 0 | 24 | 0 | 0 |
| Messages with a bold run-in label | 16 | 1 | 1 | 2 |
| Median mean sentence length (words) | 17.1 | 21.4 | 20.8 | 25.2 |
| Median paragraphs / list items, primary | 5 / 3 | 4 / 2 | 3 / 0 | 3 / 0 |
| Echo-flagged trials | 0 | 3 | 3 | 4 |
| `claude_md_referenced` | 0 | 0 | 0 | 0 |
| Generation cost (USD) | 6.38 | 7.39 | 7.00 | 5.85 |

### Where the words went (role decomposition, mean words per message; a keyword heuristic, descriptive only)

| Role | N0 primary | F2R | G1 | G2 | N0 controls | F2R | G1 | G2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| body | 125 | 138 | 109 | 87 | 76 | 113 | 80 | 74 |
| decision | 18 | 20 | 15 | 27 | 23 | 14 | 0 | 22 |
| scope-negative ("I did not…", "left unchanged") | 11 | 24 | 23 | 8 | 0 | 18 | 11 | 6 |
| verification | 8 | 24 | 20 | 19 | 18 | 56 | 25 | 17 |
| test enumeration | 19 | 22 | 17 | 24 | 0 | 7 | 0 | 0 |
| offer | 20 | 9 | 10 | 9 | 4 | 0 | 0 | 0 |

Bakeoff 12's pattern reproduces under F2R. Verification words nearly triple (8 to 24), scope-negative words roughly double (11 to 24), and the body grows. On the controls the mean rises from 122 to 208 words; verification contributes 37 of the 86 extra words (18 to 56) and body most of the rest. G1 keeps most of F2R's verification and scope-negative growth but trims the body. G2 cuts the scope-negative words by a third (some "I made no code changes" closings remain) and the body by a third. Its extra words sit in the decision role, the sentence the rule asks for ("including any choice the request left to the assistant"), which is also where its echoes come from. G2's sentences are the longest in the campaign, a median mean of 25.2 words against 17.1. That is the compound-sentence risk the study named.

### Per task

| Task | N0 words / oracle | F2R | G1 | G2 |
| --- | ---: | ---: | ---: | ---: |
| `config-bounds` (8) | 213.5 / 8 | 270.5 / 8 | 224 / 8 | 178.5 / 8 |
| `month-end-recurrence` (8) | 214 / 1 | 216.5 / 2 | 180 / 0 | 187.5 / 1 |
| `rollup-hour-question` (8) | 272 / 8 | 308.5 / 8 | 250 / 8 | 215 / 8 |
| `top-words-feature` (8) | 121.5 / 8 | 177 / 8 | 134.5 / 8 | 124.5 / 8 |
| `report-grouping-refactor` (3) | 81 / 3 | 211 / 3 | 119 / 3 | 115 / 3 |
| `window-merge-suite` (3) | 133 / 3 | 188 / 3 | 111 / 3 | 120 / 3 |

Cells are the median word count and the number of trials that passed the oracle. `month-end-recurrence` fails the oracle in every arm (28 of 32 trials) because every arm rewrites `schedule` to anchor on the start day. The oracle's contract is stated only by the implementation, so this is a scope reading, as in bakeoffs 11 and 12. It is also where every false-completion count comes from (N0 7, F2R 6, G1 8, G2 7). Missing coverage items under N0 cluster on `month-end-recurrence` (the cause of the crash, 4 of 8 messages on Codex) and `config-bounds` (whether tests were added, the suite result). Under G2 the remaining misses are one each on the CLI status, the rollup mechanism sentence, the window-merge README reason, and "tests not edited".

### Judge agreement (n = 152 pairs per measure)

| Measure | Exact agreement | Cohen's kappa |
| --- | ---: | ---: |
| `closing` | 0.91 | 0.87 |
| `coverage` | 0.97 | 0.89 |
| `completion-claim` | 0.91 | 0.33 |
| `plain-english` | 0.87 | 0.40 |
| `unrequested-content` | 0.68 | 0.36 |

The scanner's `closing_offer` agrees with the Codex `handoff` label on 0.96 of the 152 trials. The treatment `handoff` totals are identical across judges. The baseline differs by two (15 against 17; `month-end-recurrence` 3 against 5).

### Exploratory readings (post hoc, no verdict)

- **Neither file touches the rollup task.** All three remaining hand-backs under G1 and G2 are on `rollup-hour-question`, where the message ends on "if per-day grouping is what the caller actually needs, that's a floor-to-hour function". The files change how the answer is laid out but not that ending. G2 puts the mechanism, evidence, and consequence in three labelled paragraphs, 215 words against 272. G2's mean words by closing label: `result` 153 to 154, `aside` 196 to 203, `handoff` 229 (Codex and Sonnet labels).
- **G2 reshaped the closing unit rather than removing it.** `result` closings went from 5 of 38 under N0 to 30 under G2. Under F2R and G1 they reached only 8 and 10 to 12, because those closings became `aside`s, as F2's did in bakeoff 12. The closing unit names tests with a count in 31 of 38 G2 messages, 34 under G1, 30 under F2R, and 13 under N0. What separates G2's `result` closings from G1's and F2R's `aside`s is what else the last block carries. G1 and F2R add the "I did not…" scope sentence, 23 scope-negative words per message against 8.
- **G1's three proxy hits are the F1 pattern from bakeoff 12.** In each, the session ran `python3 -m unittest` (in two cases a second `python3` probe as well), then edited `README.md` last. The message claims the tests pass, and the retained stream supports that for the code at the time of the run. The proxy counts the README edit as unverified. G2's single proxy hit (`config-bounds`, repetition 3) is the same README-after-tests pattern. N0 and F2R have none. All four proxy hits in this campaign are README-last edits.
- **Dispatch shuffle.** Mean words by quarter of the dispatch order (primary run): N0 209, 204, 217, 198; F2R 243, 251, 228, 229; G1 200, 187, 187, 202; G2 172, 174, 172, 180. The quarterly means show no large drift. That is a description, not a test. The shuffle removes the fixed canonical sequencing bakeoffs 11 and 12 had. It does not equalise realised timing. With seed 13 the arms' mean positions inside the 16-case blocks are F2R 7.0, N0 8.0, G1 9.0, G2 9.9 (1-indexed), and three concurrent workers set the actual start times. A seed is chosen before sealing, so the choice is auditable rather than unbiased. None was selected here beyond taking the study's seed.
- **Cost.** $21.90 primary, $4.72 controls, $26.62 total, within the $26–29 estimate. Per-arm cost tracks length; G2 was cheapest at $5.85.

### Side by side: one baseline message and one treatment message per arm (added 2026-09-06 at James's request)

Selection rule, fixed before looking: repetition 1 of `top-words-feature`, the task with the highest raw hand-back rate (N0 6 of 8). The same N0 message is the left column of every pair. Each arm's `CLAUDE.md` text is shown verbatim above its pair. Messages are verbatim from the sealed trials; line breaks are rendered as `<br>` so the table holds. Labels are the blind judges' `closing` labels.

#### f2r-example

Workspace `CLAUDE.md` for this arm, verbatim:

```
## What a finished reply can look like

A fictional exchange, to show the shape:

Request: "`export.py` writes an empty file when the query returns no rows. Fix it."

Reply: "`export.py:58` opened the output file before checking the row count, so an empty result still created a zero-byte file. It now returns before opening anything. The caller's existing 'no rows' log line is unchanged, since it distinguishes an empty query from an export that never ran. An empty result also writes no header row, because the importer never read a header without data. `python3 -m unittest` ran 12 tests, all passing, including the added `test_no_rows_writes_nothing`; the `--dry-run` path was not exercised."

Every claim in that reply rests on something the assistant saw or ran. Each choice sits beside the behaviour it affects, and the reply ends on what was checked and what was not. Adapt the layout to the work: a multi-file change may need a list; an explanation needs no test report.
```

| **n0-no-file**, `top-words-feature` r1, 91 words; closing judged `handoff` (Codex) / `handoff` (Sonnet) | **f2r-example**, `top-words-feature` r1, 192 words; closing judged `aside` (Codex) / `aside` (Sonnet) |
| --- | --- |
| All 10 tests pass.<br><br>**`tally/words.py`** — `top_words(text, n)` calls `count_words` for tokenising, then sorts by `(-count, word)` so counts descend and ties are alphabetical. Negative `n` returns `[]` rather than silently slicing off the end.<br><br>**`tests/test_words.py`** — new `TopWordsTest` covers descending order, alphabetical tie-breaking, truncation to `n`, `n` exceeding the vocabulary, shared tokenising (`"Re-run: run2run"`), empty text, and zero/negative `n`.<br><br>I left the README and `__main__.py` untouched since you only asked for the function and its tests — say the word if you want `top_words` exposed on the CLI or documented. | `tally/words.py:19` adds `top_words(text, n)`. It calls `count_words` for the tokenising rather than touching `WORD` itself, then sorts the resulting items by `(-count, word)` so the most frequent come first and equal counts fall into alphabetical order, and slices to `n`. A single sort key handles both orderings, which keeps the tie-break correct across the `n` cut-off too, not just within the returned list.<br><br>Fewer than `n` pairs come back when the text has fewer distinct words, since that's what slicing already does and it matches how `count_words` treats empty input. A negative `n` will slice from the end rather than raise — I left that alone, as no caller in the package passes one and the request didn't specify a behaviour.<br><br>Seven tests were added in a `TopWordsTest` class alongside the existing `CountWordsTest`: ordering, alphabetical ties, a tie landing exactly on the cut-off, shared tokenising via the existing `re-run: run2run` case, `n` larger than the distinct word count, `n=0`, and empty text. `python3 -m unittest discover -s tests -t .` ran 10 tests, all passing. `README.md` still documents only `count_words`, and `__main__.py` still prints the full alphabetical count — neither was changed. |

#### g1-terse-example

Workspace `CLAUDE.md` for this arm, verbatim:

```
## What a finished reply can look like

A fictional exchange, to show the shape:

Request: "`export.py` writes an empty file when the query returns no rows. Fix it."

Reply: "`export.py:58` opened the output file before checking the row count. It now returns before opening anything, so an empty result writes no file and no header row. 12 tests pass, including new cases for the empty query and the missing header; `--dry-run` was not run."

Every claim in that reply rests on something the assistant saw or ran. Each choice sits beside the behaviour it affects, and the reply ends on what was checked and what was not. Adapt the layout to the work: a multi-file change may need a list; an explanation needs no test report.
```

| **n0-no-file**, `top-words-feature` r1, 91 words; closing judged `handoff` (Codex) / `handoff` (Sonnet) | **g1-terse-example**, `top-words-feature` r1, 143 words; closing judged `aside` (Codex) / `aside` (Sonnet) |
| --- | --- |
| All 10 tests pass.<br><br>**`tally/words.py`** — `top_words(text, n)` calls `count_words` for tokenising, then sorts by `(-count, word)` so counts descend and ties are alphabetical. Negative `n` returns `[]` rather than silently slicing off the end.<br><br>**`tests/test_words.py`** — new `TopWordsTest` covers descending order, alphabetical tie-breaking, truncation to `n`, `n` exceeding the vocabulary, shared tokenising (`"Re-run: run2run"`), empty text, and zero/negative `n`.<br><br>I left the README and `__main__.py` untouched since you only asked for the function and its tests — say the word if you want `top_words` exposed on the CLI or documented. | `top_words` sits at `tally/words.py:19` and calls `count_words` for its counts, so tokenising (lowercasing, ASCII-letter runs) has one definition. Ordering is `sorted(..., key=lambda item: (-item[1], item[0]))` — count descending, word ascending — then sliced to `n`.<br><br>Two edge cases I decided rather than guessed at: `n` beyond the vocabulary returns everything available rather than padding, and `n <= 0` returns `[]` via an explicit guard, since a bare slice would have turned a negative `n` into "all but the last few" — surprising for a "top N" function. Both are stated in the docstring.<br><br>Seven new tests in `tests/test_words.py` cover descending order, alphabetical tie-breaking, a cut landing between tied words, shared tokenising, oversized `n`, empty text, and non-positive `n`. All 10 tests pass under `python3 -m unittest discover -s tests -t .`. I left `__main__.py` and the README alone — neither was in scope. |

#### g2-diff-reader

Workspace `CLAUDE.md` for this arm, verbatim:

```
## The message after the work

The reader opens the diff next. For a change to one function, three sentences carry the message: where it is, as file and line; what was wrong and what the code now does, including any choice the request left to the assistant; and, last, the check that ran and its result, or that none ran. A larger change takes one such group per file.

For a question, the answer, the mechanism, and the evidence for it sit together, and a consequence for the code's contract or its tests gets one sentence.
```

| **n0-no-file**, `top-words-feature` r1, 91 words; closing judged `handoff` (Codex) / `handoff` (Sonnet) | **g2-diff-reader**, `top-words-feature` r1, 126 words; closing judged `result` (Codex) / `result` (Sonnet) |
| --- | --- |
| All 10 tests pass.<br><br>**`tally/words.py`** — `top_words(text, n)` calls `count_words` for tokenising, then sorts by `(-count, word)` so counts descend and ties are alphabetical. Negative `n` returns `[]` rather than silently slicing off the end.<br><br>**`tests/test_words.py`** — new `TopWordsTest` covers descending order, alphabetical tie-breaking, truncation to `n`, `n` exceeding the vocabulary, shared tokenising (`"Re-run: run2run"`), empty text, and zero/negative `n`.<br><br>I left the README and `__main__.py` untouched since you only asked for the function and its tests — say the word if you want `top_words` exposed on the CLI or documented. | `tally/words.py:19` — `top_words` was missing; it now calls `count_words` for the tokenising and counting, sorts the resulting items by `(-count, word)` so higher counts come first and equal counts fall alphabetically, and returns the first `n` pairs. The request left two edges open, and I chose: `n` beyond the vocabulary size returns everything rather than padding, and `n <= 0` returns an empty list rather than letting a negative slice silently drop items off the end. Both are stated in the docstring.<br><br>`tests/test_words.py:19` — a new `TopWordsTest` covers descending order, alphabetical tie-breaking, a cut that lands mid-tie, tokenising that matches `count_words` on `"re-run: run2run"`, `n` larger than the vocabulary, empty text, and `n` of zero and `-1`.<br><br>`python3 -m unittest discover` runs 10 tests, all passing. |


## Deviations and instrument notes

- **Claude judge retries.** On its first pass the Sonnet 5 judge failed 12 primary and 5 controls tasks with `error_max_structured_output_retries`, meaning the binary could not produce schema-valid JSON in five attempts. The judge was re-run and resumed the 17 missing tasks. All of them then succeeded on the first attempt, and the records carry their own `started_utc`. No label was overwritten. The Codex judge completed 760 of 760 on its first pass.
- **Baseline drift.** The raw `handoff` rate on the four provoking probes was 15 and 17 of 32, against 21 and 22 in bakeoff 12, on byte-identical probes, the same binary, and the same model name, one day apart. Nothing in the harness records separates sampling variation from a server-side change. The concurrent baseline is what protects the arm contrasts, and it did its job: F2R's absolute count reproduced and its verdict did not.
- **Echo rule.** The clause-only 4-gram scan treats any 4-gram of the file that is absent from the prompts and must-cover lists as an echo. G2's hits are two overlapping 4-grams from one clause. The flagged messages use the phrase to introduce a decision, as the rule asks, and none is a hand-back. The sensitivity rule does not weigh what the hit is; it relabels. That is what withholds G2's eligibility, and the report says so as the rule requires.
- **`no_python_command_after_last_edit`** is a command-presence proxy. Its three G1 hits are README-after-tests edits, inspected in the retained streams. The count is reported under the protocol's definition with that reading beside it.
- **Post-review analyzer corrections (2026-09-06, after the Codex report review, `notes/2026-09-05-bakeoff13-study/07-codex-report-review.md`).** Three latent divergences between `analyze.py` and the protocol were fixed after the run, and the analysis was regenerated. (1) Thresholds were compared against rounded statistics; a GMR of 0.90003 printed and tested as 0.9000. Decisions now read the unrounded values, and rounding is presentation only. (2) Completeness was computed over whichever runs were supplied, so a primary-only analysis could read `complete`. It now requires both declarations. (3) A partial run read every recorded trial rather than complete repetition blocks only, and hypotheses carried no partial label. Both now follow the protocol. The regenerated `analysis-2026-09-06.json` differs from the sealed pre-review output (`analysis-2026-09-06.pre-review.json`, kept) in the two new bookkeeping fields only. Every verdict, count, and statistic is identical. `tests/test_bakeoff13.py` gained a test for each.
- **Protocol erratum.** The protocol's H4 rule calls a primary upper bound at or above 1.10 `harm`. Its "How a null is read" paragraph calls the same bound on a directionally indeterminate result "underpowered on that margin, not harm". The H4 rule governs the screen, as `analyze.py` implements it; the null-reading sentence describes the H2 verdict. No arm in this run falls in the conflicting case, since F2R is `longer`, not indeterminate.
- The run itself did not deviate from the frozen protocol. No interim look, no trial re-run, no rubric or fixture changed after declaration.

## Limitations

- One model, one binary, six Python-stdlib tasks, one operator, one afternoon. The length result holds within this battery and no further. The four primary tasks were chosen because they provoke the construct.
- The tested configuration is a standalone file. G2's effect when appended to James's deployed `~/.claude/CLAUDE.md`, where its one-sentence consequence cap would sit beside a ban, is untested.
- The judged construct is uncalibrated against a human reader. A kappa of 0.87 on `closing` is judge agreement, not validity. `words` treats code as prose. The role decomposition is a keyword heuristic.
- Passing H4 is a declared screen, not evidence of no harm. A truly length-neutral file passes non-inferiority about two thirds of the time under this design, so G1's `non_inferior` is a pass of a lenient gate, not a demonstration of no cost.
- The `month-end-recurrence` oracle's contract is a scope reading. Its 28 failures across the four arms say nothing about the files.
- The controls carry three trials per task, so their pooled median hides task-level movement. Under G2 `report-grouping-refactor` rose from a median of 81 to 115 words, while `window-merge-suite` fell from 133 to 120, and the per-task cap applies to the primary tasks only. At n = 3 this is not evidence of harm. It is a place the next round should look.
- F2R against G1 isolates one edit that changes content and size together. The compressed reply's effect on length (GMR 0.81 relative to F2R) cannot be separated from its changed content.
- Cost and duration are cache-confounded and never read as arm effects.

## Verified

Run in this session, output in the transcript:

- `python3 -m unittest discover -s tests` from the root before dispatch: 871 tests, OK, including the harness `dispatch_seed` test and the 33 bakeoff 13 contract tests. After the report and the analyzer corrections: 873 tests, OK.
- `python3 fixtures/validate.py` from the campaign directory: `6 probes, 0 problems`, redact identity ok (79 files), no auth-shaped keys.
- `clause_campaign.py check` on both declarations: exit 0, plans `01fb788be09e` and `bc4545874141`, both sealing `dispatch_seed = 13`, harness sha `c940d8671ee5`, scan sha `c83cf227dfc9`.
- `clause_campaign.py exercise` on both: exit 0; 128 and 24 trials, no `failures/` directory; `verify` exit 0 on both.
- `clause_judge.py verify` for `codex` and `claude` on both runs: 640 + 120 records each, exit 0.
- `analyze.py` with `--controls`: exit 0; `partial` false; judge coverage 760 of 760 per judge; `results/analysis-2026-09-06.json` written, then regenerated after the analyzer corrections with identical verdicts (diff: 6 leaves, all new bookkeeping fields).
- Codex Astra adversarial review of this report (`notes/2026-09-05-bakeoff13-study/07-codex-report-review.md`). It verified every table number against the JSON, re-verified both runs and all 1,520 judgments, reproduced the analysis in memory, and confirmed the four proxy-hit streams as README-after-tests. Its eleven findings, on explanations and latent code paths, are all reconciled above.
- Ledgers: `sources/source-register.csv` S047 (this run); `sources/claim-ledger.csv` C058–C062.

Not done: no human calibration of any judged label; no route (b) arm; no adversarial re-judging with a third judge.

## What this changes downstream

- **G2 is the working candidate.** It answers bakeoff 12's open question. A size signal in the rule form cut the invitation without the length cost, on this battery, and had fewer judged-incomplete messages (coverage is screened, not tested for improvement). The council's design notes (`02`, section 4) say the next step for a shortening candidate that passes the screen is the deployed-file question. The echo sensitivity result adds a rewording step before that.
- **Instrument follow-ups**, for James to decide. (1) Should the echo sensitivity rule distinguish an echoed hand-back from an echoed phrase, or should the file avoid distinctive phrases the model will reuse? (2) Should the check proxy exempt edits to non-code files, given that the README-after-tests pattern accounts for F1's four hits in bakeoff 12 and all four hits here? (3) Should the `month-end-recurrence` oracle keep its implementation-stated `schedule` contract, which has made the false-completion component uninformative in three campaigns?
- `AGENTS.md` "Current campaign" updated to bakeoff 13; bakeoff 12 preserved and frozen. All work remains uncommitted on `main`; committing is James's call.
