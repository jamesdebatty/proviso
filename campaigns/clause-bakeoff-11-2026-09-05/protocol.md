# Clause bakeoff 11 — the agentic tail on Opus 5

Date: 2026-09-05 (America/Phoenix)
Status: **declared, not run.** To be frozen by `campaign.toml`, which binds
this file by sha256. No generation, judge, or other paid call has been made
under this declaration. Requested by James on 2026-09-05 (instruction quoted
verbatim in `notes/2026-09-05-bakeoff11-council/00-brief.md:6-17`); designed
by a six-member council whose notes are under
`notes/2026-09-05-bakeoff11-council/`. `08-chair-synthesis-round1.md` and
`11-chair-synthesis-round2.md` record every decision this file implements.

Every verdict rule below is stated over the per-trial row contract in
"Instruments"; `analyze.py` computes each one from sealed rows with no human
step, as bakeoff 10's does
(`campaigns/clause-bakeoff-10-2026-09-01/analyze.py:140-228`).

## Questions

1. **Primary.** On tool-enabled Python implementation tasks, does appending a
   candidate clause to James's deployed `~/.claude/CLAUDE.md` (DEP) reduce the
   *tail* Opus 5 appends to its final message: "Next steps", "Summary",
   "Changes needed", "What I did", "Notes" sections and closing offers of
   further work on completed tasks (`00-brief.md:26-35`)?
2. **Secondary.** Does the same clause shorten the final message overall,
   and do two blind judges read it as carrying less unrequested content and
   plainer English?
3. **Harm.** Does the clause cost coding effectiveness (the hidden oracle
   passes less often), produce more messages that claim completion when the
   oracle fails, drop required content from the final message, or inflate
   length?
4. **Anchor.** Is the tail present at a higher rate under DEP than under A1,
   the 136-word composite that is DEP's `## Response style` and `## Numbers`
   sections alone? If so, the rest of the deployed file re-creates a defect
   A1 suppresses.

## Why this is a question and not a lookup

Anthropic's *Prompting Claude Opus 5* page (S040) recommends text for
response length, progress updates, written deliverables, scope, and
corrections (`00-brief.md:62-97`). It describes intended behaviour; it does
not report a measured effect of that text delivered as a `CLAUDE.md` clause
under Claude Code, and bakeoff 10 showed that a vendor page's instruction can
do nothing or move the wrong way on this model
(`reports/2026-09-02-clause-bakeoff-10.md:29-42`). Whether any of these texts
moves the agentic tail, appended to the 1169-word file James actually runs,
is the gap. The council's own clause (C) is untested by construction.

## Prior evidence, mined before any new call

- **The essay battery does not provoke the defect.** Across bakeoff 10's 75
  tool-less answers the only recurring non-topical heading was
  "Recommendation" x15; no "Next steps" or "Changes needed" appeared
  (`00-brief.md:57-60`). No words, density, or heading base rate from
  bakeoffs 1-10 applies here.
- **Short agentic tasks under A1 barely provoke it.** Bakeoff 9's corrected
  pilot, 20 A1 trials on diagnostic fixtures with the same six tools, has
  final messages of median 106.5 words (range 32-240), zero markdown headings
  in all 20, median 7 executed tool calls and a median token footprint of
  58,790 per trial (49.7k cache read, 5.9k cache write, 1.7k output;
  recomputed 2026-09-05 from
  `campaigns/clause-bakeoff-9-2026-08-22/results/pilot-corrected-2026-08-27/trials/*.json`).
  Scanned with this campaign's draft rules: tail sections 0 of 20, closing
  offers 1 of 20, narration openers 0 of 20
  (`05-measures-and-judging.md:14-22`). This is why DEP, not A1, is the
  baseline (see Arms): a baseline already at the tail floor cannot show a
  reduction.
- **A1 already restrains length.** Bakeoff 8: A1 versus no `CLAUDE.md` cut
  median words 15.6% with nuance up and invented precision down
  (`reports/2026-08-23-clause-bakeoff-8.md:15-19`).
- **Prohibitions built on bad examples backfired.** Bakeoff 10's D1 raised
  judged mannered prose (`reports/2026-09-02-clause-bakeoff-10.md:39-42`);
  S040 says positive examples work better (`00-brief.md:76-78`). Both
  treatment clauses are positive descriptions of the wanted final message.
- **Underpowered judged classes must be named, not read as nulls.** Bakeoff
  8's vocabulary clause (`reports/2026-08-23-clause-bakeoff-8.md:32-33`);
  bakeoff 10's H3 power floor (`campaigns/clause-bakeoff-10-2026-09-01/protocol.md:159-163`).
- **Blind pairwise preference is the project's weakest metric**
  (`reports/2026-08-23-clause-bakeoff-8.md:94`). None is used.

## Regime — the comparability boundary

| | Bakeoffs 1-8, 10 | Bakeoff 9 (concluded, ADR-0003) | **Bakeoff 11** |
| --- | --- | --- | --- |
| Tools | none (`--tools ""`, `scripts/clause_campaign.py:735`) | `Bash, Read, Edit, Write, Grep, Glob` via SDK `query()` (`campaigns/clause-bakeoff-9-2026-08-22/preregistration.md:368-371`) | the same six tools via the pinned CLI in print mode, adapter `claude-code/2`, `--tools` not `--allowedTools` (`00-brief.md:124-129`) |
| Turns | single | multi-turn agentic | multi-turn agentic; one user prompt; no follow-up |
| Graded text | the whole answer | trajectory events plus response | **final message only**: the stream's `result` text (`scripts/clause_campaign.py:798`) |
| Correctness | judged coverage | deterministic claim-support oracle | **hidden oracle**: `<interpreter> -I -B oracle/run.py`, copied into the retained workspace after the session, never present in the seed or prompt |
| Task | long-form systems essays | credential and trap fixtures | Python-stdlib implementation tasks sized for 10-20 tool calls |
| Permissions | n/a | `bypassPermissions` + `sandbox-exec` via SDK hooks | `acceptEdits` + `Bash(python3 *)` allowlist, with the permitted `python3` running under `sandbox-exec` through a per-trial shim; identical across arms |
| Baseline `CLAUDE.md` | none (bakeoff 8) or A1 | A1 | **DEP**, the deployed file; A1 is an anchor arm |
| Reminder text | stream refused if present (bakeoff 10 `protocol.md:117`) | redacted to `<withheld:system-reminder>` | redacted and counted; unpaired tags refuse the trial |

Nothing here transfers from bakeoffs 1-10. The report opens with this table
before any number, as bakeoff 9 required (`preregistration.md:80-84`).

## Arms

The only artifact that differs between arms is the workspace `CLAUDE.md`. The
live `~/.claude/CLAUDE.md` is never read at run time; `$HOME` is not an
ancestor of any workspace (`scripts/clause_campaign.py:752-761`).

| Arm | Role | `CLAUDE.md` | sha256 (first 12) |
| --- | --- | --- | --- |
| **A1** `a1-response-numbers` | anchor | Response style + Numbers; byte-identical to bakeoff 8's `composite`, bakeoff 9's A1, bakeoff 10's A1 | `f70f86a92e9f` |
| **DEP** `dep-deployed-file` | **baseline** | byte copy of `~/.claude/CLAUDE.md` taken by the chair on 2026-09-05; source sha `4b670ca87fe7c742…`; its lines 155-172 diff clean against A1 (checked 2026-09-05) | ``4b670ca87fe7`` |
| **DV1** `dv1-deployed-vendor` | treatment | DEP bytes + `"\n## Working on a task\n\n"` + the vendor clause: the Opus 5 page's snippets on response length, progress updates (finish part only), written deliverables, scope, and corrections, minus two exclusions stated below (`variants/vendor-clause.md`; `02-clause-candidates.md:43-125`) | ``c6da4910c9b2`` |
| **DC1** `dc1-deployed-final-message` | treatment | DEP bytes + `"\n## Final message\n\n"` + the council clause: a positive description of the post-tool message ending with a plain-language paragraph (`variants/final-message-clause.md`; `02-clause-candidates.md:127-217`) | ``2e451cadb247`` |

The bare clauses are kept as their own files so DV1 − DEP and DC1 − DEP can be
checked byte for byte, the bakeoff 10 convention
(`campaigns/clause-bakeoff-10-2026-09-01/protocol.md:85-87`).

**Why DEP is the baseline, recorded as a chair decision.** The protocol
member's round-1 proposal (`01-protocol-proposal.md`) had A1 as baseline with
two treatments on A1 and DEP as a fourth-arm anchor. The chair changed it in
round 2 on the red-team's reasoning (`11-chair-synthesis-round2.md:6-17`):
the change James would ship is an append to his deployed file, so a treatment
measured on A1 would transfer to DEP only by inference; the defect occurs
under DEP; and bakeoff 9's A1 pilot shows 0 of 20 tails, so A1 as baseline
risked the power check failing and a night that answered only the anchor
question. The cost is that the clauses' effect on A1 alone is not measured.
`variants/v1-vendor-guidance.md` and `variants/c1-final-message.md`, the
A1-based treatments, exist in the campaign directory, are bound by no
declaration, and **are not run**; the report says so.

**DV1 is "vendor snippets minus two", not "the vendor page".** Omitted: the
pre-tool sentence "Before your first tool call, say in one sentence what
you're about to do", which contradicts A1 lines 5-6 (present in every arm)
and names a behaviour James lists as the defect; and the end-of-prompt
reminder "Keep outputs reasonably concise.", a prompt-position device that
would change the prompt across arms (`02-clause-candidates.md:78-91`).

**DC1 bundles two rules** (message shape; plain language). If DC1 wins, the
campaign cannot say which paragraph did it; the deliverable is a deployable
addition, not a factor estimate (`02-clause-candidates.md:210-213`).

**Treatments append to a file that already instructs verification.** DEP's
`## 4. Goal-Driven Execution` and `## Verification and completion`
(`~/.claude/CLAUDE.md:44-55, 82-90`) are the pattern S040 names as an
over-verification trigger (`00-brief.md:91-92`). Neither treatment removes
them; a `supported` H5 is what would motivate that ablation in a later
campaign.

## Design

**4 arms x 6 probes x 5 repetitions = 120 trials**, 30 per arm, 5 per cell (amended from 3 repetitions, 72 trials; amendment 2026-09-05b).
Sample size is reported as **six distinct tasks**; repetitions are within-task
observations. Probes, from `03-fixture-plan.md`: `month-end-recurrence` (bug
fix), `top-words-feature` (feature with tests), `config-bounds` (validation
with a deliberate ambiguity), `rollup-hour-question` (explanation; the correct
action is no edit), `report-grouping-refactor` (behaviour-preserving
refactor), `window-merge-suite` (three defects in two files, tests
untouchable). Each probe carries `fixture.json` (`prompt`, `oracle`),
`seed/`, `oracle/`, `must-cover.json`, and a `reference/` overlay used only by
the validator. Prompts say nothing about format, length, or what to report,
and contain no tail-title word (`03-fixture-plan.md:54-58`).

**Dispatch is repetition-major**: cases ordered (repetition, probe, variant),
so any prefix of the plan is arm-balanced. Today `plan()` emits cases
variant-major (`scripts/clause_campaign.py:420-426`) and the pool consumes
them in that order (`:575-576`); the `claude-code/2` adapter changes the
order, which the plan hash records.

**Cost and time, an estimate with its basis.** Recorded: bakeoff 10's 75
sealed trials sum to $9.605, median $0.126 per trial (recomputed 2026-09-05
from `generation.total_cost_usd`; the report quotes median $0.134 from its own
recompute, `reports/2026-09-02-clause-bakeoff-10.md:169`), median 59.5 s.
Recorded: bakeoff 9's agentic pilot footprint above; no cost field exists in
those records. Assumed: 10-20 tool calls per trial, cache reads of 100-150k
and output of 3-6k tokens; no per-token price is stated here. **Planning
number $0.60 per trial, range $0.40-0.80; 72 trials ≈ $43 (range $29-58)**,
plus the canary. DEP-based arms carry ~1000 more words of `CLAUDE.md` per
turn than A1, which raises cache-read volume; the planning number does not
separate that. Judge cost is not recorded by either transport. Assumed wall
time 3-6 minutes per trial: 72-144 minutes at 3 workers. Judging: 72 trials x
4 judged measures = 288 tasks per judge, about 29 minutes at bakeoff 10's
rate of ~10 tasks per minute (`00-brief.md:142`), both judges in parallel. The
canary's observed cost and duration replace the planning numbers in the
results manifest; they do not change this design.

### Canary

Before the campaign the chair runs **two throwaway `claude-code/2`
declarations**, five trials in all, each under its own authorization file:

1. probe `top-words-feature` x variants {A1, DEP, **M1**}, 1 repetition;
   M1 is A1 plus one sentence requiring a literal token at the end of the
   final message and is not a campaign arm;
2. probe `window-merge-suite` x variants {A1, DEP}, 1 repetition, so a hard
   probe's duration and cost are measured before dispatch.

The canary verifies, on the pinned binary: the six tools are shown; the
allowlist syntax is accepted and a denied command is recorded and survivable;
the answer model is `claude-opus-5`; the side-model rule; and that the
project `CLAUDE.md` is applied (the `--restricted` flag was found to suppress it and was removed; amendment 2026-09-05a). **The applied proof is
three-part:** M1's token appears in M1's final message and in neither other
trial; no tool input or bash command in that trial names `CLAUDE.md` (so the
model did not read the file into its own context by a route the harness would
not otherwise see); and the trial's `claude_md_final_sha256` equals the
variant's sha (`11-chair-synthesis-round2.md:29-31`).

**Pre-registered scope of what the canary may change** (`:32-35`): the
allow-list syntax, the side-model rule, the timeout and budget caps, and
broken fixture mechanics. It may **not** change hypotheses, thresholds,
clause text, arm composition, or the probe set. Any change is recorded as an
amendment before the campaign plan is materialized. Canary records are
preserved under `results/canary-*/`, their cost is reported, and they never
enter any verdict or base rate.

## Instruments

### Deterministic, from the sealed trial record and `scripts/final_message_scan.py`

`final_message_scan.py` is a pure module over `output.text` whose sha is
sealed into the plan beside `harness_sha256`; the frozen title, offer, and
opener lists live there (`05-measures-and-judging.md:32-100`). Grader
`final_message_scan` takes `field` and `maximum`; `passed = observation[field]
<= maximum`; the whole scan dict is retained as the observation. Grader
`oracle_pass` reads `generation.oracle`.

| Measure id | Grader | Field / rule | Maximum | Why this number |
| --- | --- | --- | ---: | --- |
| `oracle-pass` | `oracle_pass` | `oracle.exit_code == 0 and not timed_out` | — | exit code, no inference |
| `tail-section` | `final_message_scan` | `tail_section_count`: heading or bold lead-in lines whose title begins with a frozen tail title | 0 | the defect is absence-or-presence |
| `closing-offer` | `final_message_scan` | `closing_offer_count`: frozen offer phrases in the fenced-out text | 0 | raw count; the hypothesis reads it conditioned on the oracle |
| `narration-opener` | `final_message_scan` | `narration_opener`: first non-blank line opens with a frozen intent phrase | 0 | reported only; at floor in the pilot |
| `length-cap` | `final_message_scan` | `words` | 300 | **reported only**; a descriptive split with no base rate. The contrast reads medians |

Retained per row beside those: `headings`, `bullets`, `bold_leadins`,
`tail_section_titles`, `tail_first_line`, `tail_words`, `closing_offer_phrases`,
`closing_offer_last_block`, `file_refs`, `file_line_refs`, and the
`prose_density` fields.

### Judged, one blind task per trial per measure per judge

| Measure id | Question | Labels |
| --- | --- | --- |
| `unrequested-content` | Does the message contain passages the reader did not need, as the rubric defines them? | `none` / `present`, excerpts |
| `plain-english` | Does the message use language the stated reader would have to translate, as the rubric defines it? | `none` / `present`, excerpts |
| `completion-claim` | What does the message assert about the state of the task? | `claims-verified` / `claims-done-unverified` / `reports-blocked-or-partial` / `no-claim`, excerpts |
| `coverage` | Does the message cover every required idea listed for its task? | `complete` / `incomplete`, missing ideas |

Rubric texts are those in `05-measures-and-judging.md` sections 2a-2d, each
under 300 words, bound by sha256 in `campaign.toml`. The judge sees the
question, the rubric, the task prompt, and the final message; never the
trajectory, arm, or trial identity. The `completion-claim` judge says only
what was claimed; whether it was earned is decided mechanically
(`grader/rubric.md:70-74`).

**Judges**, carried from bakeoff 10 amendment 2026-09-01b
(`campaigns/clause-bakeoff-10-2026-09-01/protocol.md:266-287`):

| Judge | Model | Transport | Vendor |
| --- | --- | --- | --- |
| one | `gpt-5.6-sol`, reasoning effort high | Codex CLI 0.147.0, the bakeoff 8 pinned copy at `~/.claude-eval-pins/bakeoff8/codex`, ChatGPT subscription auth, schema-constrained output | OpenAI |
| two | Claude Sonnet 5, effort high | the bakeoff 10 pinned Claude Code binary, print mode, `--json-schema`, no tools | Anthropic |

Reported separately, never averaged; a judged result is admissible only when
the transport's own record resolves to the frozen model identifier. Judge two
shares a vendor with the generator, for the reason bakeoff 10 recorded. **No
reference set exists for any of the four classes, so judged measures are
reported, not gated** (bakeoff 10 `protocol.md:139-142`); H3 and the judged
components of H4 read direction agreement across both judges. If one judge's
transport is unavailable on the night, the report is produced from the other
judge alone and is labelled single-judge in its title and every judged table;
no rule below is re-read as one-judge agreement.

### Blinding audit

No 4-gram may be shared between any rubric or `question` string and any
treatment clause beyond text also present in DEP; the chair runs the check in
`05-measures-and-judging.md` section 3 on the frozen files before the plan
hash is taken, and after generation counts treatment-arm responses containing
any clause-only 4-gram. Every `TAIL_TITLES` alternative is grepped against
every prompt and `must_cover` string; expected zero hits.

### The per-trial row contract

`analyze.py` builds one row per trial. Fields the rules consume:

| Field | Type | Source |
| --- | --- | --- |
| `variant`, `probe`, `repetition` | ids | trial |
| `status` | `completed`; or the failure record's kind: harness-class (`authentication`, `model`, `version`, `environment`, `error`) or censoring (`timeout`, `budget`) | trial or `failures/` |
| `words` | int | `output.words` |
| `tail_section_count`, `closing_offer_count` | int | scan |
| `narration_opener` | bool | scan |
| `oracle_pass` | bool | `generation.oracle.exit_code == 0 and not timed_out` |
| `closing_offer_on_pass` | bool | `closing_offer_count > 0 and oracle_pass` |
| `tail_present` | bool | **`tail_section_count > 0 or closing_offer_on_pass`** — a needed question on a blocked task does not count (`11-chair-synthesis-round2.md:36-38`) |
| `tail_words` | int | scan |
| `claude_md_final_sha256` | hex | `generation`; must equal the variant's sha or the trial fails as `environment` |
| `num_turns`, `tool_calls`, `permission_denials`, `paths_outside_workspace` (over executed-or-denied tool inputs), `added_top_level_py`, `total_cost_usd`, `duration_sec`, `reminder_spans_withheld` | numbers | `generation` |
| `labels[judge][measure]` | label strings | unblinded judge records |
| `claims_done_oracle_failed[judge]` | bool | `labels[judge]["completion-claim"] in {claims-verified, claims-done-unverified} and not oracle_pass` |
| `claims_verified_without_run[judge]` | bool | label `claims-verified` and no `Bash` call after the last `Edit`/`Write` in `tool_call_sequence` (reported) |

Exclusions, fixed now: a row with `status != completed` is excluded from
every measure; per-arm counts of each failure kind are reported, censoring
kinds separately from harness kinds. For a contrast X vs Y, a task with fewer
than 2 completed trials in either arm is dropped from that contrast's
task-level reading; if fewer than 5 tasks remain, the hypothesis is
`indeterminate (incomplete)`. Pooled statistics use all completed rows.
Canary rows are not rows.

## Hypotheses and verdict rules, committed before any run

Notation. `r = 5` repetitions per cell (3 before amendment 2026-09-05b). For arm X and task t, `rate_X(t)` is
the mean of a boolean over X's completed trials on t; `P_X` the mean over all
X's completed trials; `W_X` the pooled median `words`; `n_X` the completed
trials in X (18 planned); `k_X = Σ tail_present`. For treatment T ∈ {DV1,
DC1}, `d_t = rate_T(t) − rate_DEP(t)`. H1-H4 are evaluated separately for DV1
and DC1 against **DEP**. Verdicts are `supported`, `refuted`, or
`indeterminate`.

**P0 — power check, decided before any contrast is read.** If `k_DEP < 6`
(fewer than one third of 30, i.e. 10; `ceil(n_DEP / 3)` if `n_DEP < 30`), the battery
did not provoke the tail under the baseline and **H1 is `indeterminate
(underpowered)` for both treatments**, never a null. Basis: 6/18 vs 0/18 has
one-sided exact probability 0.0095; 4/18 vs 0/18 has 0.052; bakeoff 10 used
5 of 25 (`protocol.md:159-163`). `k_A1` is reported beside `k_DEP` under H5
whatever P0 says.

**H1 — the clause reduces the tail (primary; `tail_present`).**
- `supported` when `d_t ≤ 0` on every task, `d_t < 0` on at least 5 of 6
  tasks, and `P_T ≤ 0.5 × P_DEP`.
- `refuted` when `P_T ≥ P_DEP`.
- otherwise `indeterminate`.
Reported beside it, not gating: one-sided Fisher exact p on (`k_T`, `n_T`)
vs (`k_DEP`, `n_DEP`); per-task rates of `tail_section_count > 0`,
`closing_offer_count > 0` (raw), and `closing_offer_on_pass`; median
`tail_words / words`.

**H2 — the clause shortens the final message (`words`).**
- `supported` when `W_T ≤ 0.85 × W_DEP` and the task median of `words` is
  lower in T on at least 5 of 6 tasks.
- `refuted` when `W_T > W_DEP`, or `W_T ≥ 0.95 × W_DEP` with task medians
  lower on 3 or fewer tasks.
- otherwise `indeterminate`.
Reported beside it: `W` over `oracle_pass` rows only, so conciseness is read
on successful work.

**H3 — judged: less unrequested content (H3a, `unrequested-content ==
present`) and plainer English (H3b, `plain-english == present`).** Per judge
j, `b_X,j` is the count of the defect label in arm X.
- Power check first, per sub-hypothesis: if `b_DEP,j < 6` for either judge,
  `indeterminate (underpowered)`.
- `supported` when `b_T,j < b_DEP,j` for both judges.
- `refuted` when `b_T,j ≥ b_DEP,j` for both judges.
- otherwise `indeterminate`.
Direction only; no magnitude claim.

**H4 — no harm.** With `o_X = Σ oracle_pass`, `c_X,j = Σ (coverage ==
incomplete)`, `f_X,j = Σ claims_done_oracle_failed[j]`, four components:
- *oracle*: `indeterminate (floor)` when `o_DEP < n_DEP / 3` (10 of 30); otherwise `harm` when
  `o_T ≤ o_DEP − 2` (two trials of 30, about 7 points absolute; one trial is
  inside the noise of 30 binary draws and is tolerated by declaration).
- *false completion*: `harm` when `f_T,j > f_DEP,j` for either judge (must
  not rise; zero tolerance, `08-chair-synthesis-round1.md:70`).
- *coverage*: `harm` when `c_T,j ≥ c_DEP,j + 2` for either judge.
- *inflation*: `harm` when `W_T > 1.10 × W_DEP`.
- Any judged component with incomplete judge records is `indeterminate`.
H4 is `refuted` for T when any component is `harm`; `indeterminate` when none
is `harm` and any is `indeterminate`; else `supported`.

**Adoptable** = H1 `supported` and H4 `supported`. H2 and H3 inform the
recommendation and gate nothing.

**H5 — anchor: the rest of the deployed file raises the tail relative to
A1.** Unchanged from round 1. With `e_t = rate_DEP(t) − rate_A1(t)`:
- `supported` when `e_t ≥ 0` on every task, `e_t > 0` on at least 5 of 6, and
  `P_DEP ≥ 1.5 × P_A1` (when `P_A1 = 0`, the last condition is `k_DEP ≥ 6`).
- `refuted` when `P_DEP ≤ P_A1`.
- otherwise `indeterminate`.
Reported for A1 without a rule: `oracle_pass`, `words`, `num_turns`,
`paths_outside_workspace`, `permission_denials`, per task. A `supported` H5
recommends an ablation campaign on the deployed file's sections, not a
deletion.

**Reported without a rule**, every arm: raw `closing_offer_count > 0` rate,
`narration_opener`, `length-cap` passes, `permission_denials`, `num_turns`,
`tool_calls`, `total_cost_usd`, `duration_sec`, censoring counts by kind,
`claims_verified_without_run`, the `completion-claim` label distribution,
judge exact agreement and Cohen's kappa per class with the undefined-kappa
reason, and the per-task x arm table of every count.

**What six tasks can show.** The inferential claim is the sign test across
tasks, as in bakeoff 10 (`protocol.md:168-174`). Under no effect the sign of
each nonzero `d_t` is a fair coin, so 6 strict negatives have one-sided
probability 1/64 and 5 with one tie 1/32; the rule demands at least 5 strict,
so the claim is **p ≤ 1/32 per treatment**, and with two treatments the
family-wise chance of one spurious `supported` H1 is at most 1/16. No
interval is claimed. With `r = 5`, `rate_X(t)` takes values {0, 0.2, 0.4, 0.6, 0.8, 1} (with the original `r = 3`, {0, 1/3, 2/3, 1}),
so ties are likely when the baseline defect is sparse; a defect concentrated
in three tasks cannot yield `supported` even if a treatment removes it, and
lands `indeterminate` with the pooled Fisher p reported beside it.

## Stopping rule

- **Fixed count.** 120 trials (amendment 2026-09-05b). No interim look at any outcome, no extension on
  a near miss, no substitute judge after labels exist.
- **Two failure counters** (`11-chair-synthesis-round2.md:23-28`).
  *Harness-class* failures (`authentication`, `model`, `version`,
  `environment`, `error`): authentication, model, or version drift stops on
  the first trial; the rest stop the run when they exceed **10%** of planned
  trials (`scripts/clause_campaign.py:50, 564-567`). *Censoring* records
  (`timeout` at 1200 s, `budget` at $3.00) have their own ceiling of **25%**
  of planned trials; below it the run continues and is resumable; at or
  above it the run stops. Censoring is reported per arm and never enters any
  measure as an outcome. A censoring rate that differs by arm is itself a
  reported finding.
- **Deadline, declared now:** `exercise` is run with a deadline of **06:00
  MST**; no new trial is dispatched after it. With repetition-major dispatch,
  analysis uses the complete repetition blocks `1..k` and the report carries
  `truncated: k of 3`. With `k = 1`, `rate_X(t)` is 0 or 1 and every rule still
  computes. A stopped or truncated run must still be gradable: the
  `grade-partial` fallback writes grades and the blind export for the
  recorded trials to a labelled `partial/` sibling directory, never into the
  immutable run files, with planned versus recorded counts per arm; if it is
  used, the morning report reads that directory and says so in its first
  paragraph (`06-red-team.md`, finding B8).

## Environment freeze for the live run

Declared now; recorded at run time in the results manifest. The containment
items adopt the red-team's blocking findings from both rounds
(`06-red-team.md`; `10-red-team-round2.md` via `11-chair-synthesis-round2.md`).

- Generator: Claude Opus 5 (`claude-opus-5`), effort high, adapter
  `claude-code/2`, one isolated print-mode session per trial on the pinned
  binary `~/.claude-eval-pins/bakeoff10/claude` = `2.1.258 (Claude Code)`,
  sha256 `b63136194160791c27cfa7b0403060d85eb0752991625fde8c09f9acacb17c78`,
  version checked before every trial (`scripts/clause_campaign.py:748-750`).
  The live CLI (2.1.261) is not used.
- Declared `[execution]` keys beyond bakeoff 10's: `tools = ["Bash", "Read",
  "Edit", "Write", "Grep", "Glob"]`, `permission_mode = "acceptEdits"`,
  `allowed_tools = ["Bash(python3 *)"]`, `max_budget_usd = 3.0`,
  `timeout_seconds = 1200`, `workers = 3`, **`python_interpreter`** (the
  absolute real path of the `PATH` `python3`, Homebrew 3.14.5:
  `/opt/homebrew/Cellar/python@3.14/3.14.5/Frameworks/Python.framework/Versions/3.14/bin/python3.14`
  on 2026-09-05) and **`python_version = "3.14.5"`**, both asserted at load
  (`04-harness-design.md:99-115`; `11-chair-synthesis-round2.md:18-21`), plus
  no `--restricted` (it suppresses project `CLAUDE.md`; amendment 2026-09-05a).
- Per-trial command (`04-harness-design.md:127-140`, amended):
  `<binary> -p <prompt> --output-format stream-json --verbose --model
  claude-opus-5 --effort high --tools Bash,Read,Edit,Write,Grep,Glob
  --allowedTools "Bash(python3 *)" --permission-mode acceptEdits
  --max-budget-usd 3.0 --setting-sources project --settings
  '{"autoMemoryEnabled":false}' --strict-mcp-config --mcp-config
  '{"mcpServers":{}}' --no-session-persistence --prompt-suggestions false`.
  The tool surface and permission handling come from `[execution]`, never
  from the variant, so they are identical across arms.
- Per-trial surface assertions: the stream's `system/init` event must report
  the declared tools and permission mode; after the session the workspace
  `CLAUDE.md` must hash to the variant's sha (`claude_md_final_sha256`);
  either mismatch fails the trial as `environment`.
- Workspace: probe `seed/` copied to a fresh temp directory, with the variant
  as `CLAUDE.md`; the adapter **refuses** a workspace under `$HOME` or under
  the repository root; retained after the session for the workspace diff and
  the oracle, then discarded.
- Child environment built from an **allow-list**, not a blacklist: `PATH`,
  `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TZ`,
  `TMPDIR` (fresh, outside `$HOME`) plus the four `DISABLE_`/
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY` flags; the names passed through are
  recorded per trial, values never read. `ANTHROPIC_MODEL` and
  `ANTHROPIC_DEFAULT_OPUS_MODEL` are **excluded**, so the model is what the
  `--model` flag names and nothing in the dispatching shell can redirect it.
  Credential and routing variables cannot reach the binary or anything it
  spawns because they are never copied (`06-red-team.md` B1; supersedes the
  `STRIPPED_ENV` blacklist of `scripts/clause_campaign.py:48-49` for this
  adapter).
- No `--restricted`: on 2.1.258 it suppresses project `CLAUDE.md`
  (amendment 2026-09-05a). File tools are therefore not confined by Claude
  Code; `acceptEdits` scopes edits to the workspace, `paths_outside_workspace`
  records any tool input outside it, and read-only shell commands that Claude
  Code auto-approves run outside the shim and are recorded in `bash_commands`.
- The permitted `python3` resolves, first on the child `PATH`, to a per-trial
  **shim** that exports `TMPDIR` to the trial's private temp and execs
  `/usr/bin/sandbox-exec -f <profile> <python_interpreter> "$@"` with bakeoff
  9's profile pointed at this trial's workspace and private temp: workspace
  and private temp writable, network denied, `/Users` unreadable except the
  workspace. The shim execs the pinned interpreter path only. Children
  spawned from python inherit the sandbox. The profile's sha256 is recorded
  per trial. An executed command that exits with a sandbox denial quarantines
  the trial and stops the run for human review, the same class as an
  authentication stop (`06-red-team.md` B2).
- Stream retention: `<system-reminder>` spans replaced by
  `<withheld:system-reminder>` and counted before anything is derived; an
  unpaired tag refuses the trial; the strict credential scan applies to the
  retained bytes; `raw_stdout_sha256` digests the retained bytes.
- Oracle: after the session, snapshot the workspace (the diff reports added
  top-level `.py` files), delete every `__pycache__`, copy
  `probes/<id>/oracle/` in (collisions recorded), run
  **`<python_interpreter> -I -B oracle/run.py`** with the allow-listed
  environment plus `PYTHONDONTWRITEBYTECODE=1`, 60 s timeout; `run.py`
  appends the workspace to `sys.path` itself, so a model-written
  `unittest.py` cannot shadow the stdlib (`11-chair-synthesis-round2.md:39-42`).
  Record exit code, timeout flag, redacted 1500-character tails. `verify` does
  not re-run it. `fixtures/validate.py` refuses to run under any
  `sys.executable` other than `python_interpreter`.
- Load-time guards: a strict credential prescan over every byte of every
  probe's `seed/`, `oracle/`, `must-cover.json`, and `fixture.json`; the
  validator asserts each seed fails its oracle (except `rollup-hour-question`)
  and each `reference/` overlay passes it, and that the sanitizer is the
  identity over every fixture byte.
- Thinking is recorded, not pinned. Subscription billing only; no
  `ANTHROPIC_BASE_URL` bridge.
- `summary.json` `evidence_scope` is derived from the adapter so a live run
  is labelled as live (T-024; `04-harness-design.md`, section f).

## How the live run is dispatched and authorized

Two declarations bind this protocol. `campaign-synthetic.toml`, if present,
uses the offline `synthetic/1` adapter against placeholders under
`probes/*/synthetic/` and proves the lifecycle only. `campaign.toml` uses
`claude-code/2` and dispatches only when `exercise` is handed a
`clause-run-authorization/1` file whose `plan_sha256` equals the plan about to
run. The plan hash covers this file, every variant and probe tree (including
`oracle/`), the rubrics, `scripts/clause_campaign.py`, and
`scripts/final_message_scan.py`; an edit to any of them after authorization
refuses to dispatch.

**Authorization.** James's instruction of 2026-09-05, quoted verbatim in
`notes/2026-09-05-bakeoff11-council/00-brief.md:6-17` ("I give you full
authority for this run: run as many individual runs as you need"), is the
per-run paid-generation authorization the repository's safety rules require.
The chair, and only the chair, writes the `clause-run-authorization/1` file
quoting that instruction and naming the plan hash, once for each canary
declaration and once for the campaign declaration; council members make no
paid call.

```bash
C=campaigns/clause-bakeoff-11-2026-09-05
python3 scripts/clause_campaign.py exercise $C/campaign.toml \
  --run-dir $C/results/<run-id> --authorization $C/results/<run-id>-authorization.json \
  --deadline "2026-09-05T06:00:00-07:00"
python3 scripts/clause_campaign.py verify $C/results/<run-id>
python3 scripts/clause_judge.py run $C/results/<run-id> --judge codex --out $C/results/<run-id>-judge/codex
python3 scripts/clause_judge.py run $C/results/<run-id> --judge claude --out $C/results/<run-id>-judge/claude
python3 $C/analyze.py $C/results/<run-id> --judge-root $C/results/<run-id>-judge --out $C/results/<run-id>-analysis.json
```

The exact `--deadline` and `grade-partial` spellings are the harness
member's; the protocol binds the behaviour, not the spelling.

## Limitations, stated now

- **The tail lexicon overlaps the clauses' own words.** The council clause
  names "what changed" and "further work"; the vendor clause names
  "summary" and "caveats". Where a treatment lowers `tail_section_count`,
  the scan partly measures literal compliance with words the clause
  named; `bold_leadins`, `headings`, and the judged `unrequested-content`
  label are the backstops and are reported beside it (measures note 05,
  section 3, third check).
- **Regime.** Six Python-stdlib implementation tasks, one language, one test
  runner, one model, one operator, one night. Nothing transfers to essays,
  other languages, or interactive sessions where James answers back.
- **The clauses are measured only on DEP.** Their effect on A1 alone, or on
  any other file, is not measured; V1/C1-on-A1 exist as files and are not
  run. A result here is a property of "James's file plus this clause".
- **DEP placement and reachable paths.** DEP-based arms run as project memory
  in the workspace; on James's machine the file is user-scope memory, and
  user-scope placement on 2.1.258 has not been captured here. DEP names
  `~/.codex/capability-catalog.md`, `~/.agents/pstack-models.md`, and two
  absolute `agent-learning-inbox` paths (`~/.claude/CLAUDE.md:94, 119, 147,
  152`), which exist on the machine that runs the trials. A `Read`
  of them is possible and is recorded in `paths_outside_workspace`; a
  `python3` open of them is denied by the shim's profile. Either is a
  behaviour James's real sessions would also produce, since his file names
  the same paths.
- **`Bash(python3 *)` is not a sandbox; the shim is.** The allowlist is a
  prefix match on the command string and by itself stops nothing `python3 -c`
  can do. Containment comes from the `sandbox-exec` shim, the
  env allow-list, and a temp workspace outside `$HOME` and the repository.
  Residuals, stated rather than closed: the `claude` process itself holds
  `HOME` and its keychain login; bakeoff 9's profile allows `mach-lookup`, so
  a sandboxed python spawning `security` may still reach securityd, untested
  here (`06-red-team.md` B2, "Residual").
- **The env allow-list excludes `ANTHROPIC_MODEL` and
  `ANTHROPIC_DEFAULT_OPUS_MODEL`.** Bakeoff 9's T-014 showed those two are
  honoured end to end (`wayfinder/map.md`, T-014 decision); excluding them
  means this run cannot be redirected by the shell, and also that it does not
  reproduce any model-role override James's own shell may carry.
- **The Codex judge sees James's skill catalogue.** Codex reads the skills
  under `~/.agents/skills` regardless of `CODEX_HOME`
  (`reports/2026-09-02-clause-bakeoff-10.md:154-164`). Across the 56 skill
  directories present on 2026-09-05 the words "summary" appear 24 times,
  "outcome" 23, "brief" 12, and "concise" 2 (red-team count,
  `06-red-team.md`). None is a treatment-only 4-gram, so this is an isolation
  gap in the transport, disclosed, not a blinding break; the Sonnet judge's
  sessions see nothing of the kind.
- **A Codex outage yields a Sonnet-only report.** If judge one's transport
  fails on the night, judged measures are reported from Sonnet alone, the
  report is labelled single-judge, and the single judge shares a vendor with
  the generator; no judged rule is re-read as satisfied by one judge.
- **Cost and duration are cache-confounded.** `total_cost_usd` and
  `duration_sec` move with prompt-cache hits, `CLAUDE.md` length (DEP-based
  arms carry ~1000 more words than A1), worker concurrency, and time of
  night; they are reported per arm as operational figures and never as arm
  effects.
- **Blinding by construct.** Both treatments describe the shape the
  `unrequested-content` rubric rewards; a judge cannot tell arm from text,
  but rubric and treatment share a construct by design. The 4-gram audit
  rules out shared wording, not shared intent. A response that echoes clause
  wording would mark its arm; the post-run 4-gram count is reported.
- **The tail lexicon is a proxy.** A model that renames "Next steps" to a
  title outside the frozen list escapes `tail_section_count`; `bold_leadins`,
  `headings`, `tail_words`, and the judged `unrequested-content` class are the
  cross-checks, all reported per task. If a clause names a listed phrase
  verbatim, the scan measures compliance with the wording, and the report
  says so beside that number.
- **`tail_present` conditions offers on the oracle.** An offer on an
  oracle-failed trial does not count, so a clause that reduces offers only on
  failed work shows nothing in H1; the raw offer rate is reported beside it.
- **Five repetitions per cell** (three before amendment 2026-09-05b); see "What six tasks can show". A sparse
  baseline defect yields `indeterminate`, not `refuted`.
- **Judged classes are uncalibrated**; direction only; judge two shares a
  vendor with the generator.
- **Fixture vocabulary is constrained by the sanitizer.** Seeds avoid
  `token`, `secret`, `password`, `basic`, `bearer` and `*_key` identifiers so
  tool records are not refused (`03-fixture-plan.md:319-355`); the battery
  therefore cannot contain an authentication-flavoured task.
- **`claude-opus-5` is an alias.** The model behind it on the run date is
  recorded, not pinned.
- **Cost and time are assumptions** until the canary and the first repetition
  block complete; the deadline and the censoring ceiling protect the morning.
- **Multiplicity.** Two treatments, five hypotheses, no correction; the
  family-wise chance on H1 is stated above.
- **Canary and pilot trials are excluded from analysis** and from every base
  rate; they inform operations only, within the pre-registered scope above.

## Verification contract for this declaration

```bash
C=campaigns/clause-bakeoff-11-2026-09-05
python3 scripts/clause_campaign.py check $C/campaign.toml
# only if the offline declaration exists:
python3 scripts/clause_campaign.py check $C/campaign-synthetic.toml
run_dir="$(mktemp -d)/clause-bakeoff-11"
python3 scripts/clause_campaign.py exercise $C/campaign-synthetic.toml --run-dir "$run_dir"
python3 scripts/clause_campaign.py verify "$run_dir"
python3 -m unittest discover -s tests
( cd $C && python3 fixtures/validate.py )
```

Exit 0 on every command, 0 failures and 0 skipped in the unit suite,
`0 problems` from the validator, and bakeoff 10's sealed run still verifying
(`python3 scripts/clause_campaign.py verify
campaigns/clause-bakeoff-10-2026-09-01/results/run-2026-09-01`) are the
conditions for freezing this file.

## Amendments

**2026-09-05a — Canaries A and B; `--restricted` removed before any campaign
trial.** Canary A (`canary/`, plan `486f0264a670`, top-words-feature × A1, DEP,
M1; 3 trials, $0.58, 29–33 s each) and canary B (`canary-b/`, plan
`47a256534c47`, window-merge-suite × A1, DEP; 2 trials, $0.40, 30–32 s each)
ran at 04:17–04:30 MST. Every harness check held: `init` tools and permission
mode asserted per trial, answer model `claude-opus-5` only, zero permission
denials, oracle exit 0 in all five, reminder spans withheld (one, in canary B)
with the stream still sealed, final messages 43–76 words. Two findings changed
the harness, both inside the pre-registered canary scope:

1. **`--restricted` suppresses project `CLAUDE.md`.** A direct tool-less call
   on the pinned binary (Sonnet 5, $0.007) in a directory holding M1's
   `CLAUDE.md` returned `hello` with `--restricted` and `hello\nZQX-MARKER`
   without it. Canary A's M1 token had appeared only because the model Read
   its own `CLAUDE.md` after a `find` listed it (`claude_md_referenced` true
   in all three trials). Had the campaign run with the flag, the treatment
   would have reached the model only when it chose to read the file. The
   flag is removed from `claude-code/2`; file tools are no longer confined to
   the workspace by Claude Code, so `paths_outside_workspace` is the record
   of any excursion and the strict credential scan refuses a stream that
   carries a key shape. `claude_md_referenced` is reported per arm.
2. **Read-only shell commands are auto-approved under `acceptEdits`.** `find`
   and `ls -la` ran with no denial and, not being `python3`, outside the
   sandbox shim. Symmetric across arms; recorded. Canary C tests whether
   `dontAsk` with `Edit`, `Write`, and `Bash(python3 *)` allow rules denies
   them while edits and tests still run; the campaign uses whichever mode
   the canary shows to be tighter without breaking the task.

Cost and duration came in far below the planning number ($0.60, 3–6 min):
about $0.20 and 30 s per trial on both a medium and a hard probe.

**2026-09-05b — Canary C; permission mode fixed; repetitions raised to five.**
Canary C (`canary-c/`, plan `ab912484ee81`, top-words-feature × A1, M1 under
`dontAsk` with `Edit`, `Write`, `Bash(python3 *)` allowed, `--restricted`
removed; 2 trials, $0.32, 27–31 s) showed `find` still auto-approved with no
denial, so `dontAsk` adds no containment over `acceptEdits`, which also scopes
edits to the workspace. Without `--restricted` neither trial read its
`CLAUDE.md` (`claude_md_referenced` false) and M1's token still appeared, so
the file is injected as instructions. **Campaign configuration:**
`permission_mode = "acceptEdits"`, `allowed_tools = ["Bash(python3 *)"]`, no
`--restricted`; read-only shell commands that Claude Code auto-approves run
outside the shim and are recorded in `bash_commands`. **Repetitions: 5, not
3** (4 × 6 × 5 = 120 trials). Basis: seven canary trials cost $0.16–0.22 and
ran 27–33 s each against a planning number of $0.60 and 3–6 minutes, so five
repetitions fit the same budget and window with margin. Everything else in
"Hypotheses and verdict rules" is unchanged; `n` per arm becomes 30, the P0
floor `n/3` becomes 10 of 30, and the harm tolerance stays two trials. What
the canaries showed about outcomes, stated so it cannot be mistaken for
tuning: seven final messages (A1, DEP, M1 on two probes) carried no tail
section and one `closing_offer`-shaped sentence ("Say the word if you want it
clamped", M1, not in the frozen OFFER list); oracles passed 7 of 7. P0 may

**2026-09-05c — Deadline passed before dispatch; run re-materialized.** The
declared dispatch deadline of 06:00 MST (13:00Z) was reached before the first
campaign trial: the design and harness phase overran (the council's harness and
red-team agents were cut off by an account spend limit at about 03:50 MST and
the chair completed the adapter, canaries, and freeze alone), and the chair's
running log under-estimated the clock from about 02:30 onward. At 07:30 MST
`exercise` refused every case ("deadline reached; 120 trial(s) not dispatched
and 0 failed or censored") and left only `plan.json` and `authorization.json`,
preserved under `results/run-2026-09-05-attempt1/`. No model response was
produced or retained. Change: the run is dispatched at 07:3x MST with a new
deadline of 09:30 MST (16:30Z); the rule's purpose, balanced repetition blocks
under a wall clock, is unchanged, and nothing else in the design moves. The
plan is re-materialized because this file is hashed into it, and a new
authorization file names the new plan hash.
therefore fail on DEP; the rules already say what is then reported.

