"""My MVP: the owner's view of the product, in plain words.

What the product is (VISION.md), what's been built (session summaries), what's changed and not yet
kept, what's next on the roadmap, what it has cost, and the actions an owner takes: keep this
version (a commit, pushed when there's a GitHub repository), build the next feature, prepare the
application to Lakeba (the marketing run's brief and deck).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import files, sessions, usage
from .config import Team

APPLY_URL = "https://lakeba.com/os/apply"
SKIP = (".team/", ".team.toml.bak")


def _git(root: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def changed(root: Path) -> list[str]:
    """Files changed since the last kept version (not the team's own records)."""
    code, out = _git(root, "status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return []
    paths = [line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines() if len(line) > 3]
    plan_tracked = bool(_git(root, "ls-files", "--", "PLAN.md")[1])
    # The team's working PLAN.md stays out of kept versions unless the project already tracks one.
    return [p for p in paths if not p.startswith(SKIP) and (p != "PLAN.md" or plan_tracked)]


def roadmap(root: Path, limit: int = 8) -> list[str]:
    path = Path(root) / "ROADMAP.md"
    if not path.exists():
        return []
    items = [re.sub(r"^\s*[-*\d.)]+\s*(\[[ x]\]\s*)?", "", l).strip()
             for l in path.read_text(encoding="utf-8").splitlines() if re.match(r"^\s*([-*]|\d+[.)])\s+", l)]
    return [i for i in items if i][:limit]


def summary(team: Team) -> dict:
    root = Path(team.root)
    vision = (root / "VISION.md").read_text(encoding="utf-8") if (root / "VISION.md").exists() else ""
    vision_text = "\n".join(l for l in vision.splitlines() if not l.startswith("#")).strip()
    total = usage.summarize(usage.load(root), team.pricing)["total"]
    code, log = _git(root, "log", "--format=%h|%ad|%s", "--date=short", "-n", "8")
    versions = [dict(zip(("sha", "date", "message"), l.split("|", 2))) for l in log.splitlines() if code == 0 and "|" in l]
    has_brief = (root / "BRIEF.md").exists()
    deck = next((str(p.relative_to(root)) for p in sorted(root.glob("deck/*.html"))), "")
    from .workflows.init import github_repo
    return {
        "name": team.project.name,
        "vision": vision_text[:4000],
        "built": [sessions.summary_line(p) for p in sessions.listing(root)[:8]],
        "changed": changed(root),
        "versions": versions,
        "roadmap": roadmap(root),
        "cost": total.get("cost", 0.0),
        "repo": team.project.repo or github_repo(root),
        "application": {"brief": has_brief, "deck": deck, "apply_url": APPLY_URL},
        "needs_key": needs_key(team),
    }


def needs_key(team: Team) -> bool:
    """Whether a member runs on Claude and no Anthropic key is saved: the team can't start until
    one is (the guided setup lets people skip choosing where the AI runs)."""
    from . import keys
    keys.load_into_env()
    used = {a.provider for a in team.agents.values()}
    return any(p.kind == "anthropic" and not os.environ.get(p.api_key_env or "ANTHROPIC_API_KEY")
               for name, p in team.providers.items() if name in used)


def keep_version(team: Team, message: str = "") -> dict:
    """Commit what changed (not the team's records) and push it when there's a remote."""
    root = Path(team.root)
    paths = changed(root)
    if not paths:
        return {"kept": False, "note": "nothing has changed since the last version"}
    from . import secret_scan
    message = (message or "").strip()[:200] or "A new version"
    _git(root, "add", "--", *paths)
    try:
        secret_scan.guard(root)
    except SystemExit as e:
        _git(root, "reset", "-q")
        return {"kept": False, "note": str(e)}
    code, out = _git(root, "commit", "-q", "-m", message)
    if code != 0:
        return {"kept": False, "note": out[-300:]}
    pushed = ""
    if _git(root, "remote", "get-url", "origin")[0] == 0:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")[1]
        code, out = _git(root, "push", "-q", "-u", "origin", branch)
        pushed = "pushed to GitHub" if code == 0 else f"saved here, but not pushed: {out[-200:]}"
    return {"kept": True, "files": paths, "note": pushed or "saved on this computer"}
