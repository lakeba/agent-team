---
name: release-check
description: Check a project is ready to release: version, changelog, tests, docs, risks
mode: report
---
Check whether $ARGUMENTS is ready to release.

Verify: the version follows the changes since the last release (breaking/feature/fix); the changelog
lists every user-visible change; tests and CI are green; docs match; migrations and upgrade notes exist
for breaking changes; nothing debug or secret is shipped. Give a go/no-go with the blockers.
