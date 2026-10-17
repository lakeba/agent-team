---
name: backend-patterns
description: Back-end service structure: layers, transactions, jobs and resilience
---
# Back-end patterns

- Layers: transport (HTTP, queue) → application (use cases) → domain (rules) → infrastructure (DB, APIs).
  Dependencies point inwards.
- Transactions around use cases, not around single queries; no remote calls inside a DB transaction.
- Background work in jobs that are idempotent, retried with backoff, and observable.
- Timeouts on every outgoing call; circuit breakers for unreliable dependencies.
- Configuration from the environment, validated at start-up.
- Health and readiness endpoints; graceful shutdown.
