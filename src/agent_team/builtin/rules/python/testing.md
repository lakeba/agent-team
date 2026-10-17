---
name: testing
description: Python testing
---
- Use the project's test runner (pytest or unittest) and its existing layout.
- Use temporary directories (`tmp_path`, `tempfile`) for files; never write into the repository.
- Mock at the boundary (network, clock, subprocess), not the code under test.
- Parametrise cases instead of copying tests.
