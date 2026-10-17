---
name: plan-feature
description: Turn a feature request into a step-by-step plan with acceptance checks and risks
mode: report
---
Plan this feature: $ARGUMENTS.

1. Restate the goal and the user it serves; list what is out of scope.
2. Find where it fits: the files and modules involved, existing patterns to follow.
3. Write the steps in order, each small enough to review, each leaving the project working.
   For each: files touched, what changes, the acceptance check (test or observable behaviour).
4. List risks and unknowns with the cheapest way to resolve each.
5. Estimate size (S/M/L) and suggest how to split it into pull requests.
