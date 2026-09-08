# Constraints for the queue decision

- Background work today: nightly invoice generation (about 4,000 jobs, each
  under a second), plus PDF rendering triggered by users (about 200 a day,
  5 to 40 seconds each, memory-hungry).
- Team: three engineers, no dedicated operator, on-call is best-effort during
  business hours.
- Existing infrastructure: one Postgres instance (see ADR 0001), two
  application servers behind a load balancer, no Redis, no container
  orchestrator.
- A user-triggered PDF that never renders is a support ticket. A nightly
  invoice that never generates is caught by the morning reconciliation report.
- Budget for new managed infrastructure this year: roughly one small instance.
- The PDF renderer occasionally wedges and has to be killed.

## The two options on the table

1. A queue in the existing Postgres: a jobs table, SELECT ... FOR UPDATE SKIP
   LOCKED, workers as extra processes on the application servers.
2. A managed Redis with a worker pool on a separate small instance.
