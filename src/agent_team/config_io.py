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

from .config import (CONFIG_NAME, AgentConfig, BehaviourConfig, BehaviourScenario, ConfigError, LimitsConfig,
                     McpServerConfig, NotifyConfig, ProjectConfig, ProviderConfig, ResearchConfig, RoutingConfig,
                     SandboxConfig, Team, looks_like_secret, parse)

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
    limits = {k: v for k, v in asdict(team.limits).items() if v}
    routing = {k: v for k, v in asdict(team.routing).items() if v != getattr(RoutingConfig(), k)}
    notify = {k: v for k, v in asdict(team.notify).items() if v != getattr(NotifyConfig(), k)}
    sandbox = {k: v for k, v in asdict(team.sandbox).items() if v != getattr(SandboxConfig(), k)}
    mcp = {}
    for name, s in team.mcp.items():
        d = asdict(s)
        d.pop("name")
        defaults = McpServerConfig(name="", command="")
        mcp[name] = {k: v for k, v in d.items() if k == "command" or v != getattr(defaults, k)}
    behaviour = {}
    if (team.behaviour.scenarios or team.behaviour.server != BehaviourConfig().server
            or team.behaviour.browser):
        sdef = BehaviourScenario(name="")
        behaviour = {"server": team.behaviour.server,
                     **({"browser": team.behaviour.browser} if team.behaviour.browser else {}),
                     # only the ones written here: team/behaviour.toml keeps its own
                     "scenarios": [{k: v for k, v in asdict(sc).items()
                                    if k != "source" and (k == "name" or v != getattr(sdef, k))}
                                   for sc in team.behaviour.scenarios if sc.source == ".team.toml"]}
    research = {k: v for k, v in asdict(team.research).items() if v != getattr(ResearchConfig(), k)}
    return {"project": project, "providers": providers, "pricing": dict(team.pricing), "limits": limits,
            "routing": routing, "notify": notify, "sandbox": sandbox, "mcp": mcp, "behaviour": behaviour,
            "research": research, "agents": agents}


def render(data: dict) -> str:
    project = dict(data.get("project") or {})
    marketing = project.pop("marketing", None) or {}
    parts = [HEADER, "[project]", *_lines(project)]
    if marketing:
        parts += ["", "[project.marketing]", *_lines(marketing)]
    for name, p in (data.get("providers") or {}).items():
        parts += ["", f"[providers.{_key(name)}]", *_lines(p)]
    limits = {k: v for k, v in (data.get("limits") or {}).items() if v}
    if limits:
        parts += ["", "[limits]", *_lines(limits)]
    routing = {k: v for k, v in (data.get("routing") or {}).items() if v not in ("", None)}
    if routing:
        parts += ["", "[routing]", *_lines(routing)]
    notify = {k: v for k, v in (data.get("notify") or {}).items() if v not in ("", None, [])}
    if notify:
        parts += ["", "[notify]", *_lines(notify)]
    sandbox = {k: v for k, v in (data.get("sandbox") or {}).items() if v not in ("", None)}
    if sandbox and sandbox != {"mode": "off"}:
        parts += ["", "[sandbox]", *_lines(sandbox, skip_empty=False)]
    for model, price in (data.get("pricing") or {}).items():
        parts += ["", f"[pricing.{_key(model)}]", *_lines(price, skip_empty=False)]
    for name, s in (data.get("mcp") or {}).items():
        parts += ["", f"[mcp.{_key(name)}]", *_lines(s)]
    research = {k: v for k, v in (data.get("research") or {}).items() if v not in ("", None, [])}
    if research:
        parts += ["", "[research]", *_lines(research)]
    behaviour = dict(data.get("behaviour") or {})
    scenarios = behaviour.pop("scenarios", None) or []
    if behaviour.get("server") and (scenarios or behaviour["server"] != BehaviourConfig().server
                                    or behaviour.get("browser")):
        parts += ["", "[behaviour]", *_lines(behaviour)]
    for sc in scenarios:
        parts += ["", "[[behaviour.scenarios]]", *_lines(sc)]
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
        for k in ("owns", "skills"):
            if isinstance(a.get(k), list):
                a[k] = [x.strip() for x in a[k] if isinstance(x, str) and x.strip()]
    if isinstance(project.get("guarantees"), list):
        project["guarantees"] = [g.strip() for g in project["guarantees"] if isinstance(g, str) and g.strip()]
    if isinstance(project.get("require_approval"), list):
        project["require_approval"] = [g.strip() for g in project["require_approval"] if isinstance(g, str) and g.strip()]
    for k in ("checks", "rules", "library"):
        if isinstance(project.get(k), list):
            project[k] = [g.strip() for g in project[k] if isinstance(g, str) and g.strip()]
    if isinstance(project.get("context_skip"), list):
        project["context_skip"] = [g.strip() for g in project["context_skip"] if isinstance(g, str) and g.strip()]
    pricing = {str(m): {k: v for k, v in (p or {}).items() if k in ("input", "output", "cache_read", "cache_write")}
               for m, p in (data.get("pricing") or {}).items()}
    limits = {}
    for k, v in (data.get("limits") or {}).items():
        if k == "milestones":
            if isinstance(v, dict):
                try:
                    ms = {str(m).strip(): float(x) for m, x in v.items() if str(m).strip() and x not in (None, "")}
                except (TypeError, ValueError):
                    raise ConfigError("[limits.milestones] values must be US dollars") from None
                if ms:
                    limits[k] = ms
            continue
        if k in {f.name for f in fields(LimitsConfig)} and v not in (None, ""):
            try:
                limits[k] = float(v)
            except (TypeError, ValueError):
                raise ConfigError(f"[limits].{k} must be a number of US dollars") from None
    routing = {}
    for k, v in (data.get("routing") or {}).items():
        if k == "escalate_after" and v not in (None, ""):
            try:
                routing[k] = int(v)
            except (TypeError, ValueError):
                raise ConfigError("[routing].escalate_after must be a whole number") from None
        elif k == "light_model" and isinstance(v, str) and v.strip():
            routing[k] = v.strip()
    notify = {k: v for k, v in (data.get("notify") or {}).items()
              if k in {f.name for f in fields(NotifyConfig)} and v not in (None, "")}
    if isinstance(notify.get("events"), list):
        notify["events"] = [e for e in notify["events"] if isinstance(e, str) and e.strip()]
    sandbox = {k: v for k, v in (data.get("sandbox") or {}).items()
               if k in {f.name for f in fields(SandboxConfig)} and v not in (None, "")}
    mf = {f.name for f in fields(McpServerConfig)} - {"name"}
    mcp = {str(n): {k: v for k, v in (s or {}).items() if k in mf} for n, s in (data.get("mcp") or {}).items()}
    btable = data.get("behaviour") or {}
    sf = {f.name for f in fields(BehaviourScenario)}
    behaviour = {}
    if isinstance(btable, dict) and (btable.get("scenarios") or btable.get("server") or btable.get("browser")):
        behaviour = {"server": str(btable.get("server") or BehaviourConfig().server),
                     **({"browser": str(btable["browser"])} if btable.get("browser") else {}),
                     "scenarios": [{k: v for k, v in (sc or {}).items() if k in sf - {"source"}}
                                   for sc in btable.get("scenarios") or [] if isinstance(sc, dict)]}
    rf = {f.name for f in fields(ResearchConfig)}
    research = {k: v for k, v in (data.get("research") or {}).items() if k in rf and v not in (None, "", [])}
    if isinstance(research.get("sites"), list):
        research["sites"] = [u.strip() if isinstance(u, str) else
                             {k: v for k, v in u.items() if k == "url" or v not in (None, "", [])}
                             for u in research["sites"] if (isinstance(u, str) and u.strip()) or isinstance(u, dict)]
    return {"project": project, "providers": providers, "pricing": pricing, "limits": limits, "routing": routing,
            "notify": notify, "sandbox": sandbox, "mcp": mcp, "behaviour": behaviour, "research": research,
            "agents": agents}


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
        for p in (data.get("providers") or {}).values():   # a key pasted as a variable's name stays off the page
            value = str(p.get("api_key_env", "")) if isinstance(p, dict) else ""
            if value and looks_like_secret(value):
                old, new = old.replace(value, "<hidden>"), new.replace(value, "<hidden>")
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
