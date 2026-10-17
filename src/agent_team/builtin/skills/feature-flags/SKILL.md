---
name: feature-flags
description: Shipping safely behind feature flags and removing them afterwards
---
# Feature flags

- Use flags to separate deploy from release, for gradual rollouts and quick kill switches.
- Default to off for new behaviour; evaluate the flag in one place, not scattered through the code.
- Test both paths while the flag exists.
- Record the owner and removal date; remove the flag and the dead path once fully rolled out.
- Don't use flags for permanent configuration or authorisation.
