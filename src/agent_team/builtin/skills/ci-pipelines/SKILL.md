---
name: ci-pipelines
description: Continuous integration that is fast, reliable and secure
---
# CI pipelines

- Run on every pull request and on the main branch: install, lint, type-check, test, build.
- Fail fast: cheap checks first; cache dependencies keyed on lock files.
- Same commands locally and in CI (a `make`/script target), so failures reproduce.
- Pin action and image versions (by digest or exact tag for third-party actions).
- Least privilege: read-only tokens by default; secrets only in jobs that need them, never on PRs from forks.
- Flaky tests are fixed or quarantined with an issue, not retried forever.
- Keep the pipeline under ten minutes for pull requests; move slow suites to a separate job.
