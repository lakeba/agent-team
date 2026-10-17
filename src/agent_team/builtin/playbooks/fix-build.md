---
name: fix-build
description: Get a failing build, type check, lint or test run green with the smallest correct change
mode: build
---
Fix the failing build: $ARGUMENTS.

1. Run the failing command and read the first error.
2. Find the root cause (changed signature, missing dependency, type mismatch, environment).
3. Make the smallest change that fixes the cause. Never disable a rule, skip a test or add an
   ignore comment to get green.
4. Re-run the whole check and list what was wrong and what changed.
