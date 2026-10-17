---
name: refactoring
description: Refactoring safely: small behaviour-preserving steps backed by tests
---
# Refactoring

- Refactor only with tests that cover the behaviour you're keeping. Add characterisation tests first if needed.
- Work in tiny steps, each a known transformation: rename, extract function/variable, inline, move,
  replace conditional with polymorphism, introduce parameter object. Run tests after each.
- Keep behaviour changes out of refactoring commits.
- Look for: long functions, duplicated logic, long parameter lists, feature envy, shotgun surgery,
  primitive obsession, dead code.
- Stop when the next feature is easy to add. Leave a note for larger restructurings instead of doing
  them halfway.
