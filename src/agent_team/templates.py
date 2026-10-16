"""Team templates: common setups applied to a project's config in one step (always reviewed first).

Each template changes the config as plain data (the same shape as `config_io.to_data`): it adds
the members and connections it needs if they're missing, and sets the options it's about. The
dashboard shows the resulting diff before anything is saved.
"""
from __future__ import annotations

import copy

TEMPLATES = [
    {"id": "claude-only", "name": "Claude only",
     "about": "Every member on Claude: Opus leads, Sonnet builds, ships and markets. No local model needed."},
    {"id": "local-builder", "name": "Local builder, Claude backup",
     "about": "The builder runs on your Ollama model; after a rejected round, a Claude builder takes over. "
              "Sign-offs and fact-checks use Haiku."},
    {"id": "full-quality", "name": "Full quality team",
     "about": "Adds Sentinel (security review of every build, signs off every PR), Probe (QA writes tests first) "
              "and Quill (docs after every build)."},
    {"id": "budget", "name": "Budget",
     "about": "Spend limits of $2 per run and $10 per day, Haiku for routine checks, and the cheaper Claude model "
              "for marketing and devops."},
    {"id": "safe-autopilot", "name": "Safe autopilot",
     "about": "Releases need your approval, CI and dependency files need your approval, tests run in a container, "
              "and spend limits are set if they weren't."},
]

LEAD, BUILD, LIGHT = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"


def _claude(d: dict) -> str:
    """The name of a Claude connection, added if there isn't one."""
    for name, p in d["providers"].items():
        if p.get("kind") == "anthropic":
            return name
    d["providers"]["claude"] = {"kind": "anthropic"}
    return "claude"


def _member(d: dict, role: str) -> dict | None:
    return next((a for a in d["agents"] if a.get("role") == role), None)


def _add(d: dict, name: str, role: str, provider: str, model: str, **extra) -> None:
    """Add a member for this role unless the team has one; pick a free name if this one's taken."""
    if _member(d, role):
        return
    taken = {a.get("name") for a in d["agents"]}
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name}{n}", n + 1
    d["agents"].append({"name": candidate, "role": role, "provider": provider, "model": model, **extra})


def apply(data: dict, template_id: str) -> dict:
    d = copy.deepcopy(data)
    for key in ("providers", "agents", "project", "limits", "routing", "sandbox", "pricing", "notify"):
        d.setdefault(key, [] if key == "agents" else {})
    if template_id == "claude-only":
        c = _claude(d)
        for a in d["agents"]:
            a["provider"] = c
            a["model"] = LEAD if a.get("role") == "lead" else BUILD
            a.pop("escalate_to", None)
        _add(d, "Atlas", "lead", c, LEAD)
        _add(d, "Forge", "builder", c, BUILD)
    elif template_id == "local-builder":
        c = _claude(d)
        local = next((n for n, p in d["providers"].items() if p.get("kind") == "ollama"), None)
        if not local:
            d["providers"]["local"] = {"kind": "ollama", "url": "http://localhost:11434"}
            local = "local"
        builder = _member(d, "builder")
        if builder is None:
            d["agents"].append({"name": "Forge", "role": "builder", "provider": local, "model": "qwen3.8:27b-mlx"})
            builder = d["agents"][-1]
        elif d["providers"].get(builder["provider"], {}).get("kind") != "ollama":
            builder["provider"], builder["model"] = local, "qwen3.8:27b-mlx"
        backup = next((a for a in d["agents"] if a.get("role") == "builder" and a is not builder), None)
        if backup is None:
            d["agents"].append({"name": "Anvil", "role": "builder", "provider": c, "model": BUILD})
            backup = d["agents"][-1]
        builder["escalate_to"] = backup["name"]
        d["routing"]["light_model"] = LIGHT
    elif template_id == "full-quality":
        c = _claude(d)
        _add(d, "Sentinel", "security", c, BUILD, owns=["*"])
        _add(d, "Probe", "qa", c, BUILD, owns=["tests/"])
        _add(d, "Quill", "docs", c, LIGHT)
    elif template_id == "budget":
        d["limits"]["per_run"] = min(d["limits"].get("per_run") or 2.0, 2.0)
        d["limits"]["per_day"] = min(d["limits"].get("per_day") or 10.0, 10.0)
        d["routing"]["light_model"] = LIGHT
        for a in d["agents"]:
            if a.get("role") in ("marketing", "devops", "docs") and d["providers"].get(a["provider"], {}).get("kind") == "anthropic":
                a["model"] = BUILD if a.get("role") == "devops" else LIGHT
    elif template_id == "safe-autopilot":
        d["project"]["release"] = "ask"
        gated = list(d["project"].get("require_approval") or [])
        for p in (".github/", "package.json", "pyproject.toml", "*.csproj", "Dockerfile", "requirements.txt"):
            if p not in gated:
                gated.append(p)
        d["project"]["require_approval"] = gated
        d["sandbox"]["mode"] = "container"
        d["limits"].setdefault("per_run", 5.0)
        d["limits"].setdefault("per_day", 25.0)
    else:
        raise ValueError(f"unknown template {template_id!r}")
    return d
