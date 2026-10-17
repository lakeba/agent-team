---
name: tdd
description: Build something test-first: failing tests, minimal code, refactor
mode: build
---
Build $ARGUMENTS test-first.

1. List the behaviours to implement, simplest first, then edge cases and errors.
2. For each behaviour: write a failing test, run it, see it fail for the right reason; write the
   minimum code to pass; refactor with the tests green.
3. Finish with the full suite green, no skipped tests, and a short note of the behaviours covered.
