# ADR 0001: Bakeoff 9 runs as a cut-down, decision-relevant campaign

**Status:** accepted 2026-08-14 (grill session, James + Claude Fable 5)
**Context files:** `archive/field-critique-synthesis-2026-08-14/notes/2026-08-14-eval-handoff-prompt.md`
(spec rev 2), `.../2026-08-14-adversarial-review-codex.md`, `.../2026-08-14-followon-factorial-eval.md`

## Context

The rev-2 handoff specifies four arms × four batteries (30 tasks × 3 reps) plus
a five-level effort sweep — roughly 2,000 tool-enabled agentic responses with
trajectory-level dual judging, ~30 seeded repo fixtures, and a human gold set.
Bakeoffs 1–8 were 50–75 responses each. The Completion clause under test is
already deployed verbatim in James's live `~/.claude/CLAUDE.md`. Its own
follow-on note calls the spec "a patch" and names a held-out factorial as the
methodologically correct design.

## Decision

Bakeoff 9 is scoped to the single contrast that would change a deployment
decision: **does the deployed Completion clause reduce false `Verified` claims
without inducing paralysis?**

- **Arms:** A1 (Response style + Numbers) vs A2 (A1 + Completion). A0 and A3
  deferred.
- **Batteries:** B1 (false completion, easy + hard strata) and B3
  (over-suppression control). B2, B4, and the effort sweep deferred.
- **Trigger for action:** a negative result removes the Completion clause from
  James's CLAUDE.md. James confirmed he would act on that.

## Consequences

- ~360 responses instead of ~2,000; the fixture-engineering lift is the
  dominant cost either way and is now bounded to B1/B3 task families.
- The campaign cannot speak to Completion-in-isolation (A3 vs A0), tampering,
  calibration carry-over, or effort interaction. Those remain with the
  factorial follow-on.
- The harness-owned verification state machine recommended by the adversarial
  review is a separate build, evaluated by the factorial, not by this campaign.
