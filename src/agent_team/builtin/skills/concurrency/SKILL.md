---
name: concurrency
description: Writing concurrent code without races, deadlocks or lost work
---
# Concurrency

- Prefer not sharing mutable state: message passing, immutable data, or a single owner.
- When sharing, protect every access with the same lock; keep critical sections small; never call
  unknown code while holding a lock.
- Acquire multiple locks in a fixed order to avoid deadlocks.
- Every background task has an owner that awaits it, handles its errors and can cancel it.
- Bound queues and worker pools; apply backpressure instead of growing memory.
- Make operations idempotent so retries after partial failure are safe.
- Test with race detectors and stress tests where the platform has them.
