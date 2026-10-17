---
name: python-testing
description: Testing Python with pytest or unittest: fixtures, parametrisation, mocking, coverage
---
# Python testing

- Follow the project's runner. pytest: plain `assert`, fixtures for setup, `@pytest.mark.parametrize`
  for tables of cases. unittest: `setUp`, `subTest` for tables.
- Files and folders: `tmp_path` (pytest) or `tempfile.TemporaryDirectory()`; never the repo.
- Mock at boundaries with `unittest.mock.patch` on where the name is looked up; prefer fakes for
  complex collaborators. Assert behaviour, not call counts, unless the call is the behaviour.
- Time: inject a clock or freeze time; randomness: seed it.
- Exceptions: `pytest.raises(ValueError, match="...")` / `assertRaisesRegex`.
- CLI: call `main(argv)` and capture output (`capsys`, `contextlib.redirect_stdout`).
- Coverage to find untested branches, not as a target in itself.
