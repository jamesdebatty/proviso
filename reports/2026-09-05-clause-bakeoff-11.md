# Clause bakeoff 11: two CLAUDE.md additions on Opus 5's agentic final message

**Report date:** 2026-09-05. Data collected 2026-09-05 (generation from 07:31 MST; judging and analysis the same morning; times below are MST unless marked Z).
**Campaign:** `campaigns/clause-bakeoff-11-2026-09-05/`, frozen by `protocol.md` before any campaign trial, with three pre-dispatch amendments (2026-09-05a–c) recorded there; P0 and H1 to H5 pre-registered with verdict rules.
**Design authority:** a six-agent Claude Fable 5.1 council chaired by a seventh, convened on James's instruction; every proposal, critique, decision, and timestamp is under `notes/2026-09-05-bakeoff11-council/` (`07-chair-log.md` is the timeline; `08` and `11` are the two synthesis rounds).
**Artifacts:** `results/run-2026-09-05/` (sealed trials with withheld-reminder streams, `grades.json`, blind `judgments.json`, `summary.json`), `results/run-2026-09-05-judge/{codex,claude}/`, `results/run-2026-09-05-analysis.json` (the verdicts below, produced by `analyze.py`), and the three canaries under `canary*/results/`.
**Generator:** Claude Opus 5, effort high, Claude Code pinned as a binary copy `2.1.258 (Claude Code)` (sha `b6313619…`), adapter `claude-code/2`: tools `Bash, Read, Edit, Write, Grep, Glob`, permission mode `acceptEdits`, allow rule `Bash(python3 *)`, the permitted `python3` (Homebrew 3.14.5, pinned by real path) run through a per-trial `sandbox-exec` shim (workspace and private temp writable, network denied, `/Users` unreadable except the workspace), child environment built from an allow-list, one fresh workspace outside `$HOME` and the repository per trial, budget cap $3.00, timeout 1200 s. Hidden oracle run after each session with `<interpreter> -I -B oracle/run.py`.
**Judges:** Codex `gpt-5.6-sol` effort high (Codex CLI 0.147.0, bakeoff 8's pinned copy) and Claude Sonnet 5 effort high (the pinned 2.1.258 binary, `--json-schema`, no tools), blind, one task at a time, no arm or trial identity, reported separately and never averaged.
**Baseline:** DEP, a byte copy of James's deployed `~/.claude/CLAUDE.md` taken 2026-09-05 (`4b670ca87fe7`). **Anchor:** A1, the two-section composite (`f70f86a92e9f`), byte-identical to bakeoffs 8–10's A1.

## Executive summary

Neither addition is adoptable under the rules the council committed to
before the run, and the battery did not provoke the defect it was built to
measure in the form the pre-registered detector looks for. Across 120 final
messages, no arm produced a heading or bold lead-in from the frozen tail
lexicon ("Next steps", "Summary", "Changes needed", …) and none used a phrase
from the frozen closing-offer list, so the power check P0 failed on the
baseline (0 of 30, floor 10) and H1 is **indeterminate (underpowered)** for
both treatments. H5, the anchor, is **refuted**: James's deployed file and the
minimal two-section A1 file are both at zero tails.

What the run did show, with the pre-registered rules and then the exploratory
readings labelled as such:

- **On this battery the defect appears in a shape the lexicon cannot see.** The tail here is a
  closing paragraph that flags an adjacent decision or offers more work
  ("One thing worth your decision, which I did not change…", "Tell me which
  and I'll make the change", "Say the word if you want it clamped"). A post
  hoc last-line reading (regex below, not a verdict) finds it in A1 4, DC1 8,
  DEP 9, and DV1 13 of 30 messages.
- **Neither clause lowered the pooled median word count against the deployed
  file (H2 refuted; the rule has zero tolerance for a rise).** Pooled median words: DEP 124.5, DV1 126.5 (task medians lower on
  5 of 6, pooled higher because `top-words-feature` grew 75 to 108), DC1
  142.5 (+14.5%, lower on 3 of 6). The minimal A1 file gives 91.5.
- **No harm passed for either treatment (H4 refuted).** DC1 failed on
  inflation (+14.5%) and on judged coverage (Codex 22 vs 20, Sonnet 24 vs 21
  incomplete). DV1 failed on Codex coverage (24 vs 20) and on
  claims-done-while-the-oracle-failed (2 vs 1, both judges). Oracle pass was
  DEP 29, DV1 28, DC1 30 of 30.
- **Both clauses improved judged plain English (H3b supported, direction
  only, no gate); unrequested content is split between judges (H3a
  indeterminate).** Both judges labelled plain-English defects less often
  under DC1 (Codex 7 to 2, Sonnet 6 to 1) and DV1 (7 to 5, 6 to 1), and DEP's
  base rate clears the protocol's H3 floor of 6. Sonnet labelled unrequested
  content present in 9 DC1 messages against 13 DEP and 12 DV1; Codex 21 in
  all three. DC1 had no message that claimed completion while the hidden
  oracle failed, and no oracle failure at all (30 of 30).
- **A1 is short, and on this battery it covers less and changes more than
  asked.** Its judged coverage was no better than any arm on the
  pre-registered measure (Codex 23 incomplete, second-worst; Sonnet 21, tied
  with DEP) and worst on the exploratory reading below (20 and 18 against
  DEP's 12 and 12). It failed the hidden oracle 5 times, all on
  `month-end-recurrence`, where every A1 message changed `schedule`'s
  semantics beyond the requested crash fix; four of the five said so and
  offered to revert, and "All 6 tests pass" was true of the visible suite.
  One DEP and two DV1 trials made the same change. The oracle's `schedule`
  contract is contestable (Limitations), so this is a scope reading, not a
  correctness one.

**Recommendation: do not append either clause to `~/.claude/CLAUDE.md`.** On
this battery the prose James objects to sits in the closing paragraph, so the
next campaign should replace the lexicon detector with a positional or judged
reading of that paragraph, and should keep the hidden-oracle design, which
surfaced a scope difference that no text measure did.

## What was tested

The object graded is the **final message** of a tool-enabled Claude Code
session on a small Python implementation task, plus a hidden oracle that says
whether the task was actually achieved. Four arms differ only in the
workspace `CLAUDE.md`:

| Arm | `CLAUDE.md` | sha256 (first 12) |
| --- | --- | --- |
| **A1** `a1-response-numbers` | Response style + Numbers (anchor) | `f70f86a92e9f` |
| **DEP** `dep-deployed-file` | James's deployed file, unmodified (baseline) | `4b670ca87fe7` |
| **DV1** `dv1-deployed-vendor` | DEP + `## Working on a task`: Anthropic's *Prompting Claude Opus 5* snippets on response length, finishing with the outcome, written-deliverable length, scope, and corrections, minus two stated exclusions | `c6da4910c9b2` |
| **DC1** `dc1-deployed-final-message` | DEP + `## Final message`: the council's positive description of the post-tool message (outcome first; only what the reader needs to act; `path:line`; ends with no trailing section or offer; plain words, no coined labels) | `2e451cadb247` |

Each treatment equals DEP + `"\n## <Heading>\n\n"` + its bare clause
(`variants/vendor-clause.md` `7fd687a9ad80`, `variants/final-message-clause.md`
`1225013a49c0`), confirmed by `cmp`. The A1-based versions of both clauses
(`v1-vendor-guidance.md`, `c1-final-message.md`) were prepared and not run;
the council moved the baseline from A1 to DEP in round 2 because the change
James would ship is an append to his file and bakeoff 9's A1 pilot showed
zero tail sections in 20 messages (`notes/…/11-chair-synthesis-round2.md`).

Six probes (`probes/`), each a stdlib Python package with a README naming the
test command, a prompt that names every identifier the oracle imports, a
`must-cover.json` of ideas a reader needs (each with one fact knowable only
by doing the work), and a hidden `oracle/` outside the seed:

| Probe | Task | Oracle |
| --- | --- | --- |
| `month-end-recurrence` | bug fix, easy | hidden date cases incl. leap year, `schedule`, CLI |
| `top-words-feature` | add a function and tests, medium | hidden cases, `count_words` unchanged, visible suite green, tests mention `top_words` |
| `config-bounds` | add validation with a deliberate ambiguity, medium | unambiguous cases only |
| `rollup-hour-question` | explanation, no edits | every seed file unchanged, no new files |
| `report-grouping-refactor` | extract a shared helper, hard | goldens plus a `patch.object` proof each caller uses the helper |
| `window-merge-suite` | make a red suite pass without touching tests, hard | test files unchanged, hidden merge cases, CLI output |

Deterministic measures over the final message (`scripts/final_message_scan.py`,
frozen lists): `tail_section_count` (heading or bold lead-in whose title is in
`TAIL_TITLES`: next steps, changes needed, summary, notes, what I did, what
changed, recommendations, follow-ups, caveats, …), `closing_offer_count`
(frozen phrase list), `narration_opener`, `headings`, `bold_leadins`,
`words`, references, and the prose-density fields; `oracle-pass` from the
trial record. `tail_present = tail_section_count > 0 or closing_offer_on_pass`.
Judged measures, four per trial per judge: `unrequested-content`
(none/present), `plain-english` (none/present), `completion-claim`
(claims-verified / claims-done-unverified / reports-blocked-or-partial /
no-claim), `coverage` (complete/incomplete). Derived:
`claims_done_oracle_failed`. Blinding: zero shared 4-grams between either
clause and any rubric or question at freeze.

## Pre-registered hypotheses

All verdicts are from `results/run-2026-09-05-analysis.json`, produced by
`analyze.py` from the sealed run and both judge sets (480 records each, all
verified). Baseline for H1–H4 is DEP; treatments are DV1 and DC1; H5 compares
DEP with A1. `n = 30` per arm, six tasks, five repetitions, all blocks
complete, nothing censored.

- **P0, power check: FAILED.** `tail_present` (a lexicon tail section, or a
  listed closing offer on a passing trial) is 0 of 30 under DEP; floor 10.
- **H1, the clause reduces the tail: INDETERMINATE (underpowered), both.**
  0 of 30 in every arm; Fisher one-sided p = 1.0.
- **H2, the clause shortens the final message: REFUTED, both.** The rule
  refutes when the pooled median rises. DV1 126.5 vs 124.5 (ratio 1.016;
  task medians lower on 5 of 6). DC1 142.5 vs 124.5 (ratio 1.145; lower on 3
  of 6).
- **H3a, unrequested content judged less often: INDETERMINATE, both.** Sonnet
  lower for both (DEP 13 → DV1 12, DC1 9); Codex level (21 → 21, 21).
- **H3b, plain English judged better: SUPPORTED, both.** DEP `present` 7
  (Codex) and 6 (Sonnet) of 30 clears the protocol's H3 floor of 6; both
  judges are lower for DV1 (5 and 1) and DC1 (2 and 1). Direction only; H3
  gates nothing. **Erratum:** the analyzer as first run applied the P0 floor
  `n/3 = 10` to H3 as well and reported `indeterminate (underpowered)`; the
  frozen protocol text says `b_DEP,j < 6` and amendment 2026-09-05b re-scaled
  only P0 and the H4 oracle floor. `analyze.py`, which the plan hash does not
  cover, was corrected on 2026-09-05 after the citation audit and the sealed
  analysis regenerated; both readings are stated here.
- **H4, no harm: REFUTED, both.** Components (harm needs a two-trial rise on
  oracle or coverage, any rise in claims-done-oracle-failed, or words above
  110%): DC1 — oracle ok (30 vs 29), claims ok (0 vs 1 both judges),
  coverage harm (Codex 22 vs 20; Sonnet 24 vs 21), inflation harm (1.145).
  DV1 — oracle ok (28 vs 29), claims harm (2 vs 1, both judges), coverage
  harm on Codex (24 vs 20) and ok on Sonnet (22 vs 21), inflation ok (1.016).
- **H5, the deployed file raises the tail relative to A1: REFUTED.** Both at
  0 of 30, a tie that the rule (`P_DEP ≤ P_A1`) calls refuted.
- **Adoptable (H1 and H4 supported): neither.**

## Results

### Per arm, 30 trials each

| Measure | A1 (anchor) | DEP (baseline) | DV1 | DC1 |
| --- | ---: | ---: | ---: | ---: |
| Hidden oracle passed | 25 | 29 | 28 | 30 |
| Median words | 91.5 | 124.5 | 126.5 | 142.5 |
| Median words, oracle-passing trials only | 70 | 123 | 120.5 | 142.5 |
| Median words per sentence | 15.4 | 17.2 | 16.8 | 18.2 |
| Median bullets | 1 | 2 | 3 | 3 |
| Messages with any heading | 0 | 0 | 0 | 0 |
| Messages with a bold lead-in | 0 | 2 | 1 | 0 |
| Lexicon tail sections / listed offers / narration openers | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Unrequested content `present`, Codex / Sonnet | 15 / 5 | 21 / 13 | 21 / 12 | 21 / 9 |
| Plain-English defect `present`, Codex / Sonnet | 4 / 5 | 7 / 6 | 5 / 1 | 2 / 1 |
| Coverage `incomplete`, Codex / Sonnet | 23 / 21 | 20 / 21 | 24 / 22 | 22 / 24 |
| Completion claim `claims-verified`, Codex / Sonnet | 20 / 23 | 26 / 29 | 26 / 28 | 27 / 30 |
| Claimed done while the oracle failed, Codex / Sonnet | 5 / 5 | 1 / 1 | 2 / 2 | 0 / 0 |
| `claims-verified` with no command after the last edit, Codex / Sonnet | 0 / 0 | 5 / 6 | 8 / 9 | 8 / 9 |
| Median turns / median tool calls | 10 / 9 | 11 / 10 | 11 / 10 | 11 / 10 |
| Permission denials (non-`python3` shell commands) | 7 | 8 | 9 | 9 |
| Generation cost, USD (cache-confounded; not an arm effect; includes $0.126 of Haiku side-model spend across the run) | 4.81 | 6.61 | 6.53 | 6.47 |

### Per task, median words and oracle passes (DEP / DV1 / DC1 / A1)

| Task | Words | Oracle passes of 5 |
| --- | --- | --- |
| config-bounds | 200 / 145 / 162 / 120 | 5 / 5 / 5 / 5 |
| month-end-recurrence | 135 / 129 / 147 / 110 | 4 / 3 / 5 / **0** |
| report-grouping-refactor | 95 / 89 / 139 / 39 | 5 / 5 / 5 / 5 |
| rollup-hour-question | 238 / 187 / 231 / 159 | 5 / 5 / 5 / 5 |
| top-words-feature | 75 / 108 / 115 / 49 | 5 / 5 / 5 / 5 |
| window-merge-suite | 86 / 66 / 84 / 63 | 5 / 5 / 5 / 5 |

**The month-end failures are a scope difference, not a weak fix.** All five
A1 messages changed `schedule` to anchor each date on the start day ("Jan 31
gives Feb 28, Mar 31, Apr 30") and reported the visible suite passing, which
was true; only the hidden `schedule` case fails, because the oracle pins the
module's existing chained behaviour. Four of the five A1 messages flag the
change and offer to revert it. One DEP trial and two DV1 trials made the same
change and failed the same way; the other deployed-file trials flagged the
question in prose and left `schedule` alone. This is the pattern Anthropic's
Opus 5 page calls widening the task, and the minimal file did it every time,
but the oracle's contract is contestable: the prompt's own sentence ("should
fall on the last day of any shorter month") can be read as the anchored rule,
and the seed states the chained contract only in `next_monthly`'s docstring.
Recorded as a fixture limitation below.

### Judge agreement (n = 120 pairs per measure)

| Measure | Exact agreement | Cohen's kappa |
| --- | ---: | ---: |
| coverage | 0.94 | 0.85 |
| completion-claim | 0.87 | 0.44 |
| plain-english | 0.83 | 0.23 |
| unrequested-content | 0.63 | 0.32 |

Codex labels unrequested content far more readily than Sonnet (78 against 39
of 120), the same asymmetry bakeoff 10 saw on mannered prose; the two are
reported separately and never averaged.

### Exploratory readings (post hoc, not pre-registered, no verdict)

- **Closing-paragraph flags and offers.** Regex over the last line:
  `tell me (which|if|whether|what)|say the word|if you want|if you prefer|
  i can (add|make|change|do|wire|switch)|i'll (make|add|do) (the|that|it)|
  want (me|it) ` (case-insensitive). Matches: A1 4, DC1 8, DEP 9, DV1 13 of
  30. Typical last lines: "One thing to flag, outside what you asked me to
  change: …", "Say the word and I'll apply it with tests.", "One thing I left
  out: I validate ranges, not types." This is the shape James describes, and
  it is invisible to the frozen title list because it carries no heading. The
  regex undercounts: a manual read of 15 messages found variants it misses
  ("Revert it if you'd rather", "say so and I'll revert", offers placed
  mid-message), so the counts above are floors, and A1's 4 in particular.
- **Coverage without the planted facts.** Each `must_cover` list carried one
  item prefixed "a fact from the work itself" (for example that two of six
  tests failed before the fix); Codex missed them in 20 of 20 on two probes
  (Sonnet 18–20) and they dominate `incomplete`. Setting them aside, `incomplete` is Codex A1 20,
  DEP 12, DV1 15, DC1 12 and Sonnet A1 18, DEP 12, DV1 13, DC1 14 of 30
  (`notes/…/tools/coverage_excluding_planted.py`). On that reading DC1 and
  DEP are level on Codex (12 and 12) and two apart on Sonnet (14 and 12),
  DV1 is one to three above DEP, and A1 is six to eight above.
- **Blinding held.** No treatment-arm response shares a clause-only 4-gram
  with its own `CLAUDE.md`; no arm's messages echo the vendor or council
  wording. Only one DC1 message and no other read its `CLAUDE.md` through a
  tool.
- **Containment.** Every trial's child environment carried the allow-listed
  names only and `python3` ran through the shim. 33 trials recorded a
  permission denial, 55 denial events in all: 17 `for … cat` loops, 16
  multi-line or compound commands that begin with `python3` but which the
  `Bash(python3 *)` prefix rule did not admit (a harness finding for the next
  campaign), 15 `python -m pytest` (no `3`), 4 `Write` attempts under `/tmp`,
  2 `cat`, 1 `cp`. Commands that ran without a denial and outside the shim, because
  `acceptEdits` auto-approved them: `ls` 84, `find` 56, `cat` 26, `head` 6,
  `rm` 4 (all inside the workspace), `grep`, `cp`, `diff` 1 each. So
  `acceptEdits` admits more than read-only commands; the workspace is a
  discarded temp directory, so the exposure is to what those commands could
  read, and the strict credential scan found no key shape in any stream. 59
  tool inputs named an absolute path outside the workspace (23 the model's own
  `*/.git/*` glob on `find`, 25 under `/tmp`, every one of which was denied
  and all on `report-grouping-refactor`, 4 `/dev/null`, 4 a bare `/`, the
  rest noise); 31 of the 41 trials with such an input had only the glob. The
  field is really "absolute-path tokens in tool inputs": it flags globs and
  redirections and would miss a relative `..` escape. 29 reminder spans were
  withheld; no stream carried an unpaired reminder tag.

## Canaries and deviations

- **Three canaries, seven trials, $1.30, all excluded from analysis.** Canary A
  (top-words-feature × A1, DEP, M1) and B (window-merge-suite × A1, DEP)
  proved the adapter end to end: tool surface and permission mode asserted per
  trial, Opus-only answer model, reminders withheld with the stream still
  sealed, oracle exit 0 in 5 of 5, about $0.20 and 30 s per trial on both a
  medium and a hard probe.
- **`--restricted` suppressed project `CLAUDE.md`.** A direct tool-less call
  on the pinned binary in a directory holding a marker `CLAUDE.md` returned
  the marker only without the flag ($0.016 for both calls). Canary A's marker
  had appeared because the model had Read its own `CLAUDE.md` after a `find`
  listed it. The flag was removed before any campaign trial (amendment
  2026-09-05a); under the final configuration no canary C trial read the file
  and the marker still appeared.
- **Read-only shell commands are auto-approved.** `find` and `ls` ran with no
  denial under both `acceptEdits` and `dontAsk` (canary C), so they run
  outside the `python3` shim. Symmetric across arms; recorded per trial in
  `bash_commands`. `dontAsk` added no containment, so `acceptEdits`, which
  scopes edits to the workspace, was kept (amendment 2026-09-05b).
- **Repetitions raised from 3 to 5 before dispatch** on cost and time
  grounds (amendment 2026-09-05b); hypotheses and thresholds unchanged, the
  power floor scaling with `n`.
- **The first dispatch was refused by its own deadline.** The design and
  harness phase overran: two council agents were cut off by an account spend
  limit at about 03:50 and the chair finished the adapter, canaries, and
  freeze alone, and the chair's log under-estimated the clock. At 07:30 the
  06:00 deadline refused all 120 cases with nothing dispatched; the empty
  attempt is preserved (`results/run-2026-09-05-attempt1/`), the plan was
  re-materialized with a 09:30 deadline and re-authorized (amendment
  2026-09-05c).
- **The Sonnet judge pass had to be repeated.** The judge module's transport
  check grepped the whole stream for `"is_error": true`, so a structured-output
  schema-validation retry inside the stream (a `tool_result` saying "Output
  does not match required schema", present in 91 of the 480 Sonnet streams)
  followed by a successful final result read as failure: 196 successful
  tasks were refused on the first pass and re-dispatched after the check was
  changed to read the final `result` event only (roughly 196 wasted
  subscription calls, no record lost). Four further tasks ended in
  `structured_output_retry_exhausted` and were re-judged on a second retry;
  four of the 480 Sonnet labels therefore come from a retried call.
- **Clock drift and the chair log.** The chair's timeline rows between about
  02:30 and 05:04 were estimates that ran roughly two and a half hours behind
  the clock; the 07:30 correction row in `07-chair-log.md` says so, and the
  judge manifests' UTC timestamps are authoritative.
- **Protocol text erratum.** The frozen `protocol.md` carries amendment
  2026-09-05c spliced into the last sentence of amendment 2026-09-05b ("P0
  may" … "therefore fail on DEP"); the file is hash-bound to the plan and is
  left as sealed. Read the two amendments as separate paragraphs.
- **T-024 fixed on the way:** `summary.json` for `claude-code/2` runs now
  carries `live:<model>:<version>:<sha12>`; `claude-code/1` keeps its sealed
  label so bakeoff 10 still re-verifies.

## Limitations

- **The tail lexicon did not fit the defect's shape on this battery.** Every
  pre-registered tail count is zero, so H1 and H5 say nothing about the
  closing-paragraph flags the exploratory reading finds. The council chose a
  frozen title list for recomputability and named the drift risk in advance
  (protocol, Limitations); the drift happened. A future campaign needs a
  detector for the last paragraph's function, judged or positional.
- **Coverage lists were too demanding.** The planted-fact items behave as a
  floor, so the pre-registered coverage component of H4 is largely a measure
  of whether the message mentions one specific fact, and its `harm` calls for
  DV1 and DC1 rest on differences of two to four trials against a base of
  twenty. The exploratory reading is the fairer one and is labelled as such.
- **Six Python-stdlib tasks, one language, one test runner, one model, one
  operator, one morning.** Nothing transfers to essays, other languages, or
  interactive sessions where James answers back.
- **Baseline is James's file; the clauses were not tested on A1.** V1 and C1
  exist as files and were not run.
- **The month-end oracle pins one reading of an under-specified prompt.**
  A1's anchored `schedule` is a defensible design; the oracle counts it as a
  failure because the prompt asked for a crash fix and the module's existing
  contract was chained. The contrast is between arms that changed unrequested
  behaviour and arms that flagged it, which is what the scope question asks,
  but the fixture could have said so explicitly.
- **Judged classes are uncalibrated and one judge shares the generator's
  vendor.** Direction only; kappa on unrequested content and plain English is
  low. Codex judge sessions see James's skill catalogue (the red-team counted
  "summary" 24×, "outcome" 23×, "brief" 12×, "concise" 2× across 56 skill
  directories), an isolation gap of the transport, not a blinding break.
- **Structural proxies move with formatting**; medians of bullets and
  sentence length are reported beside words for that reason.
- **Cost and duration are cache-confounded** and are reported, never read
  as arm effects.
- **Instrument notes from the code review** (`notes/…/13-red-team-code-review.md`):
  the oracle verdict cannot be re-derived by `verify` because the workspace is
  discarded, so it rests on the sealed record; three oracles spawn a child
  interpreter without `-I`, which a workspace `unittest.py` could shadow (no
  trial added a top-level `.py`, so none did); the `top-words-feature` oracle
  runs the model's own visible tests as part of its "cover it" check; the
  frozen `TAIL_TITLES` would count a `**Note:**` lead-in and `OFFER` matches
  "happy to report" (zero occurrences of either); judge records carry no hash
  of the judge module, which changed twice between declaration and report;
  the protocol's "side-model rule" is the adapter's existing halt on any
  non-Opus assistant event, never separately stated; `Read`, `Glob`, `Grep`
  and auto-approved shell commands run unconfined with the real `HOME` (no
  excursion observed; the operator's username appears in `ls -la` output in
  46 streams).
- **The harness changed twice after the design freeze and before the first
  campaign trial** (amendments 2026-09-05a and b: `--restricted` removed,
  permission mode confirmed, repetitions raised), and the dispatch happened
  after the declared deadline (2026-09-05c). Every change is recorded with
  what had been observed at the time; the hypotheses, thresholds, clause
  texts, arm set, and probe set did not move.

## Verified

`Verified`. `python3 scripts/clause_campaign.py verify campaigns/clause-bakeoff-11-2026-09-05/results/run-2026-09-05`, exit 0, 2026-09-05 07:56 MST and again after the code review: 120 trials, every sealed hash rederives, every withheld-reminder stream matches its trial by digest and, since the review, by content (`verify` now re-parses each stream and requires the final text, answer models, and turn count to equal the record; a forged record re-sealed with the harness's own function no longer passes), summary label `live:claude-opus-5:2.1.258 (Claude Code):b63136194160`.

`Verified`. `python3 scripts/clause_judge.py verify … --judge codex` and `--judge claude`, exit 0 with `verified: 480, missing: 0` for each (the counts are the evidence; the command also exits 1 on a wrong output root, checked): every judgment rederives from its raw stream, every Codex rollout names `gpt-5.6-sol`, every Sonnet stream names `claude-sonnet-5`.

`Verified`. `python3 campaigns/clause-bakeoff-11-2026-09-05/analyze.py … --out results/run-2026-09-05-analysis.json`, exit 0; the verdicts above are its output after the H3-floor correction, `partial: false`, all five repetition blocks complete. Judge cost is not recorded by either transport; the $0.016 for the two direct tool-less checks is the chair's reading of the binaries' `total_cost_usd` in the session, with no retained artifact.

`Verified`. `python3 -m unittest discover -s tests`, exit 0, 812 tests, 0 failed, 0 skipped, after the judge fix, the stricter `verify`, and the review's added tests. `python3 fixtures/validate.py` in the campaign directory: `6 probes, 0 problems`. `python3 scripts/clause_campaign.py verify campaigns/clause-bakeoff-10-2026-09-01/results/run-2026-09-01`, exit 0, 75 trials. `python3 scripts/clause_campaign.py shim-check`: workspace write ok; outside write, `~/.codex/auth.json` read, and loopback network all `PermissionError`.

`Implemented-unverified`. The exploratory readings (closing-paragraph regex, coverage without planted facts, blinding echo scan, containment counts) came from the chair's scripts under `notes/2026-09-05-bakeoff11-council/tools/` and inline session commands; they are reproducible from the sealed run but are not part of `analyze.py` and carry no verdict.

## What this changes downstream

- The live `~/.claude/CLAUDE.md` does not change.
- Source S043 (this run) and claims C050–C053 are added to `sources/`.
- `claude-code/2` has now carried one authorized 120-trial campaign end to
  end and its output was consumed by `analyze.py`; T-025 records the
  campaign and stays open for James. T-024 closed on this run.
- `scripts/clause_judge.py` decides transport failure from the final
  `result` event only (see Deviations). `analyze.py` applies the protocol's
  literal H3 floor.
