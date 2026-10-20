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


def gh(*args: str, check: bool = True, input: str | None = None, token: str = "") -> str:
    """Run the GitHub CLI; with `token`, as that identity (a member's own bot account or app)."""
    env = None
    if token:
        import os
        env = {**os.environ, "GH_TOKEN": token}
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180, input=input, env=env)
    if check and r.returncode != 0:
        raise GitHubError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def member_token(team, cfg) -> str:
    """The member's own GitHub token, if it has one ([[agents]].github_token_env), else ""."""
    import os
    return os.environ.get(cfg.github_token_env, "") if getattr(cfg, "github_token_env", "") else ""


def review(repo: str, number: int, verdict: bool, body: str, token: str) -> str:
    """Post a real GitHub review as a member: approve, or request changes. Returns "" or why not."""
    try:
        gh("pr", "review", str(number), "-R", repo, "--approve" if verdict else "--request-changes",
           "--body", body[:60000], token=token)
        return ""
    except GitHubError as e:    # e.g. the bot opened the PR itself, or lacks permission
        return str(e)[:300]


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


# Test counts as the usual runners print them, tried when the project's own pattern finds nothing
# (a project that started empty keeps the default pattern, whatever its tests turn out to be).
KNOWN_COUNTS = (("pytest", r"(\d+) passed"), ("unittest", r"Ran (\d+) tests?"), ("jest", r"Tests:\s+(\d+) passed"),
                ("vitest", r"Tests\s+(\d+) passed"), ("cargo", r"test result: ok\. (\d+) passed"),
                ("dotnet", r"Passed:\s+(\d+)"))


def counts_in(log: str, pattern: str) -> tuple[dict, str]:
    """({job: count}, the format that found them) for one CI log: the project's pattern first, then
    KNOWN_COUNTS. Lines of `gh run view --log` start with the job's name."""
    tries = ([("the project's pattern", pattern)] if pattern else []) + [(n, rx) for n, rx in KNOWN_COUNTS if rx != pattern]
    for name, rx in tries:
        found = {}
        compiled = re.compile(rx)
        for line in log.splitlines():
            job, _, text = line.partition("\t")
            m = compiled.search(text if _ else line)
            if m:
                found[job] = m.group(1)
        if found:
            return found, name
    return {}, ""


def ci_test_counts(repo: str, sha: str, pattern: str) -> str:
    """Test counts per CI job for one commit, read from the CI log."""
    run = run_for_commit(repo, sha)
    if not run:
        return "no CI run found for this commit"
    log = gh("run", "view", str(run["databaseId"]), "-R", repo, "--log", check=False)
    found, how = counts_in(log, pattern)
    if not found:
        return "no test count found in the CI log"
    note = "" if how == "the project's pattern" else f" (read as {how} output)"
    return "; ".join(f"{job}: {n}" for job, n in sorted(found.items())) + note


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
