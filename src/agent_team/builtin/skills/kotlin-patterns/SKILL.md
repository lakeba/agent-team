---
name: kotlin-patterns
description: Kotlin patterns: null safety, data and sealed classes, coroutines, flows
---
# Kotlin patterns

- Null safety without `!!`: `?.`, `?:`, `requireNotNull` with a message at boundaries.
- Data classes for values, sealed interfaces for states and results, `when` exhaustively.
- Coroutines with structured concurrency: scopes tied to lifecycles, `supervisorScope` when children
  fail independently, dispatchers injected for testability.
- Flows for streams; `StateFlow` for UI state.
- Extension functions for readability; avoid hiding I/O in them.
