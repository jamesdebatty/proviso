# ADR 0002: Bakeoff 9 runs through immutable per-trial artifacts

**Status:** accepted 2026-08-27

## Context

Bakeoff 9 already has fixture contracts, environment pins, request-surface
capture, and mechanical grading, but no module joins them into a live SDK trial.
The primary instrument needs response provenance plus ordered command and edit
evidence, while paid execution must survive interruption without silently
buying the same trial twice. A shared mutable manifest would make concurrency,
recovery, and audit state one problem every worker has to understand.

## Decision

One deep `Bakeoff9Campaign` interface owns planning, readiness, execution,
grading, and decision routing. It writes one immutable plan before execution,
then every trial owns a separate workspace, attempt journal, raw tier, and
atomic `bakeoff9-trial/1` artifact. Run manifests are derived from committed
trial artifacts at the read seam.

The primary generator is a repository-pinned Claude Agent SDK `query()`
adapter. The tested interactive CLI driver remains a second adapter used only
for the transfer measurement. `capture-spine/1` remains the authority for
request surfaces, turns, usage, and retention; `score_eval` remains the
authority for mechanical grading. The trial artifact composes both without
expanding either interface.

Only ordered scorer-facing `command` and `edit` events cross the trial
interface. Instrumentation must reproduce the declared request surfaces under
synthetic 401 before any paid call. Missing exit, skip, or event-order evidence
fails closed. Approval wording is never persisted; durable artifacts retain
only authorization presence, count, size, and hash bound to the immutable plan.

## Consequences

- Repeating a run skips hash-valid committed trials. A crash after dispatch is
  an ambiguous paid attempt and requires new explicit authorization; it is not
  retried automatically.
- Concurrent trials never share a workspace or manifest writer.
- Bakeoff 9 adds a campaign-specific decision module rather than turning the
  generic descriptive `campaign_spec` reducer into a clustered factorial
  analysis language.
- The repository gains a small exact Node SDK dependency instead of importing
  an unrelated private application's installation by absolute path.
- Pilot generation can be represented while the protocol is draft, but full
  generation, judging, and decision remain capability-gated until their frozen
  inputs exist.

## Alternatives considered

- A single mutable run manifest was rejected because locks, partial writes,
  and recovery would leak into every worker.
- Expanding `capture-spine/1` was rejected because response retention, fixture
  semantics, trajectory ordering, and grading policy are different knowledge.
- Using the interactive CLI as the primary generator was rejected because the
  preregistration fixes SDK `query()` as the main campaign surface.
