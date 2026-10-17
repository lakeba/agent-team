---
name: fix-bug
description: Fix a defect: reproduce it as a failing test, find the cause, fix, and guard against it
mode: build
---
Fix this bug: $ARGUMENTS.

1. Reproduce it with a failing test using the smallest input.
2. Find the root cause; check for the same mistake elsewhere.
3. Fix the cause, keep the test, run the full suite.
4. Note what caused it and whether a guard (validation, better error, type) would prevent the class of bug.
