---
name: style
description: TypeScript style
---
- `strict` mode on; no `any` without a comment explaining why. Prefer `unknown` and narrow.
- Model data with types or interfaces; use union types and exhaustive `switch` for variants.
- Prefer `const`, pure functions and immutable updates.
- Handle promise rejections: every `async` call is awaited or its error handled.
- No `console.log` left in committed code; use the project's logger.
