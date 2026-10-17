---
name: go-testing
description: Testing Go: table-driven tests, subtests, fakes, race detector
---
# Go testing

- Table-driven tests with named cases and `t.Run(tc.name, ...)`.
- `t.Helper()` in helpers; `t.Cleanup` for teardown; `t.TempDir()` for files.
- Fakes implementing small interfaces rather than mocking frameworks.
- `httptest` for HTTP handlers and servers.
- Run with `-race`; use `t.Parallel()` where tests are independent.
- Golden files for large outputs, with an update flag.
