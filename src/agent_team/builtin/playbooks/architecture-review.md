---
name: architecture-review
description: Review the structure of a codebase or design: boundaries, dependencies, risks
mode: report
---
Review the architecture of $ARGUMENTS.

Describe the current structure (components, responsibilities, dependencies, data flow). Then assess:
boundaries that leak, dependency direction, coupling hotspots, duplicated responsibilities, scaling and
failure risks, and decisions that are hard to reverse. Recommend changes in order of value, each with
the smallest first step.
