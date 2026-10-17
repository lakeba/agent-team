---
name: refactor
description: Clean up code structure without changing behaviour
mode: build
---
Refactor $ARGUMENTS.

1. Make sure the behaviour is covered by tests; add characterisation tests where it isn't.
2. Remove dead code and duplication; improve names; split long functions; simplify conditionals.
3. One kind of change at a time, tests green after each. No behaviour changes.
4. Summarise what changed and why it's clearer.
