---
name: dependency-management
description: Choosing, pinning, updating and removing dependencies
---
# Dependency management

- Before adding: is it needed? Maintained? Licence compatible? Size and transitive dependencies acceptable?
- Pin with lock files and commit them. Reproducible installs in CI (`npm ci`, `pip install -r` with
  hashes, `cargo --locked`).
- Update regularly in small batches with automated PRs; read changelogs for majors.
- Watch for vulnerabilities with automated alerts; patch quickly.
- Remove unused dependencies.
- Wrap a dependency behind your own interface when it's central and could be replaced.
