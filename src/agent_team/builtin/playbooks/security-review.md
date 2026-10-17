---
name: security-review
description: Review code or a feature for vulnerabilities, with severity and fixes
mode: report
---
Review $ARGUMENTS for security problems.

Check input handling and injection (SQL, shell, HTML, paths, deserialisation); authentication and
per-object authorisation; secrets in code, config, logs and fixtures; data exposure in responses and
logs; crypto and randomness; dependencies; file and process handling.
Report each finding with location, how it could be exploited, severity (critical/high/medium/low)
and the fix. End with the order to fix them in.
