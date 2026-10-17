---
name: code-review-checklist
description: A checklist for reviewing a change thoroughly and kindly
---
# Code review checklist

Understand first: read the task and the plan, then the tests, then the code.

1. Does it do what was asked, completely, and nothing else?
2. Correctness at the edges: empty, null, large, unicode, time zones, concurrency, failures of I/O.
3. Tests: every behaviour covered; tests would fail if the code were wrong; no tests weakened.
4. Security: input validation, injection, auth checks, secrets, logging of personal data.
5. Errors handled or propagated with context; no silent failures.
6. Clear names, small functions, no duplication, comments for why.
7. Consistent with the codebase's patterns and rules.
8. Docs and changelog updated where users would notice.

Write findings with the location, the problem, and a concrete suggestion. Mark which are blocking.
Praise what's done well; it tells the author what to keep doing.
