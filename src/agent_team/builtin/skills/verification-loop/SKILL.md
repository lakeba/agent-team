---
name: verification-loop
description: Checking your own work before handing it over: build, types, lint, tests, diff
---
# Verify before you hand over

Before saying a change is done:
1. Build or compile it.
2. Run the type checker and linter the project uses; fix what you introduced.
3. Run the tests; add the ones the change needs.
4. Read your own diff as a reviewer would: unrelated changes, debug leftovers (`print`, `console.log`,
   `debugger`), commented-out code, TODOs without an issue, secrets.
5. Check the edge cases you thought of are covered.
6. Update docs and changelog if users would notice.
Report what you ran and what it showed.
