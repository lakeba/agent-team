---
name: tdd-workflow
description: Test-driven development: red, green, refactor, with small steps and honest tests
---
# Test-driven development

1. **Red.** Write one test for the next behaviour. Run it and watch it fail for the reason you expect
   (not an import error or a typo).
2. **Green.** Write the simplest code that makes it pass. Hard-coding is fine if the next test will force
   the general solution.
3. **Refactor.** With all tests green, clean up names, duplication and structure. Run the tests again.
4. Repeat with the next behaviour, edge case or error.

Guidelines
- Pick the next test that teaches you the most: the simplest case first, then edges (empty, one, many,
  invalid, failure of a dependency).
- Keep the cycle to minutes. If a step needs a lot of code, the test was too big: split it.
- A bug report becomes a failing test before any fix.
- Tests describe behaviour ("rejects an expired token"), not implementation ("calls validate()").
- Don't mock what you own just to isolate it; fake slow or external boundaries (network, clock, disk).
- When the tests pass and the code reads well, stop.
