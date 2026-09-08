# Opus 5 social-language scan and draft test bed

Date: 2026-08-24

## Readout

The complaint is real, but "Opus 5 is verbose" is too blunt to evaluate well.
The stronger description is **length and language miscalibration**. Bad cases
bury a usable answer under framing, narration, caveats, and adjacent work. They
also compress ordinary ideas into private shorthand, multi-clause sentences,
or metaphor-heavy engineering language that makes the reader translate the
answer back into concrete steps.

The defect is not uniform. Opus 5 can produce proportional short answers, and
some users prefer its density on difficult work. One roughly 10,000-message
personal analysis even found a shorter median Opus 5 reply than Opus 4.8, 98
versus 148 characters, alongside a worse extreme tail: 2.7% versus 1.7% above
5,000 characters. That pattern matches this project's preserved outputs. One
neutral prompt produced 29, 630, and 1,266 words across three control
repetitions; the short result was a non-answer, while the longest exposed about
100 planning lines before answering. [Broad-web ledger](../sources/social-scan-2026-08-24/broad-web.md),
[local skeptic pass](../sources/social-scan-2026-08-24/skeptic-local.md)

The supported claim is narrow: multiple named users report a recognizable
Opus 5 response-style problem, Anthropic acknowledges longer default answers
and more narration, and preserved local outputs show the same heavy-tail
failure. How often it happens, and how much comes from model weights rather
than Claude Code, effort, session depth, loaded instructions, or product
surface, remains indeterminate.

## Evidence map

The platform ledgers preserve six direct X reports, eleven direct Reddit
reports, and eleven forum or developer-source reports. They are reports of
experience, not independent prevalence samples. Authors may share examples and
language, and several broad-web entries overlap the forum ledger. [X ledger](../sources/social-scan-2026-08-24/x.md),
[Reddit ledger](../sources/social-scan-2026-08-24/reddit.md),
[forum ledger](../sources/social-scan-2026-08-24/forums.md)

The most useful examples are concrete:

- A short question about an email open rate reportedly triggered a wall of
  text containing `MPP`, send-time optimization, geo data, and IP masking
  without explanations. [X-01](https://x.com/0xHuge/status/2092100577144496626)
- A Reddit author preserved output that described deleted records and failed
  jobs through `tombstone`, `retry-path`, and `dead-letter` language rather
  than naming the behavior directly. [Reddit R10](https://www.reddit.com/r/ClaudeCode/comments/1vun6ca/a_fix_for_opus_5s_nonsense_output_the_plain/)
- A Hacker News user asked how an existing application feature worked and got
  seven correct paragraphs where a scannable explanation would have done.
  [Forum F-HN-02](https://news.ycombinator.com/item?id=49421935)
- A Claude Code issue reports roughly 600 words of framing, questions, and
  model-user meta-commentary before a direct writing request was attempted.
  [Forum F-GH-02](https://github.com/anthropics/claude-code/issues/87491)
- A public benchmark on plausible nonsense recorded 1,141 Opus 5 low-effort
  output tokens versus 550 for Opus 4.8 with thinking disabled, corrected by
  its author to roughly 60% more words because the tokenizers differ.
  [Forum F-GH-01](https://github.com/anthropics/claude-code/issues/83510)

Anthropic's own material supports the length half of the complaint. Its Opus 5
guide says default visible answers, agentic messages, and written deliverables
run longer than earlier Opus models. The system card adds exhaustive
verification, correction loops, dramatic retractions, scope creep, and
over-engineering. Anthropic does not identify invented jargon or abstract
diction as an Opus 5-specific defect. [Official context](../sources/social-scan-2026-08-24/official-context.md)

The product boundary matters. Claude.ai's published Opus 5 system prompt
already contains concision instructions; the API does not receive that prompt;
Claude Code supplies its own agent harness and project instructions. A social
post that says only "Opus 5" rarely records enough context to isolate the
model. [Official context and surface boundary](../sources/social-scan-2026-08-24/official-context.md)

## Defect taxonomy

| Defect | Observable behavior | What is not automatically a failure |
| --- | --- | --- |
| Answer burial | The result, recommendation, or next action arrives after framing, background, or a plan. | Necessary safety context that changes the action. |
| Heavy-tail length | Some ordinary prompts produce essay-scale answers or many sections, even when the median is reasonable. | A long answer to a genuinely broad task. |
| Private vocabulary | The answer introduces compounds, labels, or metaphors as if the reader already shares them. | Established terms of art used for the right audience and defined when needed. |
| Abstraction compression | A short phrase hides several concrete steps and must be translated before the reader can act. | A precise abstraction that reduces reader effort. |
| Dense sentence packing | One sentence carries several causal claims, decisions, or caveats and requires rereading. | Length alone; some long sentences remain clear. |
| Performative framing | The answer sounds like a keynote, courtroom scene, social post, or staged revelation. | A useful analogy that makes the mechanism clearer. |
| Working-thought leakage | Visible self-correction, planning, tool narration, or private shorthand competes with the final answer. | A short progress update when the user needs it. |
| Scope spill | A narrow question grows into an architecture program, verification campaign, extra fixes, or unsolicited alternatives. | One adjacent risk that materially changes the recommendation. |
| Style relapse | A request for plain language repairs one turn, then the next answer returns to the prior register. | A later task that legitimately requires more detail. |

This taxonomy explains why word count alone is a bad primary grader. A 29-word
non-answer can be worse than a 300-word complete answer. The target is avoidable
reading cost without loss of correctness, nuance, safety, or useful detail.

## Ten prompt examples

The machine-readable draft is
[`config/social-language-test-bed-2026-08-24.jsonl`](../config/social-language-test-bed-2026-08-24.jsonl).
These are candidates, not a frozen eval dataset. None asks the model to be
brief or bans jargon. All ten are single-turn, no-tool prompts. They do not
measure style relapse across turns or live progress narration during tool use;
those need separate multi-turn and agentic slices.

Prompts 6, 8, and 9 also bound the requested output to one finding, one first
measurement, or a three-part decision. They test whether the model respects a
natural scope instruction. They do not measure unconstrained baseline length.

### 1. Explain an existing feature

> An admin selects invoices, clicks Export, and receives a CSV file by email.
> Exports under 10,000 rows are generated immediately. Larger exports are
> queued, and the email arrives when the file is ready. If the email is
> delayed, the same file is available on the Downloads page. Explain to a
> customer-support specialist what happens when a user clicks Export.

Targets answer burial, unnecessary architecture, and renamed concepts.

### 2. Switch release channels

> Our desktop app has Stable and Preview update channels. A user is on Preview
> version 8.4.0, and Stable has now reached the same version. Switching
> channels changes only the update feed; it does not remove settings,
> extensions, or projects. The control is at Settings > Updates > Channel.
> Tell the user how to return to Stable and what will happen to their data.

Targets compressed platform language, caveat sprawl, and completion narration.

### 3. Explain a business metric change

> A newsletter's click-through rate fell from 4.8% to 3.9% after one major
> mail client began stripping tracking parameters. Purchases attributed from
> email stayed flat, and total purchases also stayed flat. Explain to a
> marketing manager what the numbers most likely mean and name the next check
> that would separate a tracking problem from a real engagement drop.

Targets audience mismatch, acronym pileup, and dense causal sentences.

### 4. Execute a direct writing request

> Turn these notes into a first-person internal post about trying a new
> reporting tool: the generated report was useful; initial setup took 40
> minutes; a misleading permission error sent me to the wrong settings page;
> once the workspace owner granted the correct permission, the report ran
> without further changes; my recommendation is to fix the error message
> before rolling the tool out to the rest of the company. Write the post I
> should publish.

Targets meta-commentary, reframing, unnecessary questions, and staged prose.

### 5. Reject a plausible nonsense premise

> An API has a 250 ms latency budget and an 80% cache-hit rate. A proposal says
> the system therefore has a "cache entropy" of 0.2 and a latency uncertainty
> of 50 ms, using entropy in the same way as thermodynamics. Is that reasoning
> valid? Explain what can and cannot be calculated from the facts given.

Targets elaborate treatment of a false premise and decorative abstraction.

### 6. Review one real code defect

> Assume `check()` returns promptly and does not block. Review this function
> for the one correctness problem that could make its timeout behave
> incorrectly, and give the smallest fix.
>
> ```python
> import time
>
> def wait_until_ready(check, timeout):
>     deadline = time.time() + timeout
>     while time.time() < deadline:
>         if check():
>             return True
>         time.sleep(0.1)
>     return False
> ```

Targets nitpick volume, full rewrites, and theatrical review language. The
intended finding is the wall clock; elapsed time should use `time.monotonic()`.

### 7. Report a bounded completed change

> Write the message I should send to a teammate after this change: the parser
> now accepts a quoted field containing the delimiter; 42 parser tests pass;
> the type checker passes; no documentation changed; nothing was deployed;
> escaped backslashes inside quoted fields remain unsupported and are tracked
> separately. State whether the change is ready for review.

Targets handoff sprawl, repeated verification, and invented internal labels.

### 8. Diagnose one regional stall

> Jobs in one region sometimes pause for almost exactly 60 seconds. The
> application log shows "job received," then no entries, then the first
> database query. Queue depth is normal. A feature flag that routes credential
> lookup to a regional secrets endpoint was enabled in that region yesterday.
> What is the leading hypothesis, and what first measurement would best test
> it?

Targets hypothesis trees, jargon piles, and troubleshooting-manual expansion.

### 9. Make a bounded architecture choice

> Four services owned by one team each run two periodic jobs. The team wants
> one place to see missed runs and execution history. The jobs are already
> idempotent. There is no platform team to operate new shared infrastructure.
> Should the team keep scheduling inside each service or add a central
> scheduler? Give a recommendation, the strongest trade-off, and the condition
> that would make you revisit it.

Targets invented taxonomies, unsupported thresholds, and migration-plan spill.

### 10. Preserve necessary technical vocabulary

> Explain to a backend engineer how MVCC, snapshot isolation, and write skew
> relate in a PostgreSQL-like database. Use a two-doctor on-call example in
> which each transaction sees the other doctor on call and takes one doctor
> off call. Then explain what serializable isolation changes.

This is the falsifier. A treatment should not avoid or replace the requested
terms. It should define them in context and keep the explanation proportional.

## How to run the battery

Use the same prompt, model snapshot, effort, harness, tool surface, repository
instructions, and conversation state across arms. Compare a no-style-clause
baseline with the candidate clause. Do not substitute a low-effort arm for a
concision arm; Anthropic says effort does not reliably control visible answer
length.

Run at least three repetitions per prompt and report the distribution plus an
extreme-tail rate, not just the median. Separate progress narration, written
artifacts, and final responses. Record model ID, CLI or API version, product
surface, effort, thinking state, system prompt or preset, loaded instruction
files, output style, and session depth.

Prefer deterministic measurements for word count, paragraph and heading
counts, repeated sentences, position of the first requested action, and terms
introduced by the response but absent from the prompt. Use a blind comparative
rubric for the judgments that require interpretation:

1. Could a passage be removed without changing correctness, safety, or the
   reader's next action?
2. Is a technical term useful for this audience, and is it defined before the
   answer relies on it?
3. Does the answer introduce a frame, metaphor, or taxonomy that makes the
   decision clearer?
4. Does a sentence pack several claims that would be easier to evaluate
   separately?
5. Did the answer expand the requested task?

Grade task completion, factual correctness, nuance, safety, and invented
precision separately. A shorter arm fails if it omits necessary material. A
jargon-reduction arm fails if it replaces precise domain language with vague
prose on the technical-vocabulary falsifier.

## Verdicts and limits

- `supported`: multiple public authors explicitly attribute answer burial,
  low information density, dense prose, private shorthand, and scope spill to
  Opus 5.
- `supported`: Anthropic documents longer default visible answers, more
  narration, longer deliverables, over-verification, and scope expansion.
- `supported`: this project's preserved Opus 5 outputs show severe tail
  variance, narration, excess structure, and occasional undefined shorthand.
- `refuted`: Opus 5 is uniformly verbose or uniformly jargony.
- `indeterminate`: prevalence and attribution to model weights rather than
  product surface, harness, prompt, effort, or session context.

Public discussion is concentrated around launch and selected failures. Most
posts omit the raw prompt, raw answer, exact model ID, system prompt, and
configuration. The examples are good enough to design fixtures. They are not
good enough to estimate how often an ordinary Opus 5 response fails.

## Supporting ledgers

- [X scan](../sources/social-scan-2026-08-24/x.md)
- [Reddit scan](../sources/social-scan-2026-08-24/reddit.md)
- [Forum and developer-source scan](../sources/social-scan-2026-08-24/forums.md)
- [Broad-web scan](../sources/social-scan-2026-08-24/broad-web.md)
- [Official Anthropic context](../sources/social-scan-2026-08-24/official-context.md)
- [Skeptic and local-evidence pass](../sources/social-scan-2026-08-24/skeptic-local.md)
- [Frozen preregistration](../notes/2026-08-24-opus5-social-language-scan-preregistration.md)
