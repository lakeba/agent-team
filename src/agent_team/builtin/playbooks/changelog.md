---
name: changelog
description: Write the changelog entries for the changes since the last release
mode: build
---
Write the changelog for $ARGUMENTS (default: changes since the last release tag).

Read the commits and diffs, group user-visible changes under Added, Changed, Deprecated, Removed, Fixed
and Security, written for users (what they can now do, what changed for them), and add them under
Unreleased in CHANGELOG.md. Leave out internal-only changes.
