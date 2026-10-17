---
name: api-review
description: Review an API for consistency, errors, compatibility and documentation
mode: report
---
Review the API in $ARGUMENTS.

Check naming and consistency, input validation and error shapes, status codes, pagination and limits,
idempotency, authentication, backwards compatibility of changes, and documentation. Report findings
and a list of changes that would break existing callers.
