---
name: dependency-audit
description: Review the project's dependencies for need, health, licences and vulnerabilities
mode: report
---
Audit the dependencies of $ARGUMENTS (default: the whole project).

For each direct dependency: what it's used for, whether it's still needed, how maintained it is, its
licence, whether versions are pinned/locked, and known vulnerabilities you can see from the versions.
Report: dependencies to remove, to upgrade, to replace, and any licence concerns, in priority order.
