---
name: style
description: Python style
---
- Follow PEP 8 and the project's formatter; type-hint public functions.
- Use pathlib for paths, f-strings for formatting, context managers for files and locks.
- Prefer dataclasses or named tuples to loose dicts for structured data.
- Catch specific exceptions; never a bare `except:`.
- No mutable default arguments. No `print` for diagnostics in library code: use `logging`.
- Keep imports at the top, grouped standard library, third party, local.
