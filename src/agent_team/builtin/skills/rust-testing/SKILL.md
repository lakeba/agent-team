---
name: rust-testing
description: Testing Rust: unit and integration tests, property tests, doc tests
---
# Rust testing

- Unit tests in `#[cfg(test)] mod tests` beside the code; integration tests in `tests/`.
- Doc examples are tests: keep them compiling.
- Property-based tests (`proptest`) for parsers and invariants.
- `#[should_panic(expected = "...")]` sparingly; prefer testing returned errors.
- Async tests with the runtime's test macro (`#[tokio::test]`).
