"""Approval gates: paths whose changes need a person's approval before a PR can merge.

    [project]
    require_approval = ["auth/", "package.json", "*.csproj"]

A PR that changes a matching path merges only after the owners approve its exact head commit with
`agent-team approve <PR>` (or the dashboard's or panel's Approve button). The approval is recorded
on this machine (.team/owner-approvals.json), never through GitHub, where every agent posts with
the same account; a new commit needs a new approval. When a gated PR is otherwise ready, the shift
records a request so the dashboard, the panel and `agent-team status` can show it.
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from . import files, usage
from .config import Team

APPROVALS = "owner-approvals.json"
REQUESTS = "approval-requests.json"


def gated(team: Team, paths: list[str]) -> list[str]:
    """The changed paths that need the owners' approval."""
    rules = team.project.require_approval
    return [p for p in paths if any(p == r or p.startswith(r) or fnmatch.fnmatch(p, r)
                                    or fnmatch.fnmatch(Path(p).name, r) for r in rules)]


def _read(root, name: str) -> dict:
    try:
        return json.loads((Path(root) / files.LOG_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(root, name: str, data: dict) -> None:
    folder = Path(root) / files.LOG_DIR
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(data, indent=1), encoding="utf-8")


def approvals(root) -> dict[int, str]:
    return {int(k): v["sha"] for k, v in _read(root, APPROVALS).items()}


def approve(root, number: int, sha: str) -> None:
    data = _read(root, APPROVALS)
    data[str(number)] = {"sha": sha, "at": usage.now()}
    _write(root, APPROVALS, data)
    reqs = _read(root, REQUESTS)
    if reqs.pop(str(number), None) is not None:
        _write(root, REQUESTS, reqs)


def request(root, number: int, sha: str, title: str, paths: list[str]) -> None:
    reqs = _read(root, REQUESTS)
    reqs[str(number)] = {"sha": sha, "title": title, "paths": paths, "at": usage.now()}
    _write(root, REQUESTS, reqs)


def requests(root) -> list[dict]:
    return [{"number": int(k), **v} for k, v in sorted(_read(root, REQUESTS).items(), key=lambda kv: int(kv[0]))]


def clear_request(root, number: int) -> None:
    reqs = _read(root, REQUESTS)
    if reqs.pop(str(number), None) is not None:
        _write(root, REQUESTS, reqs)
