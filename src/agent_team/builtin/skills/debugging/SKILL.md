---
name: debugging
description: Systematic debugging: reproduce, isolate, explain, fix, and prevent
---
# Debugging

1. **Reproduce** reliably, with the smallest input. Write it down as a failing test if you can.
2. **Read the evidence**: the full error, stack trace, logs around it. The first error matters most.
3. **Form a hypothesis** that explains every symptom, then test it (a print, a breakpoint, a probe).
4. **Bisect** when it used to work: `git bisect`, or halving the input/config.
5. **Fix the cause**, not the symptom; check for the same mistake elsewhere.
6. **Prevent**: the failing test stays; add a guard or a better error message if it would have helped.
Avoid changing several things at once; you won't know which one mattered.
