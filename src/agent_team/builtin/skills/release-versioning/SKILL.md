---
name: release-versioning
description: Semantic versioning, changelogs and safe releases
---
# Releases and versions

- Semantic versioning: MAJOR for breaking changes to the public API, MINOR for features, PATCH for fixes.
  Before 1.0, minor versions may break; say so.
- What's public: documented APIs, CLI flags, config keys, file formats, HTTP endpoints. Changing them
  breaks someone.
- Keep a changelog (Added, Changed, Deprecated, Removed, Fixed, Security), written for users.
- Deprecate before removing: warn for at least one minor release with the replacement.
- Release from a green CI commit; tag it; publish artefacts from CI, not from a laptop.
