"""ship: one autonomous devops shift on GitHub (issues, PRs, sign-offs, merges, feedback, releases).

The devops agent decides what to do, but it can only act through the tools below, and the tools
enforce the rules in code:
  * a PR merges only if CI is green, the lead approved the exact head commit, and every team
    member who owns a changed path signed off that same commit;
  * a release needs green CI on main and a CHANGELOG entry (an `## [Unreleased]` heading is
    dated through a one-line, code-generated release PR first);
  * text from outside the team always reaches the models marked as untrusted.
"""
from __future__ import annotations

import base64
import datetime
import json
import re
import time
from pathlib import Path

import anthropic
from anthropic import beta_tool

from .. import agent, budget, files, github, logs, ui, usage
from ..config import Team

SIGNATURE = "\n\n— {name}, devops agent for this repo (automated)"


def merge_blockers(team: Team, number: int, sha: str, paths: list[str], ci_green: bool, ci_summary: str,
                   approvals: dict[int, str], signoffs: dict[tuple[int, str], str]) -> str:
    """Why this PR may not merge yet, or "" if it may. Every rule is tied to the exact head commit."""
    if not ci_green:
        return f"CI is not all green ({ci_summary})."
    if approvals.get(number) != sha:
        return "the lead has not approved the PR's current head commit in this shift."
    missing = [m for m in team.owners_of(paths) if signoffs.get((number, m)) != sha]
    if missing:
        return f"missing sign-off on this commit from: {', '.join(missing)}."
    return ""


def is_changelog_rename(changed_lines: list[str], paths: list[str], version: str) -> bool:
    """True only for a PR whose entire change is `## [Unreleased]` -> `## [X.Y.Z] - YYYY-MM-DD`."""
    return (paths == ["CHANGELOG.md"] and len(changed_lines) == 2 and changed_lines[0] == "-## [Unreleased]"
            and re.fullmatch(rf"\+## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}", changed_lines[1]) is not None)


RE_REVIEW = """You reviewed this pull request before. Your earlier review is below, and the commit has changed
since. On this re-review, block only on (a) your earlier blocking points that are still not
resolved, and (b) real problems introduced by the changes since then. Anything else you notice now
goes under "Non-blocking notes" unless it is serious (a bug, broken guarantee, security or data
loss). Don't move the goalposts: a PR that fixes what you asked for should pass.

# Your earlier review (of commit {sha})
{text}"""

PR_ENTRY_RE = re.compile(r"^(review|sign-off) (?:of|on) PR #(\d+) at ([0-9a-f]+)")


def earlier_review(root, number: int, member: str, kinds=("review", "sign-off")) -> tuple[str, str]:
    """(text, commit) of this member's latest review or sign-off of this PR in the ship log."""
    for run in logs.parse(root):                  # newest run first
        if run["workflow"] != "ship":
            continue
        for e in reversed(run["entries"]):
            m = PR_ENTRY_RE.match(e["what"])
            if e["who"] == member and m and m.group(1) in kinds and int(m.group(2)) == number:
                return e["text"], m.group(3)
    return "", ""


def re_review_note(root, number: int, member: str, sha: str) -> str:
    text, reviewed = earlier_review(root, number, member)
    if not text or sha.startswith(reviewed):
        return ""
    return "\n\n" + RE_REVIEW.format(sha=reviewed, text=text[:6000])


def split_lead(owners: dict[str, list[str]], lead: str) -> tuple[dict[str, list[str]], list[str] | None]:
    """(owners who sign off separately, the lead's owned paths or None): the lead's approval of a
    commit is its sign-off, so it isn't asked twice."""
    rest = {m: p for m, p in owners.items() if m != lead}
    return rest, owners.get(lead)


def ensure_labels(repo: str, names: list[str]) -> list[str]:
    """Create any of these labels the repository doesn't have yet; returns the ones created."""
    if not names:
        return []
    existing = {l["name"].lower() for l in github.gh_json("label", "list", "-R", repo, "--limit", "500",
                                                          "--json", "name") or []}
    created = []
    for name in names:
        if name.lower() not in existing and len(name) <= 50:
            github.gh("label", "create", name, "-R", repo, "--description", "Added by the agent-team devops shift",
                      check=False)
            created.append(name)
    return created


def repo_state(team: Team) -> str:
    repo, pattern = team.project.repo, team.project.test_count_pattern
    j = github.gh_json
    issues = j("issue", "list", "-R", repo, "--state", "open", "--limit", "50", "--json",
               "number,title,body,author,labels,comments")
    prs = j("pr", "list", "-R", repo, "--state", "open", "--limit", "30", "--json",
            "number,title,body,author,headRefName,isCrossRepository,labels,comments")
    releases = j("release", "list", "-R", repo, "--limit", "5", "--json", "tagName,publishedAt")
    merged = j("pr", "list", "-R", repo, "--state", "merged", "--limit", "15", "--json", "number,title,mergedAt")
    head = github.head_sha(repo)
    run = github.run_for_commit(repo, head)
    changelog = github.gh("api", f"repos/{repo}/contents/CHANGELOG.md", "-H",
                          "Accept: application/vnd.github.raw", check=False)
    out = [f"# Repository {repo}",
           f"Clone URL (verified by the team's tooling): https://github.com/{repo}.git",
           f"Recent releases: {json.dumps(releases)}",
           f"Recently merged PRs: {json.dumps(merged)}",
           f"main head: {head[:10]}, CI on it: {run and run['status'] + ' ' + str(run['conclusion'])}",
           f"Test counts for released versions (verified by the team's tooling from CI logs): "
           f"{github.release_test_counts(repo, pattern)}",
           f"\n# CHANGELOG.md on main\n\n{changelog[:8000] or '(missing)'}", f"\n# Open issues ({len(issues)})"]
    for i in issues:
        comments = "\n".join(f"- {c['author']['login']}: {c['body']}" for c in i["comments"])
        out.append(f"\n## Issue #{i['number']} by {i['author']['login']} · labels {[l['name'] for l in i['labels']]}\n"
                   + github.untrusted(f"Title: {i['title']}\n\n{i['body']}\n\nComments:\n{comments or '(none)'}"))
    out.append(f"\n# Open pull requests ({len(prs)})")
    for p in prs:
        comments = "\n".join(f"- {c['author']['login']}: {c['body']}" for c in p["comments"])
        out.append(f"\n## PR #{p['number']} by {p['author']['login']} · branch {p['headRefName']} · fork "
                   f"{p['isCrossRepository']}\n" + github.untrusted(
                       f"Title: {p['title']}\n\n{p['body']}\n\nComments:\n{comments or '(none)'}"))
    return "\n".join(out)


PROPOSAL = "release-proposal.json"


def release_proposal(root) -> dict | None:
    """The release the devops shift proposed and the owners haven't approved yet, if any."""
    path = Path(root) / files.LOG_DIR / PROPOSAL
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(team: Team, max_steps: int = 30, approved_release: str = "") -> None:
    repo, root, pattern = team.project.repo, team.root, team.project.test_count_pattern
    if not repo:
        raise SystemExit("[project].repo is not set.")
    devops_cfg, lead_cfg = team.by_role("devops"), team.by_role("lead")
    skip, limit = tuple(team.project.context_skip), team.project.context_limit
    log = files.Log(root, "ship", f"Ops shift on {repo}")
    sign = SIGNATURE.format(name=devops_cfg.name)
    approvals: dict[int, str] = {}                      # PR -> head SHA the lead approved
    signoffs: dict[tuple[int, str], str] = {}           # (PR, member) -> head SHA they signed off

    def act(line: str) -> None:
        ui.action(line)
        log.record(f"{devops_cfg.name}: action", line)

    def verified_facts(sha: str) -> str:
        return (f"CI test counts for this commit (verified by the team's tooling from the CI log): "
                f"{github.ci_test_counts(repo, sha, pattern)}\nTest counts for released versions "
                f"(verified): {github.release_test_counts(repo, pattern)}")

    def pr_head(number: int) -> dict:
        return github.gh_json("pr", "view", str(number), "-R", repo, "--json", "title,body,headRefOid,author")

    @beta_tool
    def view_pull_request(number: int) -> str:
        """Show a PR's description, changed files, diff, CI status and which members must sign off.

        Args:
            number: The pull request number.
        """
        info = pr_head(number)
        paths = github.changed_files(repo, number)
        green, summary = github.ci_status(repo, number)
        owners = team.owners_of(paths)
        return (f"PR #{number} head {info['headRefOid'][:10]}\nCI all green: {green} ({summary})\n"
                f"Files: {paths}\nSign-offs required (owner -> paths): {owners or 'none'}\n" +
                github.untrusted(f"Title: {info['title']}\n\n{info['body']}\n\nDiff:\n{github.diff_for(repo, number)}"))

    @beta_tool
    def comment(number: int, body: str) -> str:
        """Post a comment on an issue or pull request (signed automatically).

        Args:
            number: The issue or PR number.
            body: Markdown text.
        """
        github.gh("issue", "comment", str(number), "-R", repo, "--body", body + sign)
        act(f"commented on #{number}: {body[:160]}")
        return "posted"

    @beta_tool
    def set_labels(number: int, add: list[str], remove: list[str]) -> str:
        """Add and/or remove labels on an issue or pull request.

        Args:
            number: The issue or PR number.
            add: Labels to add (may be empty).
            remove: Labels to remove (may be empty).
        """
        add = [l.strip() for l in add if l.strip()][:10]
        created = ensure_labels(repo, add)
        args = ["issue", "edit", str(number), "-R", repo]
        for label in add:
            args += ["--add-label", label]
        for label in remove:
            args += ["--remove-label", label]
        if add or remove:
            github.gh(*args)
        act(f"labels on #{number}: +{add} -{remove}" + (f" (created {created})" if created else ""))
        return "done" + (f"; created the new labels {created}" if created else "")

    @beta_tool
    def close_issue(number: int, reason: str, comment_text: str) -> str:
        """Close an issue with a short explanatory comment.

        Args:
            number: The issue number.
            reason: "completed" or "not planned".
            comment_text: Why it is being closed.
        """
        if reason not in ("completed", "not planned"):
            return "reason must be 'completed' or 'not planned'"
        github.gh("issue", "close", str(number), "-R", repo, "--reason", reason, "--comment", comment_text + sign)
        act(f"closed #{number} ({reason})")
        return "closed"

    @beta_tool
    def request_signoffs(number: int, note: str) -> str:
        """Ask every team member who owns a path changed by the PR to sign it off. Required to merge.

        Args:
            number: The pull request number.
            note: What the PR changes and why.
        """
        info, owners = pr_head(number), team.owners_of(github.changed_files(repo, number))
        # The lead reviews every PR anyway: its approval of a commit counts as its own sign-off,
        # so it never reviews the same commit twice with two different verdicts.
        owners, lead_owned = split_lead(owners, lead_cfg.name)
        lead_note = (f"{lead_cfg.name} is the lead: its approval in request_lead_review counts as its "
                     f"sign-off for {', '.join(lead_owned)}.") if lead_owned else ""
        if not owners:
            return lead_note or "No sign-offs needed: the PR changes no owned paths."
        sha, results = info["headRefOid"], [lead_note] if lead_note else []
        main_files = github.main_snapshot(root, skip, limit, focus=None if team.project.context == "full" else github.changed_files(repo, number))
        for member, paths in owners.items():
            cfg = team.get(member)
            reviewer = agent.make(team, cfg, "signoff", files=main_files, label_suffix=f" · PR #{number} sign-off")
            reply = reviewer.turn(
                f"{devops_cfg.name}'s note:\n{note}\n\nYour paths changed: {paths}\n{verified_facts(sha)}"
                f"{re_review_note(root, number, member, sha)}\n\n" +
                github.untrusted(f"Title: {info['title']}\n\n{info['body']}\n\nDiff of your paths:\n"
                                 f"{github.diff_for(repo, number, tuple(cfg.owns))}"))
            yes = files.last_marker(files.SIGNOFF_RE, reply) == "YES"
            if yes:
                signoffs[(number, member)] = sha
            log.record(f"{member}: sign-off on PR #{number} at {sha[:10]}", reply)
            github.gh("pr", "comment", str(number), "-R", repo, "--body",
                      f"{reply}\n\n— {member} ({cfg.role} agent, automated), reviewing commit {sha[:10]}; "
                      f"recorded by the team's tooling")
            act(f"{member} {'signed off' if yes else 'did not sign off'} PR #{number} at {sha[:10]}")
            results.append(f"## {member}: {'YES' if yes else 'NO'}\n{reply}")
        return "\n\n".join(results)

    @beta_tool
    def request_lead_review(number: int, note: str) -> str:
        """Ask the lead to review a PR. The lead's approval of the current commit is required to merge.

        Args:
            number: The pull request number.
            note: Your assessment for the lead: what the PR does, CI state, concerns.
        """
        info = pr_head(number)
        sha, green_summary = info["headRefOid"], github.ci_status(repo, number)
        owners = team.owners_of(github.changed_files(repo, number))
        status = {m: ("covered by your review" if m == lead_cfg.name else
                      "YES for this commit" if signoffs.get((number, m)) == sha else "MISSING for this commit")
                  for m in owners}
        main_files = github.main_snapshot(root, skip, limit, focus=None if team.project.context == "full" else github.changed_files(repo, number))
        reviewer = agent.make(team, lead_cfg, "review_pr", files=main_files,
                              label_suffix=f" · PR #{number} review")
        review = reviewer.turn(
            f"{devops_cfg.name}'s note:\n{note}\n\nCI all green: {green_summary[0]} ({green_summary[1]})\n"
            f"Head commit under review: {sha}\nSign-offs (verified by the team's tooling): {status or 'none needed'}\n"
            f"{verified_facts(sha)}{re_review_note(root, number, lead_cfg.name, sha)}\n\n" +
            github.untrusted(f"Title: {info['title']}\n\n{info['body']}\n\nDiff:\n{github.diff_for(repo, number)}"))
        log.record(f"{lead_cfg.name}: review of PR #{number} at {sha[:10]}", review)
        if files.last_marker(files.VERDICT_RE, review) == "APPROVED":
            approvals[number] = sha
            if lead_cfg.name in owners:
                signoffs[(number, lead_cfg.name)] = sha   # the lead's approval is its sign-off
        return review

    @beta_tool
    def merge_pull_request(number: int) -> str:
        """Squash-merge a PR. Refused unless CI is green, the lead approved this exact commit, and
        every owner of a changed path signed off this exact commit.

        Args:
            number: The pull request number.
        """
        sha = pr_head(number)["headRefOid"]
        green, summary = github.ci_status(repo, number)
        blocker = merge_blockers(team, number, sha, github.changed_files(repo, number), green, summary,
                                 approvals, signoffs)
        if blocker:
            return f"REFUSED: {blocker}"
        github.gh("pr", "merge", str(number), "-R", repo, "--squash", "--delete-branch", "--match-head-commit", sha)
        act(f"merged PR #{number} at {sha[:10]}")
        return "merged"

    @beta_tool
    def write_feedback_digest(markdown: str) -> str:
        """Save the developer-feedback digest (.team/FEEDBACK.md) for the lead's roadmap planning.

        Args:
            markdown: The full digest in Markdown.
        """
        path = Path(root, files.LOG_DIR, "FEEDBACK.md")
        path.write_text(markdown.strip() + "\n", encoding="utf-8")
        act("wrote the feedback digest")
        return "saved"

    @beta_tool
    def create_release(version: str, notes: str) -> str:
        """Release a version from main. If CHANGELOG.md has an `## [Unreleased]` heading, a one-line
        release PR dates it first (verified, CI-checked, merged). Waits for CI; takes minutes.

        Args:
            version: Semantic version like "1.2.3" (no leading v).
            notes: Release notes in Markdown.
        """
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            return "REFUSED: version must look like 1.2.3"
        if github.gh("release", "view", f"v{version}", "-R", repo, check=False):
            return f"REFUSED: v{version} already exists."
        if team.project.release == "ask" and version != approved_release:
            proposal = {"version": version, "notes": notes, "at": usage.now(), "by": devops_cfg.name}
            Path(root, files.LOG_DIR).mkdir(exist_ok=True)
            Path(root, files.LOG_DIR, PROPOSAL).write_text(json.dumps(proposal, indent=1), encoding="utf-8")
            act(f"proposed release v{version} for the owners to approve")
            return (f"NOT RELEASED: this project's owners approve releases ([project].release = \"ask\"). "
                    f"Your proposal for v{version} is recorded; it is released when they run "
                    f"`agent-team ship --release {version}`. Say so in your summary.")
        head = github.head_sha(repo)
        ok, why = github.wait_for_commit_ci(repo, head, minutes=15)
        if not ok:
            return f"REFUSED: {why}"
        changelog = github.gh("api", f"repos/{repo}/contents/CHANGELOG.md", "-H",
                              "Accept: application/vnd.github.raw", check=False)
        if not re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M):
            if not re.search(r"^## \[Unreleased\]$", changelog, re.M):
                return f"REFUSED: CHANGELOG.md has neither '## [{version}] - <date>' nor '## [Unreleased]'."
            result = _date_changelog(version, changelog, head)
            if result.startswith("REFUSED"):
                return result
            head = result
        github.gh("release", "create", f"v{version}", "-R", repo, "--target", head, "--title", f"v{version}",
                  "--notes", notes)
        Path(root, files.LOG_DIR, PROPOSAL).unlink(missing_ok=True)
        act(f"released v{version} at {head[:10]}")
        return f"released v{version} at {head[:10]}"

    def _date_changelog(version: str, changelog: str, base_sha: str) -> str:
        branch = f"release/v{version}"
        existing = github.gh_json("pr", "list", "-R", repo, "--head", branch, "--state", "open", "--json", "number") or []
        if existing:
            number = existing[0]["number"]
            act(f"resuming release PR #{number}")
        else:
            date = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            updated = re.sub(r"^## \[Unreleased\]$", f"## [{version}] - {date}", changelog, count=1, flags=re.M)
            github.gh("api", "-X", "POST", f"repos/{repo}/git/refs", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={base_sha}")
            file_sha = github.gh_json("api", f"repos/{repo}/contents/CHANGELOG.md?ref={branch}")["sha"]
            payload = json.dumps({"message": f"Release v{version}: date the changelog", "branch": branch,
                                  "content": base64.b64encode(updated.encode()).decode(), "sha": file_sha})
            github.gh("api", "-X", "PUT", f"repos/{repo}/contents/CHANGELOG.md", "--input", "-", input=payload)
            url = github.gh("pr", "create", "-R", repo, "--base", "main", "--head", branch, "--title",
                            f"Release v{version}", "--body", f"Dates the `[Unreleased]` changelog section as "
                            f"`[{version}] - {date}`. Generated and checked by the release tooling." + sign).strip()
            number = int(url.rsplit("/", 1)[1])
            act(f"opened release PR #{number}")
        # Only an exact one-line heading rename may merge without a model review.
        changed = [l for l in github.gh("pr", "diff", str(number), "-R", repo).splitlines()
                   if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        if not is_changelog_rename(changed, github.changed_files(repo, number), version):
            return f"REFUSED: release PR #{number} is not exactly the changelog heading rename; left open."
        deadline = time.time() + 15 * 60
        while not github.ci_status(repo, number)[0]:
            if github.ci_failed(repo, number) or time.time() > deadline:
                return f"REFUSED: CI on release PR #{number} did not pass; left open."
            time.sleep(15)
        sha = pr_head(number)["headRefOid"]
        github.gh("pr", "merge", str(number), "-R", repo, "--squash", "--delete-branch", "--match-head-commit", sha)
        act(f"merged release PR #{number}")
        new_head = github.head_sha(repo)
        ok, why = github.wait_for_commit_ci(repo, new_head, minutes=15)
        return new_head if ok else f"REFUSED: after merging release PR #{number}, {why}. Retry later."

    tools = [view_pull_request, comment, set_labels, close_issue, request_signoffs, request_lead_review,
             merge_pull_request, write_feedback_digest, create_release]

    ui.heading(f"{devops_cfg.name}'s shift on {repo}")
    state = repo_state(team)
    if team.project.release == "ask":
        pending = release_proposal(root)
        state = (f"# Releases\nThis project's owners approve releases. "
                 + (f"They approved v{approved_release} for this shift: release it with create_release."
                    if approved_release else
                    "Propose one with create_release when it's worth it; it is recorded, not published.")
                 + (f" Pending proposal: v{pending['version']}." if pending and not approved_release else "")
                 + f"\n\n{state}")
    handover = _last_summary(log.path)
    if handover:
        state = f"# Your handover notes from the previous shift\n\n{handover}\n\n{state}"

    provider = team.providers[devops_cfg.provider]
    system = agent.make(team, devops_cfg, "devops").system
    first = f"Start your shift. Current state:\n\n{state}"
    if provider.kind != "anthropic":   # Ollama, OpenAI-compatible or a remote node: the generic tool loop
        from .. import tool_loop
        summary = tool_loop.run(team, devops_cfg, system, tools, first, max_steps)
        log.record(f"{devops_cfg.name}: shift summary", summary)
        ui.heading(f"Shift over. Log: {log.path}")
        return
    client = anthropic.Anthropic(api_key=team.secret(provider)) if team.secret(provider) else anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=devops_cfg.model, max_tokens=16000, tools=tools, system=system,
        output_config={"effort": devops_cfg.effort}, max_iterations=max_steps,
        **({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
           if devops_cfg.model.startswith(("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5")) else {}),
        messages=[{"role": "user", "content": first}])
    final = None
    for message in runner:
        final = message
        usage.record(root, devops_cfg.name, "anthropic", devops_cfg.model,
                     anthropic_usage(message))
        for block in message.content:
            if block.type == "text" and block.text.strip():
                ui.say(f"\n{ui.label(devops_cfg.name, 'devops', devops_cfg.color)}: {block.text}")
            elif block.type == "tool_use":
                ui.say(f"  → {block.name}({json.dumps(block.input)[:140]})")
        budget.check(team)
    summary = "".join(b.text for b in final.content if b.type == "text") if final else ""
    log.record(f"{devops_cfg.name}: shift summary", summary)
    ui.heading(f"Shift over. Log: {log.path}")


def anthropic_usage(message) -> dict:
    from ..providers.anthropic_provider import usage_of
    return usage_of(message)


def _last_summary(log_path: Path) -> str:
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    parts = re.split(r"\n## [^\n]*: shift summary\n", text)
    return re.split(r"\n#{1,2} ", parts[-1])[0].strip() if len(parts) > 1 else ""
