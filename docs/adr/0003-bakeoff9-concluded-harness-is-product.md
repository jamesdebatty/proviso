# ADR 0003: Bakeoff 9 concludes; the reusable clause harness is the product

**Status:** accepted 2026-08-30

Bakeoff 9 is concluded without a campaign verdict after its reference gate
failed. We will not spend more calls or redesign effort to rescue that result.
Its durable output is the reusable workflow for isolating a `CLAUDE.md` change,
pinning the execution context, running behavioral probes, and retaining enough
evidence to audit direct impact. “Clause Shipper” is the working name for that
workflow inside the `clause-bakeoff` repository, not a repository rename.

## Consequences

- Bakeoff 9 remains a preserved campaign and integration case, not the active
  roadmap.
- New work deepens campaign-independent declarations, capture, grading, and
  reporting instead of adding more `bakeoff9_*` seams.
- A future campaign must be cheap to declare and exercise locally before any
  paid run; old campaigns remain immutable evidence rather than migration work.
- The failed Fable reference attempt is retained as diagnostic evidence and is
  not promoted into gold labels or a campaign finding.
