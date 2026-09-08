# Clause bakeoff 10 — the writing-density instruction on Opus 5

Date: 2026-09-01 (America/Phoenix)
Status: **declared, not run.** Frozen by `campaign.toml`, which binds this
file by sha256. No generation, judge, or other paid call has been made.
Requested by James on 2026-09-01: test whether the Fable 5.1 prompting
guide's writing-density additions work as `CLAUDE.md` clauses for Opus 5.

## Questions

1. **Primary.** Does adding the "writing density" instruction from
   Anthropic's *Prompting Claude Fable 5.1* page to the deployed `CLAUDE.md`
   make Opus 5's long-form technical prose less dense: shorter sentences, more
   paragraph breaks, and less mannered prose?
2. **Secondary.** Does the page's short form, "Please remove all mannered
   prose.", do the same?
3. **Harm.** Does either addition inflate total length or drop required
   content?

## Why this is a question and not a lookup

The instruction is published for Claude Fable 5.1 and Claude Mythos 5.1
(source S039). The page describes a Fable 5.1 behavior, prose "denser than
Claude Fable 5's", and offers the instruction as the mitigation. James deploys
Opus 5. Anthropic's *Prompting Claude Opus 5* page (S040) has a section on
response length whose recommendation is a conciseness instruction; it says
nothing about sentence length, paragraph breaks, or mannered prose. Neither
page implies that an instruction tuned to another model's failure mode moves
Opus 5, in either direction. That is the gap this campaign measures.

Length is not the construct here. Bakeoff 8 already measured A1 against a blank
slate and found a 15.6% word reduction. The density instruction targets the
shape of the prose, not its amount, and the harm criterion below checks that it
does not change the amount.

## Prior evidence, mined before any new call

Bakeoff 8 (2026-08-14, Claude Code 2.1.232 pinned, Opus 5 High, no tools,
single turn) produced 25 responses under a `CLAUDE.md` byte-identical to this
campaign's A1 arm, on the same five prompts this campaign reuses. Re-measured
on 2026-09-01 with the rules in `scripts/prose_density.py`:

```bash
python3 scripts/prose_density.py \
  campaigns/clause-bakeoff-8-2026-08-11/out/bakeoff-20260814T055452Z/responses/*/response.json
```

Per-response values are retained in
`sources/2026-09-01-bakeoff8-density-base-rates.json` (S041). Medians over
the 25 A1 responses, with the spread that sets what this design can see:

| Measure | Median | Mean | SD | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| mean words per sentence | 18.36 | 18.36 | 2.03 | 14.00 | 23.98 |
| mean words per paragraph | 41.71 | 47.36 | 18.57 | 21.00 | 87.64 |
| words | 994 | 1075 | 277 | 703 | 1806 |

Within-task SD across the five repetitions ranged 0.82–2.12 words per
sentence and 4.82–12.34 words per paragraph. One task,
`retry-storm-interaction`, had a median of 83 words per paragraph and no list
items; the other four sat between 32 and 46.

Bakeoff 8's blank-slate control (n=25) had medians of 17.33 words per
sentence and 41.95 per paragraph, so A1 did not itself change sentence or
paragraph shape relative to no clause; it changed length. That is consistent
with A1 being the right baseline for a shape question.

Limits of this evidence: a different CLI build and an earlier date, so the
model behind `claude-opus-5` may have moved; and the measures are structural
proxies, not a judgment of mannered prose, which no prior campaign labeled.

## Arms

The only artifact that differs between arms is `CLAUDE.md`. The live
`~/.claude/CLAUDE.md` is never read at run time.

| Arm | `CLAUDE.md` | sha256 (first 12) |
| --- | --- | --- |
| **A1** `a1-response-numbers` | Response style + Numbers; byte-identical to bakeoff 8's `composite` and bakeoff 9's A1 | `f70f86a92e9f` |
| **D1** `d1-density-long` | A1 + `## Writing density` + the page's full instruction | `9999bb6ce4ba` |
| **D2** `d2-density-short` | A1 + `## Writing density` + "Please remove all mannered prose." | `22e6ed466826` |

The instruction texts are verbatim from S039; the only addition is the section
heading, which every other section in A1 also carries. The bare texts are kept
as `variants/density-clause-long.md` (`ac9a4c824c15`) and
`variants/density-clause-short.md` (`a0ad6bd1c93e`) so the diff D1−A1 and
D2−A1 can be checked byte for byte.

Placement. The page prefers a user message over the system prompt. On the
pinned Claude Code builds captured in bakeoff 9, project `CLAUDE.md` content is
delivered inside the `<system-reminder>` in `messages[0]`, beside the task
prompt, which is the user-message placement. This campaign does not vary
placement.

## Design

3 arms × 5 probes × 5 repetitions = 75 responses, the same shape and count as
bakeoff 8. Sample size is reported as **five distinct tasks**; repetitions are
within-task observations.

Probes are bakeoff 8's five prompts, reused verbatim including their frozen
closing line ("Answer from the information in this message; do not inspect
files or use tools."). Reuse is deliberate: it is what makes the prior evidence
above a base rate rather than an analogy. Each probe carries its bakeoff 8
`must_cover` list in `must-cover.json`, which the coverage rubric reproduces.

The task regime is tool-less and single-turn, like bakeoffs 1–8 and unlike
bakeoff 9. Nothing here transfers to agentic sessions.

## Instruments

**Deterministic**, computed by `scripts/prose_density.py` from the stored
response text and recomputable by anyone with the run directory:

| Measure id | Grader | Maximum | Why this number |
| --- | --- | ---: | --- |
| `sentence-length` | `max_mean_sentence_words` | 18 | A1 base-rate median 18.36; 12 of 25 A1 responses pass |
| `paragraph-length` | `max_mean_paragraph_words` | 42 | A1 base-rate median 41.71; 13 of 25 pass |
| `length-cap` | `max_words` | 1093 | 110% of A1's base-rate median, bakeoff 8's harm rule |

The pass/fail splits are descriptive. The primary contrast reads the retained
per-trial observations in `grades.json` (`mean_sentence_words`,
`mean_paragraph_words`, `words`) as medians by arm, paired by task. Rules:
fenced code is removed; headings and table rows are skipped; a list item is its
own block; sentence mean is over paragraphs and list items; paragraph mean is
over paragraphs only, so a bulleted answer cannot satisfy it by construction.

**Judgmental**, one blind task per response per measure, exported without
variant or trial identity:

| Measure id | Question | Labels |
| --- | --- | --- |
| `mannered-prose` | Does the response contain mannered prose, as the rubric defines it? | `none` / `present`, with excerpts |
| `coverage` | Does the response cover every required idea for its question? | `complete` / `incomplete`, with the missing ideas |

Judges: two non-Anthropic vendors, blind to arm and to each other, reported
separately and never averaged, the rule carried from bakeoff 9. The vendors and
model identifiers are chosen at run authorization and recorded then; they are
not frozen here because no reference set exists for these two label classes.
Without a frozen reference the judgmental measures are **reported, not
gated**; a gate needs its own prospectively frozen reference and agreement
thresholds, as bakeoff 9 required.

## Hypotheses and verdict rules, committed before any run

For each hypothesis the verdict is `supported`, `refuted`, or `indeterminate`.
"Task medians" means the median over five repetitions within a task; "pooled
median" means the median over all 25 responses in an arm. Direction is D minus
A1 on the same task.

- **H1, the full instruction reduces density (D1 vs A1).** `supported` when
  the task median of *both* mean sentence words and mean paragraph words is
  lower in D1 than A1 on all five tasks, and the pooled median of each falls at
  least 10% relative. `refuted` when the pooled median of either measure rises,
  or falls less than 5% relative with the task medians split 3–2 or worse.
  Otherwise `indeterminate`.
- **H2, the short instruction reduces density (D2 vs A1).** Same rule as H1.
- **H3, mannered prose is judged less often.** `supported` when the `present`
  rate is lower in D1 than in A1 for both judges. **Power check, decided
  first:** if fewer than 5 of 25 A1 responses are labeled `present` by either
  judge, the battery did not provoke the defect and H3 is reported
  `indeterminate (underpowered)`, never as a null. This mirrors bakeoff 8's
  coinage rule, which fired.
- **H4, no harm.** For each of D1 and D2: pooled median words at or below 110%
  of A1's pooled median, and the `incomplete` rate not above A1's for either
  judge. Either failure makes that arm `refuted` on harm regardless of H1/H2.

**What five tasks can show.** With A1's within-task SD near 1–2 words per
sentence and 5–12 per paragraph, a 10% shift (about 1.8 and 4.2 words) is on
the order of one within-task SD; five repetitions per cell put the task median
close enough to read direction, and consistency across all five tasks is the
evidence, not a confidence interval. No interval is claimed. A same-direction
result on all five tasks has a one-sided sign-test probability of 1/32 under
no effect; that is the whole of the inferential claim.

**Stopping rule.** 75 responses, fixed. No interim look, no extension on a
near miss, no substitute judge after seeing labels.

## Environment freeze for the live run

Declared now so the run has nothing left to decide; recorded at run time in
the results manifest.

- Generator: Claude Opus 5 (`claude-opus-5`), effort high, **no tools**,
  single turn, one fresh project directory per response outside `$HOME`, no
  session persistence. `settingSources: ["project"]` and
  `settings: {"autoMemoryEnabled": false}` for the reasons bakeoff 9 records.
- Claude Code pinned as a **binary copy**; version and sha256 recorded per run,
  checked before every response, stop on change (the bakeoff 1–8 rule).
- Thinking is recorded, not pinned: the pinned build's default runs and the
  request's `thinking` and `output_config` are captured per trial.
- Subscription billing only; no `ANTHROPIC_BASE_URL` bridge. **Every live run
  needs James's explicit per-run authorization**, separate from this
  declaration.
- Cost reference, recorded not estimated: bakeoff 8's 75 responses cost
  $10.30 in total (`total_cost_usd`, median $0.135, max $0.18). Current
  pricing may differ.

## How the live run is dispatched

Two declarations bind this protocol. `campaign-synthetic.toml` uses the
offline `synthetic/1` adapter against the placeholders under
`probes/*/synthetic/`; it proves the lifecycle and nothing about a model, and
its summary is labelled `synthetic-integration-only`. `campaign.toml` uses the
`claude-code/1` adapter (T-023, resolved 2026-09-01): one isolated, tool-less,
single-turn print-mode session per trial on the pinned binary copy, dispatched
only when `exercise` is handed a `clause-run-authorization/1` file whose
`plan_sha256` equals the plan it is about to run. The plan hash covers the
declaration, the protocol, every variant and probe tree, and the harness
source, so an edit to any of them after authorization refuses to dispatch.

## Limitations, stated now

- Blinding is imperfect. The mannered-prose rubric shares its definition with
  the D1 clause; a response that echoes the clause's own wording could
  identify its arm to a judge. Recorded as a limitation, not claimed as clean.
- The structural measures are proxies. Sentence and paragraph means move with
  formatting choices as well as prose style; a shift to more list items lowers
  the sentence mean and removes text from the paragraph mean. The retained
  `items` and `paragraphs` counts are reported beside every result so that
  a formatting shift is visible rather than mistaken for a density shift.
- Base rates come from a different CLI build and date. Thresholds are
  descriptive splits; if A1's live pooled medians land far from the base rates,
  the splits stay as declared and the arm contrast, which does not depend on
  them, still reads.
- No reference set calibrates the two judged classes, so they cannot gate.
- Five tasks, all long-form systems questions in English. The result does not
  generalize past that battery.
- The Fable 5.1 page recommends the instruction for a Fable 5.1 behavior. A
  null on Opus 5 says nothing about Fable 5.1, and a positive result does not
  make the page's claim a claim about Opus 5.

## Verification contract for this declaration

```bash
C=campaigns/clause-bakeoff-10-2026-09-01
python3 scripts/clause_campaign.py check $C/campaign-synthetic.toml
run_dir="$(mktemp -d)/clause-bakeoff-10"
python3 scripts/clause_campaign.py exercise $C/campaign-synthetic.toml --run-dir "$run_dir"
python3 scripts/clause_campaign.py verify "$run_dir"
python3 scripts/clause_campaign.py check $C/campaign.toml
python3 -m unittest discover -s tests
```

The synthetic placeholders are shaped so the three deterministic measures
demonstrably move independently (A1 placeholder fails sentence and paragraph
splits; D1 passes both; D2 passes sentence and fails paragraph). That
demonstrates the graders, not the clause.

The live run, once authorized:

```bash
python3 scripts/clause_campaign.py exercise $C/campaign.toml \
  --run-dir $C/results/<run-id> --authorization $C/results/<run-id>-authorization.json
python3 scripts/clause_campaign.py verify $C/results/<run-id>
```

## Amendments

**2026-09-01a — Live adapter and declaration split.** Written before any
generation call. `scripts/clause_campaign.py` gained the `claude-code/1`
adapter described above, so the section that said the campaign could not run
is replaced by the dispatch description. The offline proof keeps its own
declaration so it stays runnable after the live one is frozen.

**2026-09-01b — Judges frozen.** The Instruments section left the vendors to
run authorization. They are:

| Judge | Model | Transport | Vendor |
| --- | --- | --- | --- |
| one | `gpt-5.6-sol`, reasoning effort high | Codex CLI 0.147.0, the bakeoff 8 pinned copy at `~/.claude-eval-pins/bakeoff8/codex`, ChatGPT subscription auth, schema-constrained output | OpenAI |
| two | Claude Sonnet 5, effort high | the bakeoff 10 pinned Claude Code binary, print mode, `--json-schema`, no tools | Anthropic |

This deviates from the "two non-Anthropic vendors" rule carried from bakeoff
9, and the reason is recorded rather than hidden: on the machine that runs
this campaign the only non-Anthropic inference credential is the Codex
subscription. James ruled out Google on 2026-08-28, and no Z.ai key is
present. Judge two therefore shares a vendor with the generator, the same
pairing bakeoff 8 used. Consequences: the H3 and H4 rules still read both
judges as written; each judge is reported separately, never averaged; the two
judges' agreement is reported per class; and where the judges disagree on
direction, the report says so and does not pick one. Each judge sees one
task at a time: the measure's question, its rubric, the task prompt, and the
response, with no arm, trial, or campaign identity. A judged result is
admissible only when the transport's own record resolves to the frozen model
identifier (the Codex rollout's `turn_context.model`; the Claude stream's
assistant `model`).

**2026-09-01c — Pin and run parameters.** Claude Code `2.1.258 (Claude Code)`,
the live CLI on this date, copied to `~/.claude-eval-pins/bakeoff10/claude`,
sha256 `b63136194160791c27cfa7b0403060d85eb0752991625fde8c09f9acacb17c78`.
Three concurrent trials, 600-second timeout per trial. A single loopback-free
smoke call with the exact campaign flags confirmed on 2026-09-01 that this
build accepts them and reports `claude-opus-5` as the answer model.

**2026-09-01d — Attempt 1 discarded before any response existed.** James
dispatched the authorized plan (`b8565f6599fc…`) at 05:16 UTC on 2026-09-02.
The first ten trials the pool ran (A1 on `entitlement-drift-mechanism` and
`retry-storm-interaction`) all failed, each recorded as "stream carries
credential-shaped or reminder text; not retained", and the run stopped on the
failure fraction. All ten failures were recorded within one second of each other, which no
completed Opus 5 trial can produce, so the streams were almost certainly
error output rather than answers. The guard ran before the exit-code and
result-status checks and kept no diagnostic, so **the cause is not
established**: a local reproduction of one trial with the same flags
succeeded, and bad-key, logged-out, and nested-session probes did not
reproduce an instant exit-0 stream. The ten failure records and the plan they
belong to are preserved under `results/run-2026-09-01-attempt1/`.

The guard itself was also wrong for model prose. It applied the capture
spine's full sanitizer, whose patterns key on words such as `secret`,
`password`, `authorization`, and `*-key`, to the answer text. Over bakeoff
8's 75 stored responses that sanitizer rewrites 6, all on
`terms-of-art-explainer`, where the answer shows an `Idempotency-Key:` header.
Left as it was, the guard would have discarded legitimate answers on that
task in every arm.

Change, before any retained response exists: response text (the trial's
`output.text`, the blind export's `response`, and the retained stream) is
scanned for unmistakable credential shapes only (Anthropic key prefix,
bearer or basic authorization values, GitHub and AWS token shapes, private
key headers), because a tool-less session whose inputs carry no credential
cannot leak one; every other stored field keeps the full sanitizer. The
adapter checks exit code, stream validity, result status and model identity
before that scan, keeps a sanitized stdout and stderr tail in every failure
record, and still refuses a stream carrying a reminder payload. Because the
plan hash covers the harness source, the plan is re-materialized and
re-authorized. No model response was retained in attempt 1, so no analysis
input changed; the ten discarded responses cost roughly ten trials' worth of
generation.

**2026-09-01e — Attempt 2 discarded; cause established.** James dispatched
the re-materialized plan (`8bbccf9ffc7f…`) at 05:33 UTC on 2026-09-02. The
first ten trials failed within one second with exit 1, and the tails the
amended adapter kept show the same result event on every one:
`api_error_status: 401`, "Failed to authenticate. API Error: 401 Invalid
bearer token". The pinned binary completes the same call from an interactive
shell on its keychain login, so the dispatching shell supplied a credential
the API rejected; attempt 1's instant failures were almost certainly the same
event, hidden by the old guard. Records are preserved under
`results/run-2026-09-01-attempt2/`.

Change, before any retained response exists: the adapter removes
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and
`CLAUDE_CODE_OAUTH_TOKEN` from the child environment, so the run bills the
subscription login the pinned binary holds and no key or base URL in the
dispatching shell can change who pays or where calls go (the repository's
subscription-only rule, now enforced by construction). The names of the
variables removed, never their values, are recorded per trial as
`generation.stripped_env`. A 401 result is classified as an authentication
failure, which stops the run on the first trial instead of the tenth. The
plan is re-materialized and re-authorized; no model response was retained in
attempt 2.

**Authorization.** James wrote "You have my approval for all." on 2026-09-01
in the session that declared this campaign, after the declaration and its
open items (live adapter, generation, judging, commit) were reported to him.
The authorization file for the run quotes that sentence and names the plan
hash; it is the per-run authorization the safety rules require.
