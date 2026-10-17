---
name: testing
description: Testing rules for every change
---
- Every behaviour change comes with a test that fails without it.
- A bug fix starts with a test that reproduces the bug.
- Test behaviour through the public interface, not private details, so refactoring doesn't break tests.
- One behaviour per test, with a name that says what is expected.
- Tests are independent and repeatable: no order dependence, no real network, no reliance on the clock
  or random values without fixing them.
- Keep tests fast. Slow or external tests are marked and run separately.
- Don't weaken or delete a failing test to make a change pass. Fix the code, or explain why the test was wrong.
