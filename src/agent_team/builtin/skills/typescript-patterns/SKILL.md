---
name: typescript-patterns
description: TypeScript patterns: strict types, discriminated unions, async, modules
---
# TypeScript patterns

- `strict: true`. Prefer `unknown` to `any`; narrow with type guards; validate external data with a
  schema (zod, valibot) and infer the type from it.
- Model variants with discriminated unions and exhaustive `switch` (`const _: never = x`).
- Prefer `readonly`, `as const`, and pure functions; avoid classes for plain data.
- Async: `async`/`await`, `Promise.all` for independent work, `AbortController` for cancellation;
  never leave a floating promise.
- Errors: throw `Error` subclasses; at boundaries return result objects if callers must handle failure.
- Modules: small, explicit exports; no circular imports; path aliases kept simple.
- Node: `node:` prefixed built-ins, `fs/promises`, streams for large data.
