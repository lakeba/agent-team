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
release = "ask"                       # ask: the devops shift proposes releases, you approve them; auto: it releases

[project.marketing]
brief = "BRIEF.md"
site = "site/index.html"
deck = "deck/index.html"

# Providers: how to reach models. Add as many as you like, on this machine or others.
[providers.claude]
kind = "anthropic"                    # uses ANTHROPIC_API_KEY (or set api_key_env)

[providers.local]
kind = "ollama"
url = "{ollama_url}"

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
# owns = ["{test_dir}"]

# [[agents]]                          # updates README, docs/ and CHANGELOG.md after approval
# name = "Quill"
# role = "docs"
# provider = "claude"
# model = "claude-haiku-5-5"

# Paths whose changes need your approval before merging (agent-team approve <PR>):
# require_approval = ["auth/", "package.json"]      (goes under [project])

# Pick the model by difficulty: add escalate_to = "<stronger member>" to a member, and
# [routing]
# escalate_after = 1
# light_model = "claude-haiku-5-5"     # sign-offs and fact-checks

# Messages to Slack or any webhook; save the URL with: agent-team keys set AGENT_TEAM_WEBHOOK
# [notify]
# webhook_env = "AGENT_TEAM_WEBHOOK"

# Spend limits in US dollars; a run stops before the next model call once it reaches one.
# [limits]
# per_run = 5.0
# per_day = 20.0
'''

DEFAULT_OLLAMA = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.8:27b-mlx"
TEST_DIRS = ("tests/", "test/", "__tests__/", "spec/")
# `dotnet test` summary lines: VSTest prints "Passed!  - Failed: 0, Passed: 12, ...", the
# Microsoft.Testing.Platform runner prints "succeeded: 12".
DOTNET = ("dotnet test", r"(?:Passed:|succeeded:)\s+(\d+)")
DOTNET_SOLUTIONS = ("*.sln", "*.slnx")
DOTNET_PROJECTS = ("*.csproj", "*.fsproj", "*.vbproj")

# package.json "test" script -> CI count regex, by the runner it names (first match wins).
NODE_RUNNERS = [
    ("node --test", r"(?:#|ℹ) tests (\d+)"),        # node's built-in runner: TAP in CI, spec in a terminal
                                                      # (no ^: CI logs put a timestamp before each line)
    ("vitest", r"Tests\s+(\d+) passed"),
    ("mocha", r"(\d+) passing"),
    ("jest", r"Tests:\s+(?:\d+ \w+, )*(\d+) total"),
]

DETECT = [  # (marker file, test command, CI count regex)
    ("package.json", "npm test", r"Tests:\s+(?:\d+ \w+, )*(\d+) total"),
    ("pyproject.toml", "python -m pytest -q", r"(\d+) passed"),
    ("setup.py", "python -m pytest -q", r"(\d+) passed"),
    ("go.mod", "go test ./...", ""),   # go test prints no total; leave the count unverified
    ("Cargo.toml", "cargo test", r"test result: ok\. (\d+) passed"),
]


def is_dotnet(root: Path, nested: bool = True) -> bool:
    """A .NET project: a solution or project file at the top, or (nested) a project file a few
    folders down, as in src/App/App.csproj."""
    globs = DOTNET_SOLUTIONS + DOTNET_PROJECTS
    if any(any(root.glob(g)) for g in globs):
        return True
    return nested and any(any(root.glob(f"{d}{g}")) for d in ("*/", "*/*/") for g in DOTNET_PROJECTS)


def detect(root: Path) -> tuple[str, str]:
    if is_dotnet(root, nested=False):   # a solution at the top wins over a package.json for tooling
        return DOTNET
    for marker, cmd, pattern in DETECT:
        if (root / marker).exists():
            if marker == "package.json":
                scripts = json.loads((root / marker).read_text(encoding="utf-8")).get("scripts", {})
                if "test" not in scripts:
                    return "", pattern
                script = scripts["test"]
                pattern = next((p for runner, p in NODE_RUNNERS if runner in script), pattern)
            return cmd, pattern
    if is_dotnet(root):
        return DOTNET
    if any(root.glob("test_*.py")) or any(root.glob("tests/test_*.py")):
        return "python3 -m unittest -v", r"Ran (\d+) tests?"
    return "", r"Ran (\d+) tests?"


def test_dir(root: Path) -> str:
    """The folder the project keeps its tests in (what a QA member may write to)."""
    found = next((d for d in TEST_DIRS if (root / d.rstrip("/")).is_dir()), "")
    if not found:   # .NET keeps each test project in its own folder: App.Tests/, App.UnitTests/
        found = next((f"{p.name}/" for p in sorted(root.iterdir()) if p.is_dir() and p.name.endswith((".Tests", ".UnitTests"))), "")
    return found or "tests/"


def choose_model(models: list[str] | None, wanted: str = "") -> tuple[str, str]:
    """(model, note) for the builder, from what the Ollama server actually has pulled."""
    if wanted:
        if models is not None and wanted not in models and f"{wanted}:latest" not in models:
            return wanted, f"{wanted} isn't pulled on that server yet (ollama pull {wanted})"
        return wanted, ""
    if not models:
        return DEFAULT_MODEL, ("couldn't list the server's models; check the builder's model with `ollama list`"
                               if models is None else "the server has no models yet; pull one and set the builder's model")
    def score(name: str) -> tuple:
        n = name.lower()
        return ("coder" in n, "qwen" in n, any(s in n for s in ("27b", "32b", "30b", "34b")), "embed" not in n)
    candidates = [m for m in models if "embed" not in m.lower()] or models
    best = max(candidates, key=score)
    return best, f"chose {best} from the {len(models)} models on that server (others: {', '.join(m for m in models if m != best)[:120] or 'none'})"


def github_repo(root: Path) -> str:
    r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", r.stdout.strip())
    return m.group(1) if m else ""


BUILDER_PROVIDERS = {"local": "local", "ollama": "local", "claude": "claude", "anthropic": "claude"}


def without_claude(text: str, model: str) -> str:
    """The starter file with every member on the Ollama connection and no Claude connection."""
    for claude_model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
        text = text.replace(f'provider = "claude"\nmodel = "{claude_model}"', f'provider = "local"\nmodel = "{model}"')
        text = text.replace(f'# provider = "claude"\n# model = "{claude_model}"', f'# provider = "local"\n# model = "{model}"')
    text = text.replace('[providers.claude]\nkind = "anthropic"                    # uses ANTHROPIC_API_KEY (or set api_key_env)\n',
                        '# [providers.claude]                 # add Claude later: uncomment, point members at it, and\n'
                        '# kind = "anthropic"                 # save the key with: agent-team keys set ANTHROPIC_API_KEY\n')
    return text


def run(root: Path, builder_provider: str = "local", builder_model: str = "", force: bool = False,
        ollama_url: str = "", no_claude: bool = False) -> Path:
    path = root / CONFIG_NAME
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists (use --force to overwrite).")
    if builder_provider not in BUILDER_PROVIDERS:
        raise SystemExit(f"--builder-provider is local (Ollama) or claude, not {builder_provider!r}")
    builder_provider = BUILDER_PROVIDERS[builder_provider]   # accept the kind ("ollama") as well as the name
    if no_claude and builder_provider == "claude":
        raise SystemExit("--no-claude puts every member on Ollama; leave out --builder-provider claude")
    test_command, pattern = detect(root)
    from ..readiness import ollama_models
    ollama_url = (ollama_url or DEFAULT_OLLAMA).rstrip("/")
    note = ""
    if builder_provider == "local":
        builder_model, note = choose_model(ollama_models(ollama_url), builder_model)
    elif not builder_model:
        builder_model = "claude-sonnet-5-5" if builder_provider == "claude" else DEFAULT_MODEL
    skip = [s for s in ["node_modules/", ".next/", "dist/", "build/", "site/", "deck/"]
            if (root / s.rstrip("/")).exists() or s in ("site/", "deck/")]
    text = TEMPLATE.format(
        name=root.resolve().name, repo=github_repo(root), test_command=test_command, pattern=pattern,
        skip=", ".join(f'"{s}"' for s in skip), builder_provider=builder_provider, builder_model=builder_model,
        ollama_url=ollama_url, test_dir=test_dir(root))
    if no_claude:
        text = without_claude(text, builder_model)
    path.write_text(text, encoding="utf-8")
    from ..config import ConfigError, load
    try:
        load(root)   # never leave a file the CLI can't read
    except ConfigError as e:
        path.unlink()
        raise SystemExit(f"init produced an invalid {CONFIG_NAME} ({e}); nothing was written. Please report this.")
    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [x for x in (".team/", ".team.toml.bak") if x not in lines]
    if missing:
        lines += ["", "# agent-team logs, runs and the dashboard's backup", *missing]
    have = {x.strip().strip("/").lower() for x in lines}
    build_output = [f"{d}/" for d in ("bin", "obj") if is_dotnet(root) and not have & {d, f"[{d[0]}{d[0].upper()}]{d[1:]}".lower()}]
    if build_output:
        lines += ["", "# .NET build output", *build_output]
    if missing or build_output:
        gitignore.write_text("\n".join(lines).lstrip() + "\n", encoding="utf-8")
    ui.action(f"wrote {path} (test command: {test_command or 'none detected'}; repo: {github_repo(root) or 'none'})")
    if note:
        ui.say(f"Builder model: {note}.")
    ui.say("Edit the guarantees and team, then run `agent-team doctor`.")
    return path
