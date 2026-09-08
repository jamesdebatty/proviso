# Clause bakeoff 3 protocol

Date: 2026-08-05
Status: frozen before live calls

## Question

Does the shortened positive clause (`positive-recipe`) keep `complete-recipe`'s
preference and nuance/safety advantages over control while producing zero
confirmed material errors, no more omissions than control, and a median length
no longer than control?

## Arms

1. `control`: no project `CLAUDE.md`.
2. `positive-recipe`: the four-sentence positive clause recommended by the
   2026-08-05 clause-bakeoff report, verbatim.
3. `complete-recipe`: byte-identical to the clause tested in bakeoff 2
   (sha256 `ee8e6b55…`), included as the bridge comparator the new clause was
   derived from.

The only changed artifact per arm is `CLAUDE.md`. All arms use isolated,
single-turn Claude Opus 5 High sessions with no tools and no session
persistence.

## Hypotheses

- H1: `positive-recipe` beats control in pairwise preference at least as often
  as `complete-recipe` does.
- H2: `positive-recipe` keeps median words at or below control, repairing
  `complete-recipe`'s +66% length failure.
- H3: `positive-recipe` produces no confirmed material errors and no more
  missing requirements than control.
- H4 (instrument): the two judges agree on a majority of pairwise outcomes;
  material-error allegations made by only one judge are common enough to
  justify the dual-judge design.

## Battery

Five fresh tasks (none reused from bakeoff 2 or the confirmatory campaign):
direct operational triage, a safe production change, diagnosis under
uncertainty, a low-risk explanation, and an ambiguous scoping request. The last
two extend coverage to low-stakes work per the bakeoff-2 report's future
research items.

Each task runs five times per arm: 75 Opus responses. Each non-skipped
task/repetition set is graded by two independent blind judges in one call each:
up to 50 judge calls. Total live call ceiling: 125.

## Preflight gate (new, frozen)

Before judging, every response is classified deterministically:

- `stalled` if it contains fewer than 40 words, or its final paragraph
  announces an intent to inspect the project, files, codebase, repository, or
  directory (frozen regex in `analyze.py`).
- `answered` otherwise.

Stalled responses are not judged; a set containing any stalled arm is skipped
entirely and recorded. Stall counts per arm are a reported metric and an
eligibility gate. Word medians are computed over answered responses only.

## Judges

Two blind graders score every judged set from the identical rendered prompt
with identical label rotation:

- `sonnet`: Claude Code `--model sonnet --effort high`, no tools, verified as
  `claude-sonnet-5` from the response stream.
- `codex`: Codex CLI `exec`, model pinned to `gpt-5.6-sol`, high reasoning
  effort, read-only sandbox, run in an empty directory with a per-call
  temporary `CODEX_HOME` seeded only with `auth.json`. The resolved model is
  verified from the persisted session rollout's `turn_context` record, which is
  preserved as a raw artifact.

Labels A–C rotate deterministically by set index. Judges see the task, the
required ideas, and the three answers only.

## Material-error rule (frozen)

Judges' material-error lists are combined per response:

- alleged by **both** judges → `confirmed` (counts against eligibility; the
  manual audit may contest it in prose but cannot flip the frozen result);
- alleged by **exactly one** judge → `disputed` (queued for human review in
  `human-review.json`; a disputed allegation adjudicated `material_error: true`
  becomes confirmed, `false` becomes dismissed);
- selection status is `needs_human_review` until every disputed allegation
  against a candidate is adjudicated.

## Selection rule

A candidate is ineligible if any of these are true:

- it has a confirmed material error;
- it has an unresolved disputed error (blocks selection, pending review);
- for either judge, its missing-requirement total exceeds control's;
- for either judge, its mean nuance/safety is more than 0.25 below control;
- its median word count exceeds control's median;
- its stalled-response count exceeds control's;
- an integrity, model-identity, or CLI-stability check fails.

Among eligible candidates, rank by pooled non-tied win rate against control
across both judges, then mean focus, then jargon discipline, then lower median
words.

This is a development battery. A winning clause still requires a later, newly
frozen holdout campaign with human review before deployment.
