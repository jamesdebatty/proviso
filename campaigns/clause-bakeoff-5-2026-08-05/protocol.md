# Clause bakeoff 5 protocol

Date: 2026-08-05
Status: frozen before live calls

## Question

Does subtracting enumerated waste categories — with no length objective at all —
shorten Opus 5 answers without dropping required content?

## Design rationale

Every failed candidate across bakeoffs 2–4 made length an objective (a brevity
mandate, a word budget, a structural cap) and delegated the what-to-cut decision
to the model, which reliably cut content judges count as required. Bakeoff 4's
clean control showed the corollary: un-prompted answers score near ceiling on
nuance, so their extra length is concentrated in categories that carry no
required content — preamble, restatement, narration, closing summaries,
repetition, and unrequested adjacent topics. The subtractive clause names those
categories and removes them. Because the removed categories are disjoint from
task-required content by construction, length should fall without omissions
rising. Length is never mentioned in the clause.

The guarded variant adds a retention clause. Bakeoff 1's v2 failure (a
"never cut a caveat" guard that the model read as a license to add caveats)
makes this the riskiest single sentence in the design, so it is isolated as its
own arm with an explicit non-generative disclaimer.

## Arms

1. `control`: no project `CLAUDE.md`.
2. `subtractive`: answer-then-stop plus a do-not list of waste categories.
3. `guarded-subtractive`: the same clause plus a scoped retention guard
   ("keep every fact, risk, precondition, check, and step the reader needs...
   this is a rule about what to remove, not an instruction to add anything").
4. `budgeted-recipe`: byte-identical to bakeoff 4's candidate (sha256
   `4cfbf027…`), as the best-priced prior trade and a replication arm on fresh
   tasks.

The only changed artifact per arm is `CLAUDE.md`. All arms use isolated,
single-turn Claude Opus 5 High sessions with no tools and no session
persistence.

## Hypotheses

- H1: both subtractive variants reduce median words by at least 20% versus
  control (the waste categories carry that much of a default answer).
- H2: both subtractive variants pass the quality gates — nuance within 0.25 of
  control and missing requirements not above control, per judge — because the
  removed categories are disjoint from required content.
- H3: the retention guard neither reintroduces growth (guarded within ~10% of
  unguarded median) nor triggers the v2 additive failure (no higher omission or
  caveat counts than the unguarded arm).
- H4 (replication): `budgeted-recipe` reproduces its bakeoff-4 profile on fresh
  tasks — roughly 45–60% word reduction with omissions above control.

## Battery

Five fresh tasks (none reused from bakeoffs 2–4): intermittent-401 triage,
API v1 decommission plan, scale-out latency diagnosis, eventual-consistency
explainer, and a rate-limiting scoping request. Every prompt ends with the
frozen no-tools line. 5 repetitions × 4 arms = 100 Opus responses; up to 50
dual-judge calls. Total live call ceiling: 150.

## Preflight, judges, error rule, and selection

Identical to bakeoff 4 (preflight v2 with tool-transcript signatures; Sonnet 5
High and Codex `gpt-5.6-sol` High as isolated blind judges with artifact-based
model verification; material errors confirmed only on cross-judge agreement;
the same eligibility gates and ranking). Note the selection rule already
rewards the outcome this design aims for: a candidate with control-level
quality, control-level win rate, and lower median words is eligible and wins on
the length tiebreaker.

This is a development battery. A winning clause still requires a later, newly
frozen holdout campaign with human review before deployment.
