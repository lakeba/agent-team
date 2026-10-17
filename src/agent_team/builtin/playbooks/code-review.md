---
name: code-review
description: Review code for bugs, security, tests and clarity, ranked by severity
mode: report
---
Review $ARGUMENTS.

1. Understand the intent: read the relevant README/PLAN/VISION and the code's callers.
2. Go through the code in this order: correctness and edge cases; tests (missing, weak, or testing
   implementation); security (input, injection, auth, secrets); error handling; clarity and duplication;
   consistency with the project's rules.
3. Report findings grouped as CRITICAL, HIGH, MEDIUM, LOW. Each: file and line, the problem, why it
   matters, and the fix.
4. End with a decision (approve / request changes) and the three most important actions.
