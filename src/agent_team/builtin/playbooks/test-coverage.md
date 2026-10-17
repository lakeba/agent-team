---
name: test-coverage
description: Find untested behaviour and add the tests that matter
mode: build
---
Improve tests for $ARGUMENTS.

1. Find behaviours with no test: public functions, branches, error paths, edge cases. Use the
   coverage tool if the project has one.
2. Rank them by risk (how likely to break, how bad if it did).
3. Add tests for the top items, one behaviour each, through the public interface.
4. Report what's now covered and what's still worth testing.
