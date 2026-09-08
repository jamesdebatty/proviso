# Clause bakeoff protocol

Date: 2026-08-05  
Status: frozen before live calls

## Question

Can a positive response recipe preserve the original STE clause's clarity and
brevity gains without its losses in preference, nuance, safety, and required
content?

## Arms

1. `control`: no project `CLAUDE.md`.
2. `ste`: the exact original treatment.
3. `complete-recipe`: lead with the answer, preserve load-bearing content, then
   remove only repetition and non-decision-changing detail.
4. `adaptive-recipe`: vary detail using observable task conditions, with an
   explicit high-stakes response structure.

The only changed artifact is `CLAUDE.md`. All arms use isolated, single-turn
Claude Opus 5 High sessions with no tools or session persistence.

## Hypotheses

- H1: `complete-recipe` will beat control more often than `ste` while avoiding
  material errors and increased omissions.
- H2: `adaptive-recipe` will best preserve nuance and safety because its detail
  rule depends on observable task conditions.
- H3: the original `ste` arm will remain shortest but will reproduce omission
  or nuance failures under pressure.

## Battery

Three new tasks target the confirmatory campaign's failure clusters without
reusing its exact prompts: direct operational triage, a safe production change,
and diagnosis under uncertainty. Each task runs five times per arm: 60 Opus
responses total.

A blind Sonnet 5 High grader evaluates all four answers for one task/repetition
in one call: 15 judge calls. Answer labels rotate deterministically. Total live
call ceiling: 75.

## Selection rule

A candidate is ineligible if any of these are true:

- it has a material error;
- it has more missing requirements than control;
- its mean nuance/safety score is more than 0.25 below control;
- an integrity, model-identity, or CLI-stability check fails.

Among eligible candidates, rank by pairwise non-tied win rate against control.
Use mean focus and jargon discipline as secondary signals. Use word reduction
only as a final tiebreaker.

This is an exploratory development battery. The existing 60-response campaign
remains the confirmatory result for the original treatment. A winning new clause
requires a later, newly frozen holdout campaign.
