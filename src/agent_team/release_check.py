"""Releases backed by evidence: the version number follows what the public API actually did.

Before the devops member proposes or makes a release, the project's `api` behaviour scenarios run
on the last release and on main (REA reads the built .NET assemblies or the JavaScript packages).
Removing or changing a public member breaks callers, so it needs a major version (a minor one
while the project is 0.x); adding members needs at least a minor one. A version smaller than that
is refused, with the evidence, in code: it doesn't depend on the model reading the changelog right.
"""
from __future__ import annotations

import re

from . import behaviour, github
from .config import Team

TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse(version: str) -> tuple[int, int, int] | None:
    m = TAG.match(version.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def last_release(team: Team) -> str:
    """The highest vX.Y.Z tag (after fetching tags), or ""."""
    github.git(team.root, "fetch", "-q", "--tags", "origin", check=False)
    tags = [t for t in github.git(team.root, "tag", "--list", check=False).split() if parse(t)]
    return max(tags, key=parse) if tags else ""


def needed(old: tuple[int, int, int], breaking: bool, added: bool) -> tuple[int, int, int]:
    """The smallest version the changes allow."""
    major, minor, patch = old
    if breaking:
        return (major, minor + 1, 0) if major == 0 else (major + 1, 0, 0)
    if added:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def api_scenarios(team: Team) -> list[str]:
    return [s.name for s in team.behaviour.scenarios if s.kind == "api"]


def check(team: Team, head: str) -> dict:
    """What the public API did between the last release and `head`. Empty when there's nothing to
    compare (no api scenarios, no earlier release, or the checks couldn't run)."""
    names = api_scenarios(team)
    tag = last_release(team) if names else ""
    if not names or not tag:
        return {}
    github.git(team.root, "fetch", "-q", "origin", head, check=False)
    outcomes = behaviour.run(team, tag, head, label=f"release check since {tag}", only=names)
    if not outcomes:
        return {}
    failed = [o.name for o in outcomes if o.status == "failed"]
    breaking = sorted({m for o in outcomes for m in o.breaking})
    added = sorted({m for o in outcomes for m in o.added})
    least = needed(parse(tag), bool(breaking), bool(added))
    return {"since": tag, "breaking": breaking, "added": added, "failed": failed,
            "least": ".".join(map(str, least)), "report": behaviour.report(outcomes, for_pr=True)}


def summary(result: dict) -> str:
    if not result:
        return "No API evidence: the project has no api behaviour scenarios, or no earlier release to compare with."
    lines = [f"Public API since {result['since']}:"]
    if result["breaking"]:
        lines.append(f"- removed or changed (breaks callers): {', '.join(result['breaking'][:15])}")
    if result["added"]:
        lines.append(f"- added: {', '.join(result['added'][:15])}")
    if not result["breaking"] and not result["added"]:
        lines.append("- no change")
    if result["failed"]:
        lines.append(f"- couldn't check: {', '.join(result['failed'])}")
    lines.append(f"The next version must be at least {result['least']}.")
    return "\n".join(lines)


def refuse(result: dict, version: str) -> str:
    """A refusal when `version` is smaller than the API changes allow, else ""."""
    if not result or result["failed"]:
        return ""
    if parse(version) < parse(result["least"]):
        why = "public members were removed or changed" if result["breaking"] else "public members were added"
        return (f"REFUSED: v{version} is too small: since {result['since']}, {why}, so the version must be at "
                f"least {result['least']}.\n{summary(result)}")
    return ""
