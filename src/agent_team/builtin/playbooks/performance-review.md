---
name: performance-review
description: Look for performance problems and propose measured fixes
mode: report
---
Review $ARGUMENTS for performance.

Look for work in loops that could be done once, N+1 queries, missing indexes, unbounded data,
blocking calls on async paths, memory that grows, and algorithms with poor complexity on large input.
For each: where, the likely cost, how to measure it, and the fix. Don't recommend changes you can't
justify with a measurement plan.
