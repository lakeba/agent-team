"""init: write a starter .team.toml for a project, guessing its test command and GitHub repo."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .. import ui
from ..composition import DEFAULT_MODEL, DEFAULT_OLLAMA, EXTRAS, MAX_BUILDERS, MODELS, Composition
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

{providers}
{agents}
# Paths whose changes need your approval before merging (agent-team approve <PR>):
# require_approval = ["auth/", "package.json"]      (goes under [project])

# Pick the model by difficulty: add escalate_to = "<stronger member>" to a member, and
# [routing]
# escalate_after = 1
# light_model = "claude-haiku-5-5"     # sign-offs and fact-checks

# Messages to Slack or any webhook; save the URL with: agent-team keys set AGENT_TEAM_WEBHOOK
# [notify]
# webhook_env = "AGENT_TEAM_WEBHOOK"

{limits}'''

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

DETECT = [  # (marker file, test command, CI count regex); Python projects are handled by python_tests
    ("package.json", "npm test", r"Tests:\s+(?:\d+ \w+, )*(\d+) total"),
    ("go.mod", "go test ./...", ""),   # go test prints no total; leave the count unverified
    ("Cargo.toml", "cargo test", r"test result: ok\. (\d+) passed"),
]
PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")
PYTEST_CONFIG = ("pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini", "requirements.txt",
                 "requirements-dev.txt", "requirements-test.txt")
UNITTEST_COUNT = r"Ran (\d+) tests?"


def uses_pytest(root: Path) -> bool:
    """Whether the project runs its tests with pytest: a conftest.py, pytest named in its config or
    requirements, or a test file importing it. Otherwise its tests are plain unittest."""
    if (root / "conftest.py").exists() or (root / "pytest.ini").exists():
        return True
    for name in PYTEST_CONFIG:
        f = root / name
        if f.is_file() and "pytest" in f.read_text(encoding="utf-8", errors="replace"):
            return True
    files = [*root.glob("test_*.py"), *root.glob("tests/**/test_*.py"), *root.glob("tests/**/conftest.py")]
    return any(re.search(r"^\s*(import|from) pytest\b", f.read_text(encoding="utf-8", errors="replace"), re.M)
               for f in files[:50])


def python_tests(root: Path) -> tuple[str, str]:
    """The test command for a Python project. `python3` because many Linux machines have no
    `python`, and CI runners have both."""
    if uses_pytest(root):
        return "python3 -m pytest -q", r"(\d+) passed"
    tests = next((d.rstrip("/") for d in ("tests/", "test/") if any((root / d).glob("**/test*.py"))), "")
    if tests:
        return f"python3 -m unittest discover -s {tests} -v", UNITTEST_COUNT
    return "python3 -m unittest -v", UNITTEST_COUNT


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
    if any((root / m).exists() for m in PYTHON_MARKERS):
        return python_tests(root)
    if is_dotnet(root):
        return DOTNET
    if any(root.glob("test_*.py")) or any(root.glob("tests/test_*.py")):
        return python_tests(root)
    return "", UNITTEST_COUNT


def test_dir(root: Path) -> str:
    """The folder the project keeps its tests in (what a QA member may write to), spelled as it is on
    disk: `Tests/` stays `Tests/` (paths are case-sensitive on Linux and in git, even where the disk
    isn't)."""
    folders = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    by_lower = {name.lower(): name for name in folders}
    found = next((f"{by_lower[d.rstrip('/')]}/" for d in TEST_DIRS if d.rstrip("/") in by_lower), "")
    if not found:   # .NET keeps each test project in its own folder: App.Tests/, App.UnitTests/
        found = next((f"{n}/" for n in folders if n.lower().endswith((".tests", ".unittests"))), "")
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


def set_ollama_url(path: Path, url: str) -> list[tuple[str, str]]:
    """Point the team's Ollama connections at url, editing only their url lines so comments and
    the rest of the file stay as they are. Connections already on another machine (not localhost)
    are left alone when there is also a local one. Returns [(connection, old url)] for each change."""
    import tomllib
    from ..readiness import is_local
    url = url.rstrip("/")
    providers = tomllib.loads(path.read_text(encoding="utf-8")).get("providers", {})
    ollama = {n: p.get("url", "") for n, p in providers.items() if p.get("kind") == "ollama"}
    local = {n: u for n, u in ollama.items() if not u or is_local(u)}
    targets = {n: u for n, u in (local or ollama).items() if u.rstrip("/") != url}
    if not targets:
        return []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out, section, done = [], "", set()
    for line in lines:
        head = re.match(r"\s*\[([^\[\]]+)\]\s*(#.*)?$", line)
        if head:
            if section in targets and section not in done:   # the section had no url line: add one
                out.append(f'url = "{url}"\n')
                done.add(section)
            section = head.group(1).strip().removeprefix("providers.") if head.group(1).strip().startswith("providers.") else ""
        elif section in targets and re.match(r"\s*url\s*=", line):
            out.append(re.sub(r'=\s*"[^"]*"', f'= "{url}"', line, count=1))
            done.add(section)
            continue
        out.append(line)
    if section in targets and section not in done:
        out.append(f'url = "{url}"\n')
    path.write_text("".join(out), encoding="utf-8")
    return sorted(targets.items())


class Cancelled(SystemExit):
    pass


def _ask(question: str, default: str = "") -> str:
    try:
        answer = input(f"{question}{f' [{default}]' if default else ''}: ").strip()
    except (EOFError, KeyboardInterrupt):
        ui.say()
        raise Cancelled("Cancelled; nothing was written.")
    return answer or default


def ask_choice(question: str, options: list[tuple[str, str]], default: str) -> str:
    """One of the option keys: by number or by key, Enter for the default."""
    ui.say(question)
    for i, (key, about) in enumerate(options, 1):
        ui.say(f"  {i}. {about}{'  (default)' if key == default else ''}")
    keys = [k for k, _ in options]
    while True:
        a = _ask("Choose", str(keys.index(default) + 1)).lower()
        if a.isdigit() and 1 <= int(a) <= len(keys):
            return keys[int(a) - 1]
        if a in keys:
            return a
        ui.say(f"  Type a number from 1 to {len(keys)}.")


def ask_number(question: str, default: float, low: float, high: float, whole: bool = False) -> float:
    while True:
        a = _ask(question, f"{default:g}")
        try:
            v = int(a) if whole else float(a.lstrip("$"))
        except ValueError:
            v = None
        if v is not None and low <= v <= high:
            return v
        ui.say(f"  A {'whole ' if whole else ''}number from {low:g} to {high:g}.")


def ask_yes(question: str, default: bool = True) -> bool:
    while True:
        a = _ask(question + (" [Y/n]" if default else " [y/N]")).lower()
        if not a:
            return default
        if a in ("y", "yes", "n", "no"):
            return a.startswith("y")


def find_server(given: str, interactive: bool) -> tuple[str, list[str] | None, str, str]:
    """(url, its models or None, note, kind): the address given, else the first local model server
    that answers (Ollama, or an OpenAI-compatible one such as mlx_lm) on this machine, its host (in a
    VM or container) or the gateway; in a terminal, the user picks. kind is ollama or openai."""
    from ..readiness import find_local, probe
    if given:
        url = given.rstrip("/")
        from ..config import address_problem
        if address_problem(url):
            raise SystemExit(address_problem(url))
        found = probe(url, timeout=5)
        return url, (found or {}).get("models"), "", (found or {}).get("kind", "ollama")
    found = find_local()
    if not found:   # nothing nearby: look at the other computers on the local networks too
        found = find_local(scan=True)
    if not interactive:
        if found:
            f = found[0]
            note = "" if f["url"] == DEFAULT_OLLAMA else f"found {f['label']} at {f['url']}"
            return f["url"], f["models"], note, f["kind"]
        from ..readiness import ollama_models
        models = ollama_models(DEFAULT_OLLAMA)
        return DEFAULT_OLLAMA, models, ("" if models is not None else
                                        "no local model server answered here or on the host (Ollama, mlx_lm...); set "
                                        "its address later with agent-team init --ollama-url http://HOST:PORT"), "ollama"
    options = [(f["url"], f"{f['url']}  ({f['label']}, {len(f['models'])} models)") for f in found] + [("other", "Another address")]
    if not found:
        ui.say("No local model server (Ollama, mlx_lm, LM Studio...) answered on this machine, its host or the gateway.")
    choice = ask_choice("Which local model server should the team use?", options, options[0][0]) if found else "other"
    if choice != "other":
        f = next(x for x in found if x["url"] == choice)
        return f["url"], f["models"], "", f["kind"]
    while True:
        from ..readiness import _ollama_url
        raw = _ask("Server address (e.g. http://192.168.1.20:11434 for Ollama, http://HOST:8080 for mlx_lm)", DEFAULT_OLLAMA)
        url = raw.rstrip("/") if re.search(r":\d+$", raw.rstrip("/").split("//")[-1]) else _ollama_url(raw)
        f = probe(url, timeout=5)
        if f or ask_yes(f"{url} doesn't answer. Use it anyway?", default=False):
            return url, (f or {}).get("models"), "", (f or {}).get("kind", "ollama")


def write_vision(root: Path, text: str) -> str:
    """Save the owner's product vision as VISION.md (unless the project has one). `text` may also be
    the path of a file holding it. Returns what was done, for the summary."""
    text = text.strip()
    if text and Path(text).expanduser().is_file():
        text = Path(text).expanduser().read_text(encoding="utf-8").strip()
    if not text:
        return ""
    path = root / "VISION.md"
    if path.exists():
        return "VISION.md already exists, so it was left as it is"
    body = text if text.lstrip().startswith("#") else f"# Vision\n\n{text}"
    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return "saved the vision as VISION.md: every workflow reads it, and /team-plan plans the roadmap from it"


def setup_rea(root: Path, use_rea: bool | None, interactive: bool) -> str:
    """Behaviour checks: when REA is on this machine, add [mcp.rea] and [behaviour] (asking first in a
    terminal). Returns a note for the summary."""
    if use_rea is False:
        return ""
    from .. import rea
    command, args, where = rea.find()
    if not command and interactive and use_rea is not False and not os.environ.get("AGENT_TEAM_NO_REA_UPDATE") and \
            rea.node_ok()[0] and \
            ask_yes(f"Install REA {rea.VERSION}? Behaviour checks and Inspire use it (a minute or two)"):
        try:
            rea.install(yes=True)
            command, args, where = rea.find()
            use_rea = True
        except SystemExit as e:
            ui.say(str(e))
    if not command:
        return ("Behaviour checks (the team uses the program like a user, before and after each change) and Inspire "
                "need REA: agent-team rea setup")
    if interactive and use_rea is None and not ask_yes(f"REA is installed ({where}). Use it for behaviour checks?"):
        return ""
    rea.configure(root, command, args)
    return ("Behaviour checks are set up with REA. Next: agent-team behaviour suggest (the lead writes the first "
            "journeys), or /team-build writes them as it goes.")


def ask_vision(root: Path) -> str:
    if (root / "VISION.md").exists():
        ui.say("The product vision: VISION.md (already written).\n")
        return ""
    ui.say("What should this product be? Who is it for, what problem does it solve, what makes it worth using.\n"
           "A sentence or a short paragraph; the team plans its roadmap from it (Enter to skip, write VISION.md later).")
    return _ask("Vision")


def ask_inspiration() -> str:
    """An app the founder likes (optional): its address, once they confirm they may look at it."""
    from .. import inspire
    ui.say("Is there an app you like? The team can look at it the way a visitor does and plan your product with\n"
           "it in mind, never copying it (Enter to skip).")
    url = _ask("Its web address").strip()
    if not url:
        return ""
    try:
        url = inspire.check_url(url)
    except inspire.InspireError as e:
        ui.say(f"  Skipped: {e}. Later: agent-team inspire <address>.")
        return ""
    ui.say(inspire.CONFIRMATION)
    return url if ask_yes("Is that right?", default=False) else ""


def ask_composition(c: Composition, asked: dict) -> None:
    """Fill in, by asking, every choice the flags left open (keys of `asked` that are None)."""
    if asked["models"] is None:
        c.models = ask_choice("Where should the members' models run?", list(MODELS.items()), "mixed")
    if asked["extras"] is None:
        ui.say("Optional members (the core team is a lead, builder, marketing and devops):")
        for role, (name, about) in EXTRAS.items():
            ui.say(f"  {name} ({role}): {about}")
        picked = _ask("Add which? (e.g. security,qa,docs; all; none)", "none").lower().replace(" ", "")
        names = {name.lower(): role for role, (name, _) in EXTRAS.items()}
        chosen = list(EXTRAS) if picked == "all" else [names.get(x, x) for x in picked.split(",") if x and x != "none"]
        unknown = [x for x in chosen if x not in EXTRAS]
        if unknown:
            ui.say(f"  Skipping {', '.join(unknown)}: the optional members are {', '.join(EXTRAS)}.")
        c.extras = tuple(x for x in EXTRAS if x in chosen)
    if asked["builders"] is None:
        c.builders = int(ask_number(f"How many builders? (more than one lets build --parallel split a plan)", 1, 1,
                                    MAX_BUILDERS, whole=True))
    if asked["limits"] is None and c.uses_claude:
        if ask_yes("Set spend limits for Claude calls?", default=False):
            c.per_run = ask_number("Limit per run, US dollars (0: none)", 5, 0, 10000)
            c.per_day = ask_number("Limit per day, US dollars (0: none)", 20, 0, 100000)


def run(root: Path, builder_provider: str = "local", builder_model: str = "", force: bool = False,
        ollama_url: str = "", no_claude: bool = False, *, models: str | None = None,
        extras: tuple[str, ...] | None = None, builders: int | None = None,
        per_run: float | None = None, per_day: float | None = None, interactive: bool = False,
        vision: str | None = None, use_rea: bool | None = None, inspire_url: str | None = None) -> Path:
    """Write a starter .team.toml. Every choice left as None is asked in a terminal (interactive)
    or takes its default."""
    path = root / CONFIG_NAME
    if path.exists() and not force:
        if ollama_url:   # the team exists: point it at that Ollama server and keep everything else
            changed = set_ollama_url(path, ollama_url)
            if changed:
                for name, old in changed:
                    ui.say(f"Updated [providers.{name}] in {CONFIG_NAME}: {old or '(no url)'} -> {ollama_url.rstrip('/')}")
                return path
            raise SystemExit(f"{path} already exists and has no Ollama connection to point at {ollama_url}. "
                             f"Add one under [providers], or rewrite the file with --force.")
        raise SystemExit(f"{path} already exists, so nothing was changed. To point it at Ollama on another "
                         f"machine: agent-team init --ollama-url http://HOST:11434. To start over: --force.")
    if builder_provider not in BUILDER_PROVIDERS:
        raise SystemExit(f"--builder-provider is local (Ollama) or claude, not {builder_provider!r}")
    builder_provider = BUILDER_PROVIDERS[builder_provider]   # accept the kind ("ollama") as well as the name
    if no_claude and builder_provider == "claude":
        raise SystemExit("--no-claude puts every member on Ollama; leave out --builder-provider claude")
    if models is None and (no_claude or builder_provider == "claude"):
        models = "ollama" if no_claude else "claude"
    if models is not None and models not in MODELS:
        raise SystemExit(f"--models is one of {', '.join(MODELS)}, not {models!r}")
    test_command, pattern = detect(root)
    c = Composition(models=models or "mixed", extras=tuple(extras or ()), builders=builders or 1,
                    per_run=per_run or 0.0, per_day=per_day or 0.0, test_dir=test_dir(root))
    if interactive:
        ui.heading(f"Setting up a team for {root.resolve().name}")
        ui.say("Press Enter to take the default shown in brackets.\n")
        if vision is None:
            vision = ask_vision(root)
        if inspire_url is None:
            inspire_url = ask_inspiration()
        ask_composition(c, {"models": models, "extras": extras, "builders": builders,
                            "limits": None if per_run is None and per_day is None else True})
    try:
        c.check()
    except ValueError as e:
        raise SystemExit(str(e))
    note = ""
    if c.uses_ollama:
        c.ollama_url, server_models, found_note, c.local_kind = find_server(ollama_url, interactive)
        c.ollama_model, note = choose_model(server_models, builder_model)
        note = "; ".join(n for n in (found_note, note) if n)
    if builder_model and c.provider("builder") == "claude":
        c.builder_model = builder_model
    if interactive:
        ui.say(f"\nThe team: {c.summary()}.")
        if not ask_yes(f"Write {CONFIG_NAME}?"):
            raise Cancelled("Nothing was written.")
    skip = [s for s in ["node_modules/", ".next/", "dist/", "build/", "site/", "deck/"]
            if (root / s.rstrip("/")).exists() or s in ("site/", "deck/")]
    from ..composition import agents_text, limits_text, providers_text
    text = TEMPLATE.format(
        name=root.resolve().name, repo=github_repo(root), test_command=test_command, pattern=pattern,
        skip=", ".join(f'"{s}"' for s in skip), providers=providers_text(c), agents=agents_text(c),
        limits=limits_text(c))
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
    rea_note = setup_rea(root, use_rea, interactive)
    if inspire_url:   # confirmed by the founder when asked
        from .. import inspire
        inspire.confirm(root, inspire_url)
        rea_note = (rea_note + "\n" if rea_note else "") + (
            f"Next: agent-team inspire {inspire_url} explores the app you like; the lead plans from its brief in discuss.")
    vision_note = write_vision(root, vision or "")
    if vision_note:
        ui.say(vision_note[0].upper() + vision_note[1:] + ".")
    if rea_note:
        ui.say(rea_note)
    ui.say("Edit the guarantees and team, then run `agent-team doctor`.")
    return path
