---
name: go-patterns
description: Idiomatic Go: errors, interfaces, context, concurrency, packages
---
# Go patterns

- Errors are values: return them, wrap with `%w`, check with `errors.Is/As`; sentinel or typed errors
  for callers that branch on them.
- Accept interfaces, return concrete types; keep interfaces small and defined by the consumer.
- `context.Context` as the first parameter of anything that does I/O; respect cancellation.
- Goroutines: each has a clear owner and exit; use `errgroup` for groups; channels for ownership transfer,
  mutexes for shared state.
- Zero values useful; constructors only when needed.
- Packages by responsibility, not by layer names like `utils`.
- `defer` for cleanup right after acquiring a resource.
