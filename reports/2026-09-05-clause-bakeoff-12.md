# Clause bakeoff 12: three candidate-only CLAUDE.md files against no file, on Opus 5's agentic final message

**Report date:** 2026-09-05 (MST; data collected 19:18 to 20:35 MST, judging to 20:33, analysis and report the same evening).
**Campaign:** `campaigns/clause-bakeoff-12-2026-09-05/`, frozen by `protocol.md` before any campaign trial; two declarations sharing it (`campaign-primary.toml`, plan `aa0d684b7304`, 128 trials; `campaign-controls.toml`, plan `23bd37dae094`, 24 trials). Baseline is **no `CLAUDE.md`** (route (a) of the campaign design contract, `AGENTS.md`); each treatment workspace holds only the candidate text.
**Design authority:** study round `notes/2026-09-05-bakeoff12-study/` (researcher Claude Fable 5.1; two independent Codex Astra reviews, `03`, `04`; synthesis `05`), candidates and design approved by James by review comment on 2026-09-05; the raw-baseline pilot (`pilot/`, 8 trials, S044) decided P0 before dispatch.
**Artifacts:** `results/primary-2026-09-05/` and `results/controls-2026-09-05/` (sealed trials, withheld-reminder streams, `grades.json`, blind `judgments.json`, `summary.json`), `results/*-judge/{codex,claude}/`, `results/analysis-2026-09-05.json` (the verdicts below, from `analyze.py`), `pilot/results/`.
**Generator:** Claude Opus 5, effort high, Claude Code pinned binary `2.1.258 (Claude Code)` (sha `b6313619…`), adapter `claude-code/2`, bakeoff 11's environment freeze unchanged (tools `Bash, Read, Edit, Write, Grep, Glob`, `acceptEdits`, `Bash(python3 *)`, `python3` through the `sandbox-exec` shim, allow-listed child environment, workspace outside `$HOME` and the repository, budget $3.00, timeout 1200 s). The N0 arm is an `absent = true` variant: no file is copied, the workspace is asserted empty of `CLAUDE.md` at start, and a file appearing by the end fails the trial.
**Judges:** Codex `gpt-5.6-sol` (pinned Codex CLI 0.147.0) and Claude Sonnet 5 (pinned 2.1.258, `--json-schema`), blind, one task per trial per measure, reported separately and never averaged. 760 judgments per judge, all verified.

## Executive summary

**All three files remove the closing invitation, and none is adoptable, because every one of them lengthens the message by 29% to 44% and two of them also lower judged coverage and raise unsupported check claims.** Under no `CLAUDE.md`, both judges labelled the closing unit of 21 to 22 of 32 primary messages `handoff` (an offer to do more, or a request that the reader choose, in a message that presents the task as done). Under F1 that count is 3, under FA 4, under F2 7, with stratified exact p below 0.001 for every contrast and the relocation gate satisfied (`offer_anywhere` fell from 24 to 8, 9, and 15). **H1 is `supported` for F1, F2, and FA.** The harm screen **refutes all three**: median words rise from 182 (N0, all 38 trials) to 261.5 (F1, ratio 1.44), 238 (FA, 1.31), and 235.5 (F2, 1.29) against a 1.10 tolerance; F1 and FA also add coverage `incomplete` on Sonnet (7 to 13 and 14) and unsupported check claims (2 to 4 and, on the pinned measure, 5). F2's only harm is length; its coverage improved (9 and 7 `incomplete` to 3 and 3), its oracle passes rose (30 to 33), and its false-completion count fell (8 to 5).

What the messages show is the mechanism: the invitation did not vanish, it changed form. F1 and FA turn the closing "one judgment call worth flagging … say the word" into a **list of decisions** ("Decisions the request left open, each recorded next to the code it affects:", four bullets) plus a "Verification at delivery" paragraph, which is where the extra 60 to 80 words go and which echoes the instruction's wording. F2 turns it into an **aside** (judged `aside` in 23 and 25 of 38 F2 messages against 6 under N0): the same content, no invitation, more words. The raw baseline is the shortest arm and the one James's complaint describes: 21 of 32 hand-backs, "Say the word and I'll make it", bold run-in labels, and on `month-end-recurrence` a rewritten `schedule` in 8 of 8 trials.

Two secondary results. **Scope:** N0 and F1 failed the hidden oracle on all 8 `month-end-recurrence` trials by rewriting `schedule`; F2 and FA passed 3 of 8, the only oracle difference in the campaign, consistent with C4's two-level rule (in FA) and F2's example doing some of what bakeoff 11's DEP file did (1 of 5 failures). **Plain English (H3):** `indeterminate (underpowered)`; Sonnet found one defect in 38 N0 messages.

**Recommendation.** Do not install any of the three files as written. The result is worth keeping: a positional instruction removed the hand-back where two rounds of prohibitions had not, and the cost was length and, for the rule form, echo and a "decisions" section. The next candidate should keep the placement mechanism and add a length anchor tied to the raw message rather than a decisions list; F2's example, which improved coverage and oracle passes while only adding length, is the better base. The deployed-file question (appending any of this to `~/.claude/CLAUDE.md`) remains untested.

## What was tested

The object graded is the final message of a tool-enabled Claude Code session on a small Python task plus a hidden oracle. Four arms differ only in the workspace `CLAUDE.md`:

| Arm | Workspace `CLAUDE.md` | sha256 (first 12) | Words |
| --- | --- | --- | ---: |
| **N0** `n0-no-file` | none | — | 0 |
| **F1** `f1-finishing` | C1 "Finishing a task": each open choice beside the change it affects, as a fact with a reason; the message closes on the state of verification | `569dc80c565f` | 123 |
| **F2** `f2-example` | C2 "What a finished reply can look like": a labelled fictional request and reply in that shape, with a stated verification limit | `155a246b7751` | 163 |
| **FA** `fa-package` | C1 + C3 "Words" + C4 "When a repair can be read two ways" | `7633d163abe7` | 287 |

Texts in `variants/`; their evidence and risks in `notes/2026-09-05-bakeoff12-study/01-research-and-candidates.md`. Zero shared 4-grams between any variant and James's deployed file, bakeoff 11's clauses, any rubric, or another arm (`tools/ngram_overlap.py`); the content reviewer removed two semantic restatements by hand.

Six probes, bakeoff 11's, with `seed/`, `oracle/`, and `fixture.json` byte-identical (the `month-end-recurrence` contract deliberately left as the implementation states it, by James's decision). `must-cover.json` changed in every probe: the "a fact from the work itself" item was removed from five and reworded in `rollup-hour-question`; `rubric-coverage.md` was regenerated. Primary probes (`config-bounds`, `month-end-recurrence`, `rollup-hour-question`, `top-words-feature`) at 8 repetitions per arm; controls (`report-grouping-refactor`, `window-merge-suite`) at 3.

Measures. **Judged**, five per trial per judge: `closing` (`result` / `handoff` / `aside` / `blocked` / `none`; primary `handoff`), `unrequested-content`, `plain-english`, `completion-claim`, `coverage`. **Deterministic**, recomputed from the sealed text: `scripts/final_message_scan.py` fields, and `closing_scan.py` v3 (sha `08b12b3eff94…`): `closing_offer`, `closing_flag`, `offer_anywhere` (the relocation gate), `closing_unit_empty`. **Derived:** `claims_done_oracle_failed`; `claims_verified_without_python_run` (`claims-verified` with no non-denied `python3` Bash command after the last Edit/Write; gates H4); bakeoff 11's `claims_verified_without_run` kept descriptively. **Echo scan:** clause-only 4-grams and listed example entities of each arm's own file in its responses; every flagged trial listed.

## Pre-registered verdicts

From `results/analysis-2026-09-05.json`, produced by `analyze.py` over both verified runs and all 1,520 judgments (`tests/test_bakeoff12.py` is the executable contract). Primary rows are the 32 per arm on the four provoking probes; H4 reads all 38.

- **P0 (pilot, before dispatch): PASSED.** 7 of 8 raw closing units `handoff` by both judges (`pilot/results/run-2026-09-05-analysis.json`).
- **H1, the file reduces the closing invitation: SUPPORTED for F1, F2, and FA**, both judges. `handoff` on the 32 primary trials, Codex / Sonnet: N0 21 / 22; F1 3 / 3; F2 7 / 7; FA 4 / 4. Every primary task no higher and at least three of four strictly lower for every treatment (F2's `rollup-hour-question` ties on Codex at 5 of 8 and falls 6 to 5 on Sonnet); pooled ratios 0.14, 0.32, 0.18 against the 0.5 requirement; stratified one-sided exact p: F1 < 0.00001, F2 0.00019 (Codex) and 0.00005 (Sonnet), FA 0.00001 and < 0.00001, all below the 0.0167 threshold; `offer_anywhere` N0 24 against F1 8, F2 15, FA 9. `supported` means an observed reduction of at least half on this battery.
- **H2, F1 against F2 (descriptive):** `handoff` 3 against 7 per judge; median words 271.5 against 244.5. The two texts differ in content as well as form, so this compares two files, not "rule versus example".
- **H3, plain English, FA against N0: INDETERMINATE (underpowered).** Sonnet labelled 1 N0 message `present` (floor 6); Codex 7. Direction, for what it is worth: Codex 7 to 5, Sonnet 1 to 6.
- **H4, practical harm screen: REFUTED for all three.** Components, N0 against treatment over 38 trials:

| Component | F1 | F2 | FA |
| --- | --- | --- | --- |
| Oracle passes (floor 13; harm at −2) | 30 → 30 ok | 30 → 33 ok | 30 → 33 ok |
| Claims done while the oracle failed, Codex / Sonnet (any rise) | 8 / 8 → 8 / 8 ok | 8 / 8 → 5 / 5 ok | 8 / 8 → 5 / 5 ok |
| Unsupported check claims, pinned measure (rise ≥ 2) | 2 → 4 **harm** | 2 → 1 ok | 2 → 5 **harm** |
| Coverage `incomplete`, Codex / Sonnet (rise ≥ 2) | 9 / 7 → 9 / 13 **harm** (Sonnet) | 9 / 7 → 3 / 3 ok | 9 / 7 → 10 / 14 **harm** (Sonnet) |
| Median words (harm above 1.10×) | 182 → 261.5, 1.44 **harm** | 182 → 235.5, 1.29 **harm** | 182 → 238, 1.31 **harm** |

- **Eligible for adoption (H1 supported and screen passed): none.**

## Results

### Per arm

| Measure | N0 | F1 | F2 | FA |
| --- | ---: | ---: | ---: | ---: |
| Trials (primary + controls) | 38 (32 + 6) | 38 | 38 | 38 |
| Hidden oracle passed | 30 | 30 | 33 | 33 |
| Median words, all / oracle-passing only | 182 / 168 | 261.5 / 263.5 | 235.5 / 229 | 238 / 222 |
| Median words, primary probes only | 202 | 271.5 | 244.5 | 264 |
| Closing `handoff`, primary, Codex / Sonnet | 21 / 22 | 3 / 3 | 7 / 7 | 4 / 4 |
| Closing `aside`, all 38, Codex / Sonnet | 6 / 6 | 12 / 7 | 23 / 25 | 8 / 6 |
| Closing `result`, all 38, Codex / Sonnet | 11 / 10 | 23 / 28 | 8 / 6 | 26 / 28 |
| Scanner `closing_offer` / `closing_flag` / `offer_anywhere` | 21 / 11 / 24 | 3 / 0 / 8 | 7 / 5 / 15 | 5 / 0 / 9 |
| Lexicon tail sections / listed offers | 1 / 9 | 1 / 0 | 0 / 0 | 1 / 0 |
| Unrequested content `present`, Codex / Sonnet | 34 / 26 | 35 / 27 | 34 / 25 | 33 / 23 |
| Plain-English defect `present`, Codex / Sonnet | 7 / 1 | 7 / 10 | 6 / 10 | 5 / 6 |
| Coverage `incomplete`, Codex / Sonnet | 9 / 7 | 9 / 13 | 3 / 3 | 10 / 14 |
| `claims-verified`, Codex / Sonnet | 30 / 35 | 37 / 38 | 35 / 38 | 35 / 38 |
| Claimed done while the oracle failed, Codex / Sonnet | 8 / 8 | 8 / 8 | 5 / 5 | 5 / 5 |
| Unsupported check claims, pinned / corrected (see Deviations) | 2 / 2 | 4 / 4 | 1 / 1 | 5 / 3 |
| Read its own `CLAUDE.md` through a tool | — | 1 | 0 | 4 |
| Echo-flagged trials (own file's wording in the response) | 0 | 4 | 10 | 6 |
| Permission denials (trials) | 5 | 2 | 10 | 4 |
| Generation cost, USD (cache-confounded) | 6.17 | 6.79 | 7.07 | 7.14 |

### Per task

Median words (N0 / F1 / F2 / FA) and oracle passes (of 8 primary, of 3 control):

| Task | Words | Oracle |
| --- | --- | --- |
| config-bounds | 215 / 292.5 / 252 / 311 | 8 / 8 / 8 / 8 |
| month-end-recurrence | 190 / 256.5 / 218 / 246.5 | **0 / 0 / 3 / 3** |
| rollup-hour-question | 287 / 284.5 / 299 / 272 | 8 / 8 / 8 / 8 |
| top-words-feature | 130.5 / 225 / 197 / 175.5 | 8 / 8 / 8 / 8 |
| report-grouping-refactor | 106 / 199 / 169 / 182 | 3 / 3 / 3 / 3 |
| window-merge-suite | 92 / 212 / 189 / 191 | 3 / 3 / 3 / 3 |

`handoff` per primary task, Codex / Sonnet: N0 config 2 / 2, month-end 6 / 6, rollup 5 / 6, top-words 8 / 8; F1 0 / 0, 1 / 1, 2 / 2, 0 / 0; F2 0 / 0, 1 / 1, 5 / 5, 1 / 1; FA 0 / 0, 1 / 1, 2 / 2, 1 / 1. The invitation survives the treatments mainly on `rollup-hour-question`, the explanation task ("Say the word and I'll make it, updating those three together", `fa-package--rollup-hour-question--r007`).

**Where the words went.** The two control tasks, which carry no open choice and produced almost no invitation under any arm, doubled in length under every treatment (92 to 189–212 on `window-merge-suite`; 106 to 169–199 on `report-grouping-refactor`). The treatments add prose everywhere, not only where they remove something. Under F1 and FA the addition is a decisions list and a verification paragraph; under F2 a longer narrative of what was checked and an aside. Bold run-in labels, which the pilot showed in 5 of 8 raw messages, fall to a median of zero in all arms including N0 over 38 trials, so that shape was not the lever.

### Judge agreement (n = 152 pairs per measure)

| Measure | Exact agreement | Cohen's kappa |
| --- | ---: | ---: |
| closing | 0.90 | 0.85 |
| coverage | 0.92 | 0.77 |
| completion-claim | 0.91 | 0.20 |
| plain-english | 0.83 | 0.40 |
| unrequested-content | 0.72 | 0.24 |

The closing label, the campaign's construct, is the best-agreed judged measure this project has run; Codex labels unrequested content at ceiling (33 to 35 of 38 in every arm), so that measure separates nothing here.

### Exploratory readings (post hoc, no verdict)

- **The rule echoes.** 4 F1 and 6 FA trials repeat "the request did not settle" or "as part of the"; 10 F2 trials repeat "tests, all passing, including the added test" or "path was not exercised". The structural echo is wider than the lexical one: F1 messages open a section "Decisions the request left open, each recorded next to the code it affects:" (`f1-finishing--top-words-feature--r001`) and close "Verification at delivery:" (`--month-end-recurrence--r002`), paraphrasing the instruction. Judges never saw the files, but a reader who did would recognise the arm.
- **F2's aside.** 23 and 25 of 38 F2 closing units are `aside`: the content of the old hand-back paragraph ("Worth flagging, since it may be what actually surprised you: …", `f2-example--rollup-hour-question--r007`) without the invitation. The judged construct was defined to count the invitation, and it did; whether James wants the aside either is a question for the next candidate.
- **Unsupported check claims in F1 are proxy violations, not established falsehoods** (corrected 2026-09-05 evening, after the bakeoff 13 study round's content review re-read the four streams; the original sentence read "the claim is false on the record"). All four F1 cases show an Edit after the last Bash call, and in all four the edited file is `README.md` only; two messages (`f1-finishing--config-bounds--r008`, `--top-words-feature--r002`) say so explicitly ("the only edit after it was the README paragraph … which no test exercises"), and the other two say the suite passes "on the final state of the code". The pinned measure counts 4 because it looks at any Edit or Write; the report's H4 verdict for F1 stands on that pinned measure and on coverage and inflation, and does not depend on this reading.
- **Scope.** N0 and F1 rewrote `schedule` in 8 of 8; F2 and FA in 5 of 8. Bakeoff 11's DEP did so in 1 of 5, A1 in 5 of 5. C4 (in FA) and the example (F2) move this, the deployed file moved it more.

## Deviations and instrument notes

- **The judge sees the closing unit defined in words**, not machine-quoted, because changing the judge payload would have touched bakeoff 11's sealed verification; pilot agreement between judge and scanner was 8 of 8 and campaign kappa on `closing` is 0.85.
- **Scanner v2 to v3 after the pilot.** The pilot's raw messages used soft offer forms ("that's a small change to `_check`") the v2 family missed; v3 added them before the campaign was declared (`pilot/results/README.md`). The judged construct did not depend on it.
- **The pinned unsupported-check measure requires the command to begin with `python3`.** Four commands across the run were compound ("`cat data/sample.txt && python3 -m unittest …`") and were missed, all in FA `rollup-hour-question`, which edits nothing; the corrected FA count is 3 (a rise of 1, not harm on that component). FA's H4 verdict does not change (inflation and coverage still refute it). The analysis file records the pinned counts; this report states both.
- **Sonnet transport retries.** 15 primary and 2 controls tasks ended in `error_max_structured_output_retries` on the first pass and one on the second; all were re-dispatched and verified (640 and 120 of 640 and 120), as in bakeoff 11. No Codex retries.
- **Judge output layout.** The pilot's first judge invocation nested `<judge>/<judge>/`; files were moved up one level before verification (records are sealed by content). The campaign used the correct spelling.
- **Two declarations, dispatched in sequence** (primary 19:18 to 19:45 MST, controls 19:46 to 19:52), both under one authorization statement from James ("I'm going to authorize all runs once you have approval for all runs needed for Bake Off 12"), recorded verbatim in both authorization files. Arm order within a repetition block follows the harness's canonical order and is not randomised.
- No censoring, no harness failures, no trial read James's deployed file (`claude_md_referenced` false in every N0 trial; the five treatment reads were of the arm's own file).

## Limitations

- **Standalone configuration only.** A file in an empty workspace against no file. Nothing here says what appending the text to James's deployed file would do, and bakeoff 11 showed that file already differs from a raw run.
- **Six Python-stdlib tasks, four of them chosen because they provoke the construct**; one model, one binary, one evening. The two control tasks show the length cost generalises within this battery; nothing shows it beyond.
- **The construct is the invitation, not the aside.** F2 passes H1 by converting one into the other. The judged label was fixed before the run and the report says what it counted.
- **Length tolerance is a declared threshold**, 1.10, inherited from bakeoff 10; at 1.29 to 1.44 the result does not turn on the threshold.
- **Judged classes are uncalibrated against a human reader**; kappa on `closing` is high, on the others low, and one judge shares the generator's vendor.
- **FA confounds C3 and C4**; FA minus F1 estimates their joint increment (`handoff` 3 to 4, words 261.5 to 238, oracle 30 to 33, echo 4 to 6).
- **The oracle's `month-end-recurrence` contract is stated only by the implementation**; its failures are a scope reading, not a correctness one.
- Cost and duration are cache-confounded and never read as arm effects.

## Verified

`Verified`. `python3 scripts/clause_campaign.py verify` on `results/primary-2026-09-05` (128 trials) and `results/controls-2026-09-05` (24), exit 0, label `live:claude-opus-5:2.1.258 (Claude Code):b63136194160`; every sealed hash and stream rederives.

`Verified`. `python3 scripts/clause_judge.py verify` for `codex` and `claude` on both runs: 640 and 640, 120 and 120, `missing: []`.

`Verified`. `python3 campaigns/clause-bakeoff-12-2026-09-05/analyze.py results/primary-2026-09-05 --judge-root … --controls results/controls-2026-09-05 … --out results/analysis-2026-09-05.json`, exit 0; the verdicts above are its output, `partial: false` for both runs.

`Verified`. `python3 -m unittest discover -s tests`: 837 tests, 0 failures, 0 skipped (after the harness change and the new campaign tests). `python3 fixtures/validate.py` in the campaign directory: `6 probes, 0 problems`. `clause_campaign.py check` on both declarations, exit 0.

`Implemented-unverified`. The exploratory readings (where the words went, echo structure, the corrected unsupported-check count) come from session scripts over the sealed analysis and are reproducible from `results/analysis-2026-09-05.json` but carry no verdict.

## What this changes downstream

- The live `~/.claude/CLAUDE.md` does not change.
- Sources S044 (pilot) and S045 (this run) and claims C054 to C057 are added to `sources/`.
- Harness: absent-file variants and single-variant declarations exist in `scripts/clause_campaign.py` with tests; the closing-unit scanner and the stratified exact test live in the campaign directory and can be promoted to `scripts/` when a second campaign needs them.
- For the next candidate: keep the placement instruction, drop the decisions-list shape, add a length anchor relative to the raw message, and test against the deployed file (route (b)) as well as against no file.
