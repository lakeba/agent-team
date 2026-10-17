---
name: logging-observability
description: Logs, metrics and traces that let you find problems quickly
---
# Logging and observability

- Structured logs (key-value or JSON) with a level, a message, and identifiers (request id, user id
  hash, job id). One event per line.
- Levels: ERROR needs action, WARN is unexpected but handled, INFO marks business events, DEBUG is off in production.
- Never log secrets, tokens, passwords or full personal data. Mask or hash.
- Log at boundaries (incoming request, outgoing call, job start/end) rather than everywhere.
- Metrics for rates, errors and durations (the RED method) of every endpoint and job; alert on symptoms
  users feel, not on every cause.
- Propagate a trace/correlation id across services and include it in logs.
