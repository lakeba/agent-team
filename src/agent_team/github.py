"""GitHub and git helpers. Uses the `gh` CLI, so it acts with whatever account `gh` is signed into."""
from __future__ import annotations

import json
import re
import subprocess
import tarfile
import io
import tempfile
import time
from pathlib import Path

from . import files


class GitHubError(RuntimeError):
    pass


def gh(*args: str, check: bool = True, input: str | None = None) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180, input=input)
    if check and r.returncode != 0:
        raise GitHubError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def gh_json(*args: str, check: bool = True):
    return json.loads(gh(*args, check=check) or "null")


def git(root: str | Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=180)
    if check and r.returncode != 0:
        raise GitHubError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def untrusted(text: str) -> str:
    """Wrap text written by people outside the team, so prompts can say: data, not instructions."""
    return f"<untrusted>\n{text}\n</untrusted>"


def head_sha(repo: str, ref: str = "main") -> str:
    return gh_json("api", f"repos/{repo}/commits/{ref}")["sha"]


def ci_status(repo: str, pr: int) -> tuple[bool, str]:
    """(all checks passed, summary). Right after a push GitHub may report no checks at all."""
    checks = gh_json("pr", "checks", str(pr), "-R", repo, "--json", "name,state,bucket", check=False) or []
    if not checks:
        return False, "no CI checks reported yet"
    return all(c["bucket"] == "pass" for c in checks), ", ".join(f"{c['name']}: {c['state']}" for c in checks)


def ci_failed(repo: str, pr: int) -> bool:
    checks = gh_json("pr", "checks", str(pr), "-R", repo, "--json", "bucket", check=False) or []
    return any(c["bucket"] in ("fail", "cancel") for c in checks)


def run_for_commit(repo: str, sha: str) -> dict | None:
    runs = gh_json("run", "list", "-R", repo, "--commit", sha, "--limit", "1",
                   "--json", "databaseId,status,conclusion") or []
    return runs[0] if runs else None


def wait_for_commit_ci(repo: str, sha: str, minutes: float = 15) -> tuple[bool, str]:
    deadline = time.time() + minutes * 60
    while True:
        run = run_for_commit(repo, sha)
        if run and run["status"] == "completed":
            return run["conclusion"] == "success", f"CI on {sha[:10]}: {run['conclusion']}"
        if time.time() > deadline:
            return False, f"CI on {sha[:10]} has not finished ({run['status'] if run else 'no run yet'})"
        time.sleep(15)


def ci_test_counts(repo: str, sha: str, pattern: str) -> str:
    """Test counts per CI job for one commit, read from the CI log with the project's regex."""
    if not pattern:
        return "no test_count_pattern configured"
    run = run_for_commit(repo, sha)
    if not run:
        return "no CI run found for this commit"
    log = gh("run", "view", str(run["databaseId"]), "-R", repo, "--log", check=False)
    rx, found = re.compile(pattern), {}
    for line in log.splitlines():
        m = rx.search(line)
        if m:
            found[line.split("\t", 1)[0]] = m.group(1)    # gh log lines start with the job name
    return "; ".join(f"{job}: {n}" for job, n in sorted(found.items())) or "no test count found in the CI log"


def release_test_counts(repo: str, pattern: str, limit: int = 3) -> str:
    out = []
    for r in gh_json("release", "list", "-R", repo, "--limit", str(limit), "--json", "tagName") or []:
        sha = head_sha(repo, r["tagName"])
        out.append(f"{r['tagName']} (commit {sha[:10]}): {ci_test_counts(repo, sha, pattern)}")
    return "; ".join(out) or "no releases yet"


def main_snapshot(root: str | Path, skip: tuple[str, ...] = (), limit: int = 200_000, ref: str = "origin/main",
                  focus: list[str] | None = None) -> str:
    """Project files exactly as on `ref`, whatever branch the local checkout is on. If they don't
    fit in `limit` and `focus` is given, only the focus files (those a PR changes) plus a map."""
    git(root, "fetch", "-q", "origin")
    archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", ref],
                             capture_output=True, check=True, timeout=180).stdout
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        try:
            return files.snapshot(tmp, skip=skip, limit=limit)
        except files.SnapshotTooLarge:
            if focus is None:
                raise
            keep = set(focus) | {p for p in ("README.md", "CHANGELOG.md") if Path(tmp, p).is_file()}
            body = files.snapshot(tmp, skip=skip, limit=limit, paths=keep)
            return (f"(The project is too large to send whole: the files this PR changes, as on main, "
                    f"then a map of all files.)\n\n{body}\n\n# Project map\n{files.overview(tmp, skip=skip)[:18_000]}")


def changed_files(repo: str, pr: int) -> list[str]:
    return [f["path"] for f in gh_json("pr", "view", str(pr), "-R", repo, "--json", "files")["files"]]


def diff_for(repo: str, pr: int, prefixes: tuple[str, ...] | None = None, limit: int = 60_000) -> str:
    diff = gh("pr", "diff", str(pr), "-R", repo)
    if prefixes:
        parts = re.split(r"(?=^diff --git )", diff, flags=re.M)
        diff = "".join(p for p in parts if any(p.startswith(f"diff --git a/{x}") for x in prefixes))
    return diff[:limit]
