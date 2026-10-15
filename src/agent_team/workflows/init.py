"""init: write a starter .team.toml for a project, guessing its test command and GitHub repo."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .. import ui
from ..config import CONFIG_NAME

TEMPLATE = '''# agent-team configuration. Docs: https://github.com/lakeba/agent-team/blob/main/docs/configuration.md

[project]
name = "{name}"
repo = "{repo}"                       # owner/name on GitHub ("" if none yet)
test_command = "{test_command}"
test_count_pattern = '{pattern}'       # regex with one group, matched in CI logs
guarantees = [
  # Rules the lead enforces in every review. Replace these examples with your project's own.
  "All tests pass before merge",
  "No secrets or credentials in the repository",
]
context_skip = [{skip}]               # path prefixes never sent to the models
context_limit = 200000

[project.marketing]
brief = "BRIEF.md"
site = "site/index.html"
deck = "deck/index.html"

# Providers: how to reach models. Add as many as you like, on this machine or others.
[providers.claude]
kind = "anthropic"                    # uses ANTHROPIC_API_KEY (or set api_key_env)

[providers.local]
kind = "ollama"
url = "http://localhost:11434"

# [providers.gpu-box]                 # another machine running Ollama
# kind = "ollama"
# url = "http://gpu-box.local:11434"

# [providers.remote-forge]            # a teammate running `agent-team serve` elsewhere
# kind = "agent-http"
# url = "http://10.0.0.20:8765"
# api_key_env = "FORGE_NODE_TOKEN"

# Team members. Add, remove or rename freely; workflows find members by role.
[[agents]]
name = "Atlas"
role = "lead"
provider = "claude"
model = "claude-opus-5-5"
owns = ["ROADMAP.md"]

[[agents]]
name = "Forge"
role = "builder"
provider = "{builder_provider}"
model = "{builder_model}"

[[agents]]
name = "Spark"
role = "marketing"
provider = "claude"
model = "claude-sonnet-5-5"
owns = ["BRIEF.md", "site/", "deck/"]

[[agents]]
name = "Harbor"
role = "devops"
provider = "claude"
model = "claude-sonnet-5-5"
effort = "medium"

# Any member can take skills: Markdown files or skill folders (with SKILL.md) added to its prompt.
#   skills = ["team/skills/conventions.md", "~/.claude/skills/security-review"]

# Optional members. Uncomment any of them; `build` uses them automatically (skip with --skip).
# [[agents]]                          # reviews every approved build; a NO sends it back
# name = "Sentinel"
# role = "security"
# provider = "claude"
# model = "claude-sonnet-5-5"
# owns = ["*"]                        # "*": must also sign off every pull request

# [[agents]]                          # writes the tests for a plan before anyone builds it
# name = "Probe"
# role = "qa"
# provider = "claude"
# model = "claude-sonnet-5-5"
# owns = ["tests/"]

# [[agents]]                          # updates README, docs/ and CHANGELOG.md after approval
# name = "Quill"
# role = "docs"
# provider = "claude"
# model = "claude-haiku-5-5"

# Spend limits in US dollars; a run stops before the next model call once it reaches one.
# [limits]
# per_run = 5.0
# per_day = 20.0
'''

DETECT = [  # (marker file, test command, CI count regex)
    ("package.json", "npm test", r"Tests:\s+(?:\d+ \w+, )*(\d+) total"),
    ("pyproject.toml", "python -m pytest -q", r"(\d+) passed"),
    ("setup.py", "python -m pytest -q", r"(\d+) passed"),
    ("go.mod", "go test ./...", ""),   # go test prints no total; leave the count unverified
    ("Cargo.toml", "cargo test", r"test result: ok\. (\d+) passed"),
]


def detect(root: Path) -> tuple[str, str]:
    for marker, cmd, pattern in DETECT:
        if (root / marker).exists():
            if marker == "package.json":
                scripts = json.loads((root / marker).read_text(encoding="utf-8")).get("scripts", {})
                if "test" not in scripts:
                    return "", pattern
            return cmd, pattern
    if any(root.glob("test_*.py")) or any(root.glob("tests/test_*.py")):
        return "python3 -m unittest -v", r"Ran (\d+) tests?"
    return "", r"Ran (\d+) tests?"


def github_repo(root: Path) -> str:
    r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", r.stdout.strip())
    return m.group(1) if m else ""


def run(root: Path, builder_provider: str = "local", builder_model: str = "qwen3.8:27b-mlx", force: bool = False) -> Path:
    path = root / CONFIG_NAME
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists (use --force to overwrite).")
    test_command, pattern = detect(root)
    skip = [s for s in ["node_modules/", ".next/", "dist/", "build/", "site/", "deck/"]
            if (root / s.rstrip("/")).exists() or s in ("site/", "deck/")]
    path.write_text(TEMPLATE.format(
        name=root.resolve().name, repo=github_repo(root), test_command=test_command, pattern=pattern,
        skip=", ".join(f'"{s}"' for s in skip), builder_provider=builder_provider, builder_model=builder_model),
        encoding="utf-8")
    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [x for x in (".team/", ".team.toml.bak") if x not in lines]
    if missing:
        gitignore.write_text("\n".join(lines + ["", "# agent-team logs, runs and the dashboard's backup", *missing]).lstrip() + "\n",
                             encoding="utf-8")
    ui.action(f"wrote {path} (test command: {test_command or 'none detected'}; repo: {github_repo(root) or 'none'})")
    ui.say("Edit the guarantees and team, then run `agent-team doctor`.")
    return path
