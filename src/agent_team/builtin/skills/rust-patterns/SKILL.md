---
name: rust-patterns
description: Rust patterns: ownership, errors, traits, iterators, async
---
# Rust patterns

- Errors: `thiserror` for library error enums, `anyhow` (or similar) in applications; `?` to propagate;
  no `unwrap` on fallible operations in production paths.
- Borrow by default; clone deliberately; use `Cow` when sometimes owned.
- Newtypes for domain values; enums for states; make invalid states unrepresentable.
- Iterators and combinators over manual indexing.
- Traits for behaviour, generics for zero-cost abstraction, trait objects when you need heterogeneity.
- Async: one runtime; don't block in async code (`spawn_blocking`); cancel-safe selects.
- `unsafe` only with a `// SAFETY:` comment explaining the invariant.
