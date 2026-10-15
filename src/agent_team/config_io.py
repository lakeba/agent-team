"""Writing `.team.toml` safely: render, validate by reading it back, show the diff, back up, then save.

The standard library reads TOML but can't write it, so this module renders the one structure a
team file has. Comments in a hand-written file are not kept; every save leaves the previous file
as `.team.toml.bak`.
"""
from __future__ import annotations

import difflib
import os
import re
import tempfile
import tomllib
from dataclasses import asdict, fields
from pathlib import Path

from .config import CONFIG_NAME, AgentConfig, ConfigError, ProjectConfig, ProviderConfig, Team, parse

HEADER = ("# agent-team configuration. Docs: https://github.com/lakeba/agent-team/blob/main/docs/configuration.md\n"
          "# Secrets never go here: providers name the environment variable that holds them.\n")
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _str(s: str) -> str:
    # Backslash-heavy strings (regexes, Windows paths) read best as TOML literal strings.
    if "\\" in s and "'" not in s and not any(ord(c) < 0x20 or ord(c) == 0x7F for c in s):
        return f"'{s}'"
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _key(k: str) -> str:
    return k if _BARE_KEY.match(k) else _str(k)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + " }"
    raise ConfigError(f"can't write a value of type {type(v).__name__}")


def _lines(table: dict, skip_empty: bool = True) -> list[str]:
    out = []
    for k, v in table.items():
        if v is None or (skip_empty and v in ("", [], {})):
            continue
        line = f"{_key(k)} = {_value(v)}"
        if isinstance(v, (list, tuple)) and len(line) > 90:   # long lists: one item per line, as people write them
            line = f"{_key(k)} = [\n" + "".join(f"  {_value(x)},\n" for x in v) + "]"
        out.append(line)
    return out


def to_data(team: Team) -> dict:
    """The team as plain data, in the shape of a .team.toml file."""
    project = asdict(team.project)
    marketing = project.pop("marketing") or {}
    defaults = ProjectConfig(name="")
    keep = {"name", "test_count_pattern"}   # written even at its default: it matters and is easy to miss
    project = {k: v for k, v in project.items() if k in keep and v or v != getattr(defaults, k)}
    if marketing:
        project["marketing"] = marketing
    providers = {}
    for name, p in team.providers.items():
        d = asdict(p)
        d.pop("name")
        providers[name] = {k: v for k, v in d.items() if v not in ("", {}, None) or k == "kind"}
    agent_defaults = AgentConfig(name="", role="", provider="")
    agents = [{k: v for k, v in asdict(a).items()
               if k in ("name", "role", "provider") or v != getattr(agent_defaults, k)}
              for a in team.agents.values()]
    return {"project": project, "providers": providers, "pricing": dict(team.pricing), "agents": agents}


def render(data: dict) -> str:
    project = dict(data.get("project") or {})
    marketing = project.pop("marketing", None) or {}
    parts = [HEADER, "[project]", *_lines(project)]
    if marketing:
        parts += ["", "[project.marketing]", *_lines(marketing)]
    for name, p in (data.get("providers") or {}).items():
        parts += ["", f"[providers.{_key(name)}]", *_lines(p)]
    for model, price in (data.get("pricing") or {}).items():
        parts += ["", f"[pricing.{_key(model)}]", *_lines(price, skip_empty=False)]
    for a in data.get("agents") or []:
        parts += ["", "[[agents]]", *_lines(a)]
    return "\n".join(parts) + "\n"


def validate(text: str, root: Path) -> Team:
    """Read the rendered text back exactly as the CLI will; raises ConfigError if it's invalid."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"the rendered file isn't valid TOML: {e}") from None
    return parse(data, root)


def clean(data: dict) -> dict:
    """Keep only the keys the config knows (the API's input is untrusted JSON), and coerce types."""
    if not isinstance(data, dict):
        raise ConfigError("expected an object")
    pf, prf, af = ({f.name for f in fields(c)} for c in (ProjectConfig, ProviderConfig, AgentConfig))
    project = {k: v for k, v in (data.get("project") or {}).items() if k in pf}
    providers = {str(n): {k: v for k, v in (p or {}).items() if k in prf - {"name"}}
                 for n, p in (data.get("providers") or {}).items()}
    agents = [{k: v for k, v in (a or {}).items() if k in af} for a in data.get("agents") or []]
    for a in agents:   # strip blanks from list fields the form may send
        for k in ("owns",):
            if isinstance(a.get(k), list):
                a[k] = [x.strip() for x in a[k] if isinstance(x, str) and x.strip()]
    if isinstance(project.get("guarantees"), list):
        project["guarantees"] = [g.strip() for g in project["guarantees"] if isinstance(g, str) and g.strip()]
    if isinstance(project.get("context_skip"), list):
        project["context_skip"] = [g.strip() for g in project["context_skip"] if isinstance(g, str) and g.strip()]
    pricing = {str(m): {k: v for k, v in (p or {}).items() if k in ("input", "output", "cache_read", "cache_write")}
               for m, p in (data.get("pricing") or {}).items()}
    return {"project": project, "providers": providers, "pricing": pricing, "agents": agents}


def plan_change(root: Path, data: dict) -> dict:
    """What saving `data` would do: the new text, a unified diff, and whether it's valid."""
    path = Path(root) / CONFIG_NAME
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    new = render(clean(data))
    try:
        validate(new, Path(root))
        error = None
    except ConfigError as e:
        error = str(e)
    diff = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile=CONFIG_NAME, tofile=f"{CONFIG_NAME} (new)"))
    return {"valid": error is None, "error": error, "diff": diff, "text": new,
            "comments_lost": any(l.lstrip().startswith("#") for l in old.splitlines()) and old != new}


def save(root: Path, data: dict, expected_old: str | None = None) -> dict:
    """Validate and write. Refuses if the file changed since `expected_old` was read (a concurrent edit)."""
    path = Path(root) / CONFIG_NAME
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if expected_old is not None and old != expected_old:
        raise ConfigError(f"{CONFIG_NAME} changed on disk since you loaded it; reload and try again")
    change = plan_change(root, data)
    if not change["valid"]:
        raise ConfigError(change["error"])
    if old:
        (Path(root) / (CONFIG_NAME + ".bak")).write_text(old, encoding="utf-8")
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".team.toml.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(change["text"])
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return {"saved": True, "backup": CONFIG_NAME + ".bak" if old else None, "diff": change["diff"]}
