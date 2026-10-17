---
name: error-handling
description: Handling errors: where to catch, how to report, retries, and user-facing messages
---
# Error handling

- Decide per error: can this code do something useful (retry, fall back, ask the user)? If not, let it
  propagate with context added.
- Never swallow errors. An empty catch block is a bug unless commented with why.
- Add context when re-raising: what was being done and with which identifiers (not secrets).
- Distinguish expected failures (validation, not found) from bugs. Expected ones are values or typed
  errors; bugs crash loudly in development and are reported in production.
- Retries only for transient failures (timeouts, 503, connection reset), with exponential backoff,
  jitter and a limit. Never retry non-idempotent operations without an idempotency key.
- At the system edge, turn errors into one consistent response shape and log the details once.
- User-facing messages say what happened and what to do next, without internals.
