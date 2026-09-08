# 1. One Postgres instance for all services

Status: accepted (2026-03-02)

## Context

Four services were about to be given their own databases. The team is three
engineers and there is no dedicated operator.

## Decision

All four services share one Postgres instance, each with its own schema and
role.

## Consequences

Cross-service joins become possible, which we do not want and must review for
in code review. One instance is one thing to back up, patch and page on. If a
service later needs isolation for compliance reasons, it moves out, and the
schema separation makes that a data move rather than a rewrite.
