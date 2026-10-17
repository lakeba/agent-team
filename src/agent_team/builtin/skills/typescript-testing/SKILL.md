---
name: typescript-testing
description: Testing TypeScript and JavaScript with Vitest or Jest
---
# TypeScript testing

- Use the project's runner; `describe` per unit, `it` per behaviour with a sentence name.
- Table tests with `it.each`.
- Mock modules at boundaries (`vi.mock`/`jest.mock`) and reset between tests; prefer dependency
  injection to deep mocking.
- Fake timers (`vi.useFakeTimers()`) for time; restore after.
- HTTP: mock at the network layer (MSW) rather than stubbing fetch per test.
- Keep tests type-checked; `expectTypeOf` for type-level guarantees in libraries.
