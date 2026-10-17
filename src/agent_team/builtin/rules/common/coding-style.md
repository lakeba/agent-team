---
name: coding-style
description: How code is written on this project, whatever the language
---
- Prefer clear names over comments. A comment says why, never what the next line does.
- Keep functions short and doing one thing. More than about 40 lines or three levels of nesting is a sign to split.
- Follow the style already in the file you change. Consistency inside a file beats any personal preference.
- No dead code, commented-out code or unused imports in a change.
- Handle errors where you can do something useful about them; otherwise let them propagate with context.
  Never swallow an error silently.
- Avoid global mutable state. Pass dependencies in.
- No magic numbers or strings repeated in several places: name them once.
- Don't add a dependency for something the standard library or a few lines of code can do.
- Keep the change to what the task needs. Unrelated clean-ups go in their own change.
