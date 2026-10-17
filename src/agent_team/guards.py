"""Guards on what members write, after ECC's config-protection and GateGuard hooks.

Config protection (`[project].protect_config`, on by default): a member may not change an existing
linter or formatter config (ESLint, Prettier, Ruff, Stylelint, Biome, markdownlint, ...). Agents
too often weaken the check instead of fixing the code. When the task itself names the file, the
change goes through.

Facts first (`[project].gate_sensitive`, on by default): a change to a sensitive file (CI
workflows, database migrations, authentication, payment, secrets and keys, deployment files) is
held back until the member states the facts it rests on, in a line of its reply:

    WHY .github/workflows/ci.yml: the test job must run on Python 3.13; nothing else calls it; CI proves it

A held-back change is reported to the member like an edit that didn't apply, so it resends it with
the facts. Both guards apply to every member that writes files in build and fix.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .config import Team

PROTECTED_NAMES = {
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
    ".prettierrc", ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.json", ".prettierrc.yml", ".prettierrc.yaml",
    "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs",
    "biome.json", "biome.jsonc", ".biome.json", ".biome.jsonc", ".ruff.toml", "ruff.toml", ".flake8", ".pylintrc",
    "mypy.ini", ".mypy.ini", ".shellcheckrc", ".stylelintrc", ".markdownlint.json", ".markdownlint.jsonc",
    ".markdownlint.yaml", ".markdownlint.yml", ".markdownlintrc", ".editorconfig", ".rubocop.yml", ".golangci.yml",
    ".golangci.yaml", "clippy.toml", ".clippy.toml", "rustfmt.toml", ".rustfmt.toml", "detekt.yml", ".swiftlint.yml",
    "checkstyle.xml", ".clang-format", ".clang-tidy", "stylecop.json", ".eslintignore", ".prettierignore",
    ".stylelintignore", ".markdownlintignore",
}
PROTECTED_RE = [
    re.compile(r"^(eslint|prettier|stylelint|commitlint|oxlint)\.config(\.[\w-]+)*\.(js|mjs|cjs|ts|mts|cts)$", re.I),
    re.compile(r"^\.(eslintrc|prettierrc|stylelintrc|markdownlintrc)(\.[\w-]+)*\.(js|cjs|mjs|json|jsonc|yml|yaml|toml)$", re.I),
]
SENSITIVE_RE = [
    (re.compile(r"^\.github/workflows/|^\.gitlab-ci\.yml$|^azure-pipelines\.ya?ml$|^Jenkinsfile$|^\.circleci/"), "CI pipeline"),
    (re.compile(r"(^|/)(migrations?|alembic|db/migrate)/"), "database migration"),
    (re.compile(r"(^|/)(auth|authentication|authorization|oauth|login|session|permissions?)([/._-]|$)", re.I), "authentication"),
    (re.compile(r"(^|/)(payments?|billing|checkout|stripe)([/._-]|$)", re.I), "payment"),
    (re.compile(r"(^|/)(secrets?|credentials?|\.env[\w.]*|.*\.(pem|key|p12|pfx))$", re.I), "secrets"),
    (re.compile(r"(^|/)(Dockerfile|docker-compose\.ya?ml|compose\.ya?ml|.*\.tf|k8s/.*|helm/.*)$"), "deployment"),
]
WHY_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?WHY\s+`?([^\s:`*]+)`?(?:\*\*)?\s*:(?:\*\*)?\s*(.{20,})$", re.M)


def protected(rel: str) -> bool:
    name = Path(rel).name
    return name in PROTECTED_NAMES or name.lower() in PROTECTED_NAMES or any(r.match(name) for r in PROTECTED_RE)


def sensitive(rel: str) -> str:
    """What kind of sensitive file `rel` is ("" if it isn't)."""
    for pattern, kind in SENSITIVE_RE:
        if pattern.search(rel):
            return kind
    return ""


def make(team: Team, task: str) -> Callable[[str, bool, str], str] | None:
    """A guard for files.write_files: (path, exists, whole reply) -> why it's held back, or ""."""
    p = team.project
    if not (p.protect_config or p.gate_sensitive):
        return None

    def guard(rel: str, exists: bool, reply: str) -> str:
        if p.protect_config and exists and protected(rel) and Path(rel).name not in task:
            return (f"{rel} is a linter or formatter config, and the team doesn't weaken checks to make them pass: "
                    f"fix the code instead (if the task needs this file changed, the task must name it)")
        kind = sensitive(rel) if p.gate_sensitive else ""
        if kind and not any(path.strip("`") == rel for path, _ in WHY_RE.findall(reply)):
            return (f"{rel} is a sensitive file ({kind}), so the change waits for the facts it rests on. Resend it "
                    f"with a line `WHY {rel}: ...` that says what uses this file, what the change could break, and "
                    f"how it's checked")
        return ""
    return guard
