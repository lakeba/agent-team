---
name: python-patterns
description: Idiomatic, maintainable Python: typing, data classes, errors, I/O, packaging
---
# Python patterns

- Type hints on public functions; run a type checker (mypy, pyright). Use `X | None`, `list[str]`.
- Data: `@dataclass(frozen=True)` or `NamedTuple` for records; `Enum` for fixed choices; avoid dicts
  as ad-hoc objects across function boundaries.
- Paths with `pathlib.Path`; files with `with open(..., encoding="utf-8")`.
- Iteration: comprehensions for simple transforms, generators for large or streaming data;
  `enumerate`, `zip(strict=True)`, `itertools` instead of index juggling.
- Errors: raise specific exceptions with messages; define a small hierarchy for a library;
  `raise ... from err` to keep the cause.
- No mutable defaults (`def f(x=None)` then create inside).
- Logging with `logging.getLogger(__name__)`, never `print` in libraries.
- Subprocesses with argument lists (`subprocess.run([...], check=True)`), never `shell=True` with input.
- Async: don't mix blocking I/O into `async` code; use `asyncio.to_thread` or async libraries;
  always await or keep a reference to tasks.
- Packaging: `pyproject.toml`, pinned dev tools, a single source of version.
