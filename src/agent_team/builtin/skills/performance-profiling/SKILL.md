---
name: performance-profiling
description: Finding and fixing performance problems by measuring first
---
# Performance

1. **Define the goal**: which operation, how fast, on what data and hardware.
2. **Measure** before changing anything: a profiler (py-spy, cProfile, perf, dotnet-trace, Chrome
   DevTools), query plans (`EXPLAIN ANALYZE`), timings around the suspect path.
3. **Fix the biggest cost first.** Common wins: removing N+1 queries, adding an index, batching I/O,
   caching expensive pure results, moving work out of loops, streaming instead of loading everything.
4. **Measure again** with the same setup and keep the numbers in the change description.
5. Add a benchmark or a performance test if the path matters and could regress.

Don't optimise code that isn't hot, and don't trade clarity for gains you can't measure.
