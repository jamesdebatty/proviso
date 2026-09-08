# Coverage judgment

You are reading one response and the question it answers. Judge only whether
the response covers every required idea listed for that question. Identify the
question by its opening words below. Each required idea is a prose idea, not a
string: a response covers it when the idea is present in any wording.

Return:

- `label`: `complete` when every required idea is covered, `incomplete` when at
  least one is absent;
- `missing`: the required ideas that are absent, quoted from the list below, or
  an empty list;
- `reason`: at most 40 words.

Do not reward or penalize length, formatting, or style; other measures cover
those. Return no judgment when the question does not match any entry below.

## Question beginning "Two services each keep their own copy of customer entitlements (which features ..."

Required ideas:

- a way to detect divergence, such as periodic comparison of a digest, checksum, or versioned snapshot of each side's state
- a reconciliation rule that decides which copy wins, such as a per-record authoritative owner, last-writer-wins with a clock, or an explicit merge policy, and acknowledgement that the choice has consequences
- behavior during a partition, including that reconciliation must pause or degrade rather than converge on stale data, and what each side does while isolated
- a safety concern such as reconciliation flapping, oscillation between the copies, or silently overwriting a legitimate local change
- how an operator would observe whether the mechanism is working, such as a drift metric or an alert on divergence age

## Question beginning "Explain how these four things interact during a partial outage of a ..."

Required ideas:

- retries multiply load on an already degraded dependency, so backoff and jitter matter and synchronized retries can produce a coordinated load spike
- a circuit breaker changes the failure shape, failing fast and shedding load, but can also mask the dependency's recovery or trip on the wrong signal
- the bounded queue means work is dropped or callers block once it fills, and queued work can be stale or already abandoned by the client by the time it runs
- connection pool exhaustion couples unrelated request paths, so one slow dependency can starve requests that do not need it
- an emergent interaction, such as breaker state and retry timing amplifying each other, or queued retries arriving in a burst when the breaker closes

## Question beginning "A 30-service platform is deciding between two designs for periodic jobs: (a) ..."

Required ideas:

- the central scheduler is a shared failure and contention point, while per-service schedulers spread that risk but multiply the operational surface
- duplicate or missed runs are the core correctness concern in both designs, so leader election, locking, or idempotent jobs are needed either way
- visibility and consistency differences, such as one place to see and audit all schedules versus per-team autonomy and drift in conventions
- migration and organizational cost, including that 30 teams adopting a central dependency is a coordination problem, not only a technical one
- a recommendation that names the conditions under which it holds rather than presenting one design as universally correct

## Question beginning "A request that normally completes in about 200 ms occasionally takes around ..."

Required ideas:

- establish whether the slow requests share a dimension, such as one host, one instance, one dependency, one customer, or one code path, before forming a theory
- use per-request tracing or timing breakdown to find which segment of the request consumes the time rather than guessing at the layer
- name plausible mechanisms for a rare, region-specific stall, such as connection establishment or DNS, a lock or queue wait, garbage collection or other pauses, a retry with a long timeout, or cross-region network behavior
- note that the region restriction is evidence about topology or configuration, such as a dependency, network path, or capacity that differs in that region
- state what would confirm or eliminate the leading hypothesis rather than declaring a root cause

## Question beginning "Explain to a new backend engineer what a write-ahead log is, what ..."

Required ideas:

- define a write-ahead log as recording an intended change durably before applying it, so the system can recover or replay after a crash
- define idempotency as the property that repeating the same request produces the same result without duplicating the effect, and connect it to retries and duplicate charges
- define backpressure as a consumer signalling or forcing a producer to slow down when it cannot keep up, rather than dropping or unboundedly queueing work
- connect the three, for example that durable logging plus idempotent processing makes retry-on-failure safe, while backpressure keeps the queue between them from growing without bound
- use the standard names for these concepts rather than avoiding them
