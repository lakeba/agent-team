---
name: testing
description: TypeScript testing
---
- Use the project's runner (Vitest, Jest, node:test) and keep tests next to the code if that's the convention.
- Type-check tests too. Avoid casting to `any` to make a test compile.
- Fake timers and network explicitly; restore them after each test.
