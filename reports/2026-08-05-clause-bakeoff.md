# Opus 5 Response-Clause Micro-Bakeoff

**Repository:** a private research monorepo  
**Project:** [Opus 5 STE verbosity evaluation](../README.md)  
**Frozen protocol:** [Clause bakeoff protocol](../campaigns/clause-bakeoff-2026-08-05/protocol.md)  
**Evaluation code:** [Promptfoo configuration](../campaigns/clause-bakeoff-2026-08-05/promptfooconfig.yaml), [Opus provider](../campaigns/clause-bakeoff-2026-08-05/provider.py), [blind grader](../campaigns/clause-bakeoff-2026-08-05/analyze.py)  
**Benchmarking data:** [Tasks and required ideas](../campaigns/clause-bakeoff-2026-08-05/tasks.jsonl)  
**Candidate clauses:** [original STE](../campaigns/clause-bakeoff-2026-08-05/variants/ste.md), [complete recipe](../campaigns/clause-bakeoff-2026-08-05/variants/complete-recipe.md), [adaptive recipe](../campaigns/clause-bakeoff-2026-08-05/variants/adaptive-recipe.md)  
**Results:** [Machine-readable summary](../campaigns/clause-bakeoff-2026-08-05/out/bakeoff-20260805T054208Z/bakeoff-results.json), [raw run artifacts](../campaigns/clause-bakeoff-2026-08-05/out/bakeoff-20260805T054208Z/)  
**Related evaluation:** [Original STE confirmatory campaign](2026-08-05-confirmatory-campaign.md)  
**Presentation:** None  
**Dashboard:** None

**Document version:** 1.0.0  
**Owner:** Agent Systems Research maintainers  
**Evaluation date:** 2026-08-05  
**Deployment status:** N/A — no clause was approved for deployment

## Executive Summary

### Context

The original ASD-STE100-inspired clause made Opus 5 answers shorter and easier
to read, but the larger confirmatory study found worse blind preference,
reduced nuance and safety, material errors, and missing requirements. We ran
this exploratory micro-bakeoff to test whether a positive response recipe could
keep the clarity benefits without instructing the model to optimize brevity at
the expense of useful content.

### Findings

- **No candidate passed the frozen safety gates. Do not deploy any tested
  clause.** Every candidate had at least one judged material error.
- `complete-recipe` was the strongest direction. It beat control in 10 of 13
  non-tied comparisons and improved mean nuance/safety by 1.2 points, but it
  had three material errors and increased median length by 66%.
- The original STE clause performed better than it did in the confirmatory
  campaign, but still had five material errors. This small battery does not
  overturn the confirmatory rejection.
- `adaptive-recipe` produced a 77% lower median word count only because many
  responses were incomplete. It is an example of why brevity must remain a
  tiebreaker rather than the main objective.
- All arms sometimes tried to inspect an empty project instead of answering.
  This agent-mode behavior makes the three-task battery too noisy to approve a
  writing clause without a larger holdout and human review.

### Recommendation

Keep the positive completeness approach, but shorten it before the next test:

> Start with the answer or next action. Include the facts, uncertainty, safety
> checks, validation, and rollback needed for a correct result. Use plain words
> and explain a necessary technical term once. Remove repetition and background
> that does not change the decision or action.

Run this as a new candidate against control on fresh tasks. Add a preflight gate
that rejects a run if an answer stops at attempted project inspection. If the
candidate passes the micro-battery, move it to a larger frozen holdout with
human review. Do not reinterpret this run as approval for `complete-recipe`.

## Project Overview

### Evaluation question

Can a positive response recipe preserve the original STE clause's clarity and
brevity gains without its losses in preference, nuance, safety, and required
content?

### Candidates

| Arm | Clause strategy | Reason for inclusion |
| --- | --- | --- |
| `control` | No project `CLAUDE.md` | Measures raw Opus 5 High behavior |
| `ste` | Exact original ASD-STE100-inspired treatment | Tests whether the earlier failure reproduces |
| `complete-recipe` | Preserve correctness and safety, then remove repetition | Tests a positive completeness rule |
| `adaptive-recipe` | Increase detail for observable risk conditions | Tests task-dependent detail without a universal word limit |

### Hypotheses

1. `complete-recipe` will beat control more often than `ste` while avoiding
   material errors and increased omissions.
2. `adaptive-recipe` will best preserve nuance and safety.
3. The original STE arm will be shortest but reproduce omission or nuance
   failures under pressure.

## Data Collection

### Task set

The frozen battery contains three new tasks, with five repetitions per arm:

| Task | Risk tested | Required ideas |
| --- | --- | ---: |
| `config-triage` | Direct operational diagnosis | 4 |
| `credential-cutover` | Safe production change | 5 |
| `latency-diagnosis` | Diagnosis under uncertainty | 5 |

The [task file](../campaigns/clause-bakeoff-2026-08-05/tasks.jsonl)
contains the exact prompts and required ideas. The task prompts were not reused
from the original confirmatory campaign.

### Generation

Promptfoo 0.121.12 ran 60 isolated responses: 3 tasks × 5 repetitions × 4
arms. Each response used Claude Code 2.1.222 with the `opus` alias and High
effort. Preserved model metadata resolved every evaluated answer to
`claude-opus-5`.

The custom [provider](../campaigns/clause-bakeoff-2026-08-05/provider.py)
created an empty temporary project for each response. Only the selected arm's
`CLAUDE.md` was present. Agent tools and session persistence were disabled.
The provider recorded and rechecked the task, repetition, prompt hash, clause
hash, CLI version, model, effort, raw stream hash, and parsed response hash.

### Blind grading

A separate Sonnet 5 High judge compared all four answers for one task and
repetition in each call. This produced 15 judgments. Labels A–D rotated in a
fixed balanced order, so the judge did not know which clause produced an
answer. Each judgment scored task completion, focus, plain language, jargon
discipline, nuance/safety, material errors, missing requirements, and all six
pairwise comparisons.

“Non-tied win rate” means candidate wins divided by candidate plus control
wins. Ties are reported but excluded from that rate.

> Example: if a candidate wins 8 comparisons, control wins 6, and 1 is tied,
> the non-tied win rate is 8 ÷ (8 + 6) = 57.1%. The tie does not count as half
> a win.

Every judge output resolved to `claude-sonnet-5`. Response hashes and the full
rendered judge-prompt hash bind each cached judgment to the exact four answers
it graded. The grader used `StructuredOutput` only to return the required JSON
schema.

### Frozen selection rule

A candidate was ineligible if it had any material error, more missing
requirements than control, or a mean nuance/safety score more than 0.25 below
control. Model, CLI, or artifact-integrity failures also made a candidate
ineligible.

Eligible candidates would be ranked by pairwise non-tied win rate against
control, then focus, jargon discipline, and finally word count. This ordering
prevents a short but incomplete answer from winning.

## Analysis and Findings

### Hypothesis 1: Complete recipe will improve preference without regressions

`complete-recipe` beat control in 10 of 13 non-tied comparisons, more than the
STE arm's 8 of 14. It also had fewer listed errors and omissions than control.
However, its three material errors triggered the zero-error hard gate.

1a. `complete-recipe` beats control more often than `ste` → **TRUE**  
1b. `complete-recipe` avoids material errors → **FALSE**  
1c. `complete-recipe` avoids increased omissions versus control → **TRUE**

**Bottom Line:** `complete-recipe` was directionally strongest, but it did not
meet the safety requirement and cannot be selected.

### Hypothesis 2: Adaptive recipe will best preserve nuance and safety

`adaptive-recipe` scored 2.400 on nuance/safety, slightly below control's
2.467. It also had the lowest task-completion score, the most material errors,
and the most missing requirements. Several answers stopped after attempted
project inspection.

2a. `adaptive-recipe` has the highest nuance/safety score → **FALSE**  
2b. Its task-dependent detail rule prevents unsafe omission → **FALSE**

**Bottom Line:** The adaptive rule was the least reliable candidate and should
not be iterated without a different formulation.

### Hypothesis 3: STE will be shortest and reproduce earlier failures

STE's median was 300 words, nearly equal to control's 303. The adaptive arm was
shortest at 69 words, but that apparent gain came from incomplete answers. STE
still had five material errors and 22 missing requirements.

3a. STE is the shortest complete strategy → **FALSE**  
3b. STE reproduces material-error or omission failures → **TRUE**

**Bottom Line:** This battery did not reproduce STE's earlier 33.9% word
reduction, but it did reproduce the reason not to deploy it.

## Results

### Quality and length

| Arm | Task completion | Focus | Plain language | Jargon discipline | Nuance/safety | Median words |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Control | 3.067 | 2.667 | 2.800 | 3.000 | 2.467 | 303 |
| STE | 3.667 | 3.600 | 3.800 | 3.867 | 3.067 | 300 |
| Complete recipe | 3.667 | 2.867 | 3.067 | 3.400 | 3.667 | 504 |
| Adaptive recipe | 2.600 | 2.267 | 2.467 | 2.733 | 2.400 | 69 |

_WARNING: The adaptive arm's 69-word median is not a useful brevity result.
Many of those responses were incomplete, so the number measures failure as
well as concision._

**Bottom Line:** STE led the surface writing metrics, while complete-recipe led
nuance/safety. Neither combined those strengths with zero material errors.

### Errors, omissions, and pass status

| Arm | Material-error entries | Missing-requirement entries | Pass | Borderline | Fail | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| Control | 8 | 39 | 7 | 1 | 7 | Baseline |
| STE | 5 | 22 | 9 | 2 | 4 | No |
| Complete recipe | 3 | 27 | 10 | 0 | 5 | No |
| Adaptive recipe | 9 | 44 | 6 | 0 | 9 | No |

“Material-error entries” and “missing-requirement entries” count the strings
listed by the judge. They are not severity-weighted and are not the same as the
number of affected responses.

**Bottom Line:** Every candidate failed the material-error hard gate. The
selection result is therefore `no_eligible_candidate`.

### Pairwise preference against control

| Candidate | Candidate wins | Control wins | Ties | Non-tied win rate |
| --- | ---: | ---: | ---: | ---: |
| STE | 8 | 6 | 1 | 57.1% |
| Complete recipe | 10 | 3 | 2 | 76.9% |
| Adaptive recipe | 5 | 4 | 6 | 55.6% |

**Bottom Line:** Complete-recipe had the clearest preference signal, but
preference could not override the frozen correctness gate.

### Cost

| Phase | Calls | Recorded cost (USD) |
| --- | ---: | ---: |
| Opus 5 High generation | 60 | $3.8599 |
| Sonnet 5 High grading | 15 | $1.6254 |
| **Total** | **75** | **$5.4853** |

The four-response smoke used the same validated output directory as the full
run. Those responses were reused, so the smoke did not raise the campaign above
the frozen 75-call ceiling.

_NOTE: Costs come from Claude CLI raw-stream metadata and are rounded here.
They are not a billing invoice._

**Bottom Line:** The bounded micro-bakeoff cost $5.49 in recorded model usage.

### Overall

The complete recipe is the only candidate worth carrying forward, but only as
source material for a shorter clause. Its preference and safety scores were
strongest, while its length and material errors directly violated the goal.
The original STE clause remains rejected based on both this run and the larger
confirmatory campaign. The adaptive recipe should be dropped in its current
form.

## Manual Audit

We inspected every judgment containing a material-error or
missing-requirement entry after grading. The decisive findings were supported
by the preserved answers: non-answers, malformed agent traces, omitted rotation
or diagnosis steps, and unsafe or overconfident technical claims.

One STE credential-cutover criticism is contestable. The grader treated a
database-session verification step as unsafe when password rotation might use
the same database identity. Removing that one finding would not change the
selection because STE had other material failures.

No response-generation tool call occurred in the 60 evaluated Opus streams.
Some Opus answers emitted tool-like text or stopped after saying they would
inspect the project. We counted those as response failures because the reader
received no usable answer.

## Limitations and Considerations

### The battery is small and exploratory

Three tasks with five repetitions can expose large failures, but cannot
establish stable performance across the range of work done by an agent. The
pairwise rates are descriptive, not statistically conclusive. A single
repetition changes a candidate's rate materially.

### Agent-mode failures confound writing-style effects

All arms sometimes tried to inspect an empty project and then failed to answer.
This behavior is part of Claude Code agent performance, but it is not purely a
verbosity or jargon effect. Because the failure rates differed by arm, it can
also dominate the style scores and word medians.

This is the strongest reason to discount the exact size of the differences.
The hard-gate conclusion remains useful because each candidate produced at
least one serious failure, but the metric ranking is too noisy to support
deployment.

### The grader is not independent human ground truth

Sonnet 5 graded Opus 5 output. Blind labels reduce arm bias, but the judge is
from the same model family and may share technical assumptions or stylistic
preferences. One four-answer judgment also produces all six pairwise outcomes,
so those comparisons are correlated rather than independent observations.

### Error counts are not calibrated severity scores

The judge could list several strings for one failed response and one string for
another. The summary adds those strings, so “three errors” does not mean three
equally severe or independent events. Eligibility depends only on whether the
count is zero, which is robust to this counting problem; comparisons between
nonzero totals are weaker.

### The control was unusually weak

Control failed 7 of 15 responses. This made it easier for a candidate to win
pairwise comparisons without demonstrating production-ready behavior. The
complete recipe's 76.9% non-tied win rate must therefore be read alongside its
own five failed responses.

### Results are version-bound

This evidence applies to Claude Code 2.1.222, the Opus 5 and Sonnet 5 aliases
resolved on 2026-08-05, Promptfoo 0.121.12, these exact clauses, and this task
set. Changes to the CLI, models, hidden system instructions, or provider can
change the outcome.

## Recommendation

Do not deploy the original STE, complete-recipe, or adaptive-recipe clauses.

Use the shorter positive clause in the Executive Summary as the single mutable
artifact in the next experiment. Preserve the current hard gates, then add:

1. a preflight rejection for responses that stop at attempted project
   inspection instead of answering;
2. a requirement that median word count not exceed control;
3. fresh tasks that do not reuse this development battery;
4. human review of every alleged material error and a frozen sample of the
   remaining pairs;
5. a larger confirmatory campaign only after the micro-battery passes.

The complete recipe would become a deployable recommendation only if a shorter
version keeps its preference and nuance advantages while producing zero
material errors and no more omissions than control on fresh data.

## Reproduction

### Offline validation

From the project directory:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q campaigns/clause-bakeoff-2026-08-05
promptfoo validate \
  -c campaigns/clause-bakeoff-2026-08-05/promptfooconfig.yaml
```

### Live generation

Live execution consumes model usage. Use a new, absolute output directory. Do
not reuse the preserved run directory for changed tasks or clauses; provenance
mismatches intentionally fail closed.

```bash
mkdir -p <absolute-new-run-directory>

env \
  BAKEOFF_CLAUDE_VERSION='<exact output of claude --version>' \
  BAKEOFF_OUT_DIR=<absolute-new-run-directory> \
  PROMPTFOO_PYTHON=<absolute-path-to-python3> \
  promptfoo eval \
    -c campaigns/clause-bakeoff-2026-08-05/promptfooconfig.yaml \
    --repeat 5 \
    -j 1 \
    --no-cache \
    --no-share \
    -o <absolute-new-run-directory>/promptfoo-results.json
```

Concurrency remains one because the run is designed to isolate arms and make
resume behavior easy to audit. Promptfoo's cache is disabled, but the custom
provider safely reuses its own hash-validated artifacts after interruption.

### Blind grading and summary

```bash
env \
  BAKEOFF_CLAUDE_VERSION='<same pinned Claude version>' \
  BAKEOFF_OUT_DIR=<absolute-new-run-directory> \
  python3 campaigns/clause-bakeoff-2026-08-05/analyze.py \
    --out-dir <absolute-new-run-directory> \
    --execute
```

The final machine-readable decision is
`<absolute-new-run-directory>/bakeoff-results.json`.

## Future Research

1. **Clause compression:** Which part of complete-recipe caused the 66% length
   increase, and can it be removed without losing safety?
2. **Agent-mode stability:** Does an explicit “answer from the supplied facts;
   do not inspect the project” instruction eliminate incomplete agent traces
   across all arms?
3. **Judge agreement:** How often does a human reviewer agree with Sonnet's
   material-error and omission labels?
4. **Task coverage:** Does the candidate remain useful on low-risk factual,
   code-review, explanatory, and ambiguous requests?
5. **Generalization:** Does a micro-battery winner survive a newly frozen
   confirmatory suite?

## Versioning

| Version | Date | Change | Status |
| --- | --- | --- | --- |
| 1.0.0 | 2026-08-05 | Initial durable evaluation write-up | No eligible candidate |

## Appendix

### Data manipulation decisions

- We did not discard any completed response or judgment.
- The four-call smoke artifacts were reused in the full run after complete
  provenance validation.
- Ties were excluded from non-tied win-rate denominators, as frozen in the
  analysis code.
- Word count was used only as the final ranking tiebreaker.
- We did not retroactively change a judge label. The manual audit records the
  contestable STE credential finding without modifying the frozen result.

### Tooling rationale

Promptfoo supplied the candidate-by-task execution matrix and resumable run
surface. The project uses a custom Python provider because the evaluated object
is an isolated Claude Code project with a different `CLAUDE.md` per arm, not a
normal API prompt. The project's own analyzer performs blind four-way grading
and hard-gate selection because a single aggregate Promptfoo score would let
brevity compensate for safety or correctness failures.

For background, see the [Promptfoo evaluation
documentation](https://www.promptfoo.dev/docs/intro/) and the project's
[tooling assessment](../notes/tooling-options-2026-08-05.md).
