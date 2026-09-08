# Clause Shipper synthetic smoke protocol

This campaign exists only to prove the reusable campaign lifecycle. It does
not measure a model, estimate a clause effect, or support a ship decision.

The declaration pins two `CLAUDE.md` variants, one probe tree, the synthetic
execution adapter, and both deterministic and judgmental grading boundaries.
The adapter reads committed response fixtures and must not open a network
connection or invoke a model. Judgmental measures remain pending until a
separate judge supplies a result.

The run is complete when one command validates the declaration, writes an
immutable plan and per-trial records, applies deterministic measures, emits
blind-export judgment tasks, and writes a summary that labels its evidence as
synthetic integration evidence only. Repeating the command against the same
run directory must reproduce every durable byte.

`judgments.json` is the blind export: its tasks are ordered by opaque task id
and carry no variant or trial identity. A judge receives that file alone. The
complete run directory is intentionally unblinded audit evidence because it
also contains variant-named trials; it must not be supplied to a blind judge.
