"""Team composition: where the models run, which members the team has, and its spend limits.

One description of a team, used in two places: `agent-team init` writes a new .team.toml from it
(the questions in a terminal, or the flags), and the dashboard's Settings applies it to an existing
team as plain data, shown as a diff before anything is saved.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"
DEFAULT_OLLAMA = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.8:27b-mlx"

# Where the models run.
MODELS = {
    "mixed": "Claude leads, reviews, ships and markets; the builders run on Ollama",
    "ollama": "Only Ollama, on this machine or another: no Anthropic key, no per-token cost",
    "claude": "Only Claude: no local model needed",
}
# The optional members, in the order they're offered.
EXTRAS = {
    "security": ("Sentinel", "reviews every approved build and signs off every pull request"),
    "qa": ("Probe", "writes the tests for a plan before anyone builds it"),
    "docs": ("Quill", "updates README, docs/ and CHANGELOG.md after approval"),
}
CORE = {"lead": "Atlas", "marketing": "Spark", "devops": "Harbor"}
BUILDER_NAMES = ("Forge", "Anvil", "Kiln", "Smith")
MAX_BUILDERS = len(BUILDER_NAMES)
CLAUDE_MODEL = {"lead": OPUS, "builder": SONNET, "marketing": SONNET, "devops": SONNET,
                "security": SONNET, "qa": SONNET, "docs": HAIKU}


@dataclass
class Composition:
    models: str = "mixed"                  # a key of MODELS
    ollama_url: str = DEFAULT_OLLAMA       # the local model server (Ollama, or one speaking the OpenAI API)
    ollama_model: str = DEFAULT_MODEL
    local_kind: str = "ollama"             # ollama | openai (mlx_lm, LM Studio, llama.cpp ...)
    extras: tuple[str, ...] = ()           # keys of EXTRAS
    builders: int = 1
    per_run: float = 0.0                   # US dollars; 0 means no limit
    per_day: float = 0.0
    test_dir: str = "tests/"               # what a QA member may write to
    builder_model: str = ""                # a Claude builder's model, when not the default
    keep_limits: bool = False              # apply(): leave the team's [limits] as they are
    notes: list[str] = field(default_factory=list)

    def check(self) -> None:
        if self.models not in MODELS:
            raise ValueError(f"models is one of {', '.join(MODELS)}, not {self.models!r}")
        unknown = [e for e in self.extras if e not in EXTRAS]
        if unknown:
            raise ValueError(f"optional members are {', '.join(EXTRAS)}; unknown: {', '.join(unknown)}")
        if not 1 <= self.builders <= MAX_BUILDERS:
            raise ValueError(f"builders is 1 to {MAX_BUILDERS}, not {self.builders}")
        if self.local_kind not in ("ollama", "openai"):
            raise ValueError(f"the local server is ollama or openai (mlx_lm, LM Studio...), not {self.local_kind!r}")
        if self.per_run < 0 or self.per_day < 0:
            raise ValueError("spend limits are US dollars, 0 or more (0 means no limit)")

    def provider(self, role: str) -> str:
        """The connection a member with this role uses: "claude" or "local" (Ollama)."""
        if self.models == "claude":
            return "claude"
        if self.models == "ollama":
            return "local"
        return "local" if role == "builder" else "claude"

    def model(self, role: str) -> str:
        if self.provider(role) != "claude":
            return self.ollama_model
        return self.builder_model if role == "builder" and self.builder_model else CLAUDE_MODEL[role]

    @property
    def uses_claude(self) -> bool:
        return self.models != "ollama"

    @property
    def uses_ollama(self) -> bool:
        return self.models != "claude"

    def members(self) -> list[dict]:
        """Every member, as .team.toml data, in the order the file lists them."""
        out = [self._member(CORE["lead"], "lead", owns=["ROADMAP.md"])]
        out += [self._member(BUILDER_NAMES[i], "builder") for i in range(self.builders)]
        out.append(self._member(CORE["marketing"], "marketing", owns=["BRIEF.md", "site/", "deck/"]))
        devops = self._member(CORE["devops"], "devops")
        if self.provider("devops") == "claude":
            devops["effort"] = "medium"
        out.append(devops)
        for role in EXTRAS:
            if role in self.extras:
                out.append(self._extra(role))
        return out

    def _member(self, name: str, role: str, **extra) -> dict:
        return {"name": name, "role": role, "provider": self.provider(role), "model": self.model(role), **extra}

    def _extra(self, role: str) -> dict:
        owns = {"security": ["*"], "qa": [self.test_dir]}.get(role)
        return self._member(EXTRAS[role][0], role, **({"owns": owns} if owns else {}))

    def summary(self) -> str:
        names = [m["name"] for m in self.members()]
        limits = ("no spend limits" if not (self.per_run or self.per_day) else
                  "limits " + ", ".join(f"${v:g} per {k}" for k, v in (("run", self.per_run), ("day", self.per_day)) if v))
        local = "Ollama" if self.local_kind == "ollama" else "the local server"
        where = {"mixed": f"Claude + {local} builders", "ollama": f"all on {local} at {self.ollama_url}",
                 "claude": "all on Claude"}[self.models]
        return f"{len(names)} members ({', '.join(names)}), {where}, {limits}"


# ---------------------------------------------------------------------------------------------
# Writing a new .team.toml

_COMMENTS = {
    "security": "reviews every approved build; a NO sends it back",
    "qa": "writes the tests for a plan before anyone builds it",
    "docs": "updates README, docs/ and CHANGELOG.md after approval",
    "builder2": "more builders: build --parallel splits a plan between them",
}


def _toml(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    if isinstance(v, float):
        return f"{v:g}" if v != int(v) else f"{v:.1f}"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _agent_block(m: dict, comment: str = "", commented: bool = False) -> str:
    head = "[[agents]]" + (f"{' ' * 26}# {comment}" if comment else "")
    lines = [head] + [f"{k} = {_toml(v)}" for k, v in m.items()]
    if commented:
        lines = ["# " + line for line in lines]
    return "\n".join(lines) + "\n"


def providers_text(c: Composition) -> str:
    """The [providers] part of a new team file: the connections the members use, and commented
    examples of the others."""
    parts = ["# Providers: how to reach models. Add as many as you like, on this machine or others."]
    if c.uses_claude:
        parts.append('[providers.claude]\nkind = "anthropic"                    # uses ANTHROPIC_API_KEY (or set api_key_env)\n')
    else:
        parts.append("# [providers.claude]                 # add Claude later: uncomment, point members at it, and\n"
                     '# kind = "anthropic"                 # save the key with: agent-team keys set ANTHROPIC_API_KEY\n')
    if c.uses_ollama and c.local_kind == "openai":
        parts.append(f'[providers.local]                    # an OpenAI-compatible server here (mlx_lm, LM Studio...)\n'
                     f'kind = "openai"\nurl = "{c.ollama_url.rstrip("/")}"\n')
    elif c.uses_ollama:
        parts.append(f'[providers.local]\nkind = "ollama"\nurl = "{c.ollama_url.rstrip("/")}"\n')
    else:
        parts.append("# [providers.local]                  # Ollama, on this machine or another\n"
                     '# kind = "ollama"\n'
                     f'# url = "{DEFAULT_OLLAMA}"\n')
    parts.append('# [providers.gpu-box]                 # another machine running Ollama\n'
                 '# kind = "ollama"\n'
                 '# url = "http://gpu-box.local:11434"\n')
    parts.append('# [providers.remote-forge]            # a teammate running `agent-team serve` elsewhere\n'
                 '# kind = "agent-http"\n'
                 '# url = "http://10.0.0.20:8765"\n'
                 '# api_key_env = "FORGE_NODE_TOKEN"\n')
    return "\n".join(parts)


def agents_text(c: Composition) -> str:
    """The members, then the optional ones not chosen as commented examples."""
    parts = ["# Team members. Add, remove or rename freely; workflows find members by role."]
    builders_seen = 0
    for m in c.members():
        comment = ""
        if m["role"] == "builder":
            builders_seen += 1
            comment = _COMMENTS["builder2"] if builders_seen == 2 else ""
        elif m["role"] in EXTRAS:
            comment = _COMMENTS[m["role"]]
        parts.append(_agent_block(m, comment))
    parts.append("# Any member can take skills: Markdown files or skill folders (with SKILL.md) added to its prompt.\n"
                 '#   skills = ["team/skills/conventions.md", "~/.claude/skills/security-review"]\n')
    left = [r for r in EXTRAS if r not in c.extras]
    if left:
        parts.append("# Optional members. Uncomment any of them; `build` uses them automatically (skip with --skip).")
        for role in left:
            parts.append(_agent_block(c._extra(role), _COMMENTS[role], commented=True))
    return "\n".join(parts)


def limits_text(c: Composition) -> str:
    if c.per_run or c.per_day:
        lines = ["# Spend limits in US dollars; a run stops before the next model call once it reaches one.", "[limits]"]
        lines += [f"{k} = {_toml(float(v))}" for k, v in (("per_run", c.per_run), ("per_day", c.per_day)) if v]
        return "\n".join(lines) + "\n"
    return ("# Spend limits in US dollars; a run stops before the next model call once it reaches one.\n"
            "# [limits]\n# per_run = 5.0\n# per_day = 20.0\n")


# ---------------------------------------------------------------------------------------------
# Changing an existing team (the dashboard)

def apply(data: dict, c: Composition) -> dict:
    """The team in `data` (config_io.to_data shape) recomposed: connections, members for each role,
    the number of builders, the optional members and the limits. Members that stay keep their
    names, skills and other settings."""
    c.check()
    d = copy.deepcopy(data)
    for key in ("providers", "agents", "project", "limits", "routing"):
        d.setdefault(key, [] if key == "agents" else {})
    providers = d["providers"]

    claude = next((n for n, p in providers.items() if p.get("kind") == "anthropic"), None)
    if c.uses_claude and not claude:
        providers["claude"] = {"kind": "anthropic"}
        claude = "claude"
    local = next((n for n, p in providers.items() if p.get("kind") == c.local_kind
                  and (not p.get("url") or "localhost" in p["url"] or "127.0.0.1" in p["url"]
                       or p["url"].rstrip("/") == c.ollama_url.rstrip("/"))), None)
    if c.local_kind == "ollama":
        local = local or next((n for n, p in providers.items() if p.get("kind") == "ollama"), None)
    if c.uses_ollama:
        if not local:
            local = "local" if "local" not in providers else ("ollama" if c.local_kind == "ollama" else "mlx")
            providers[local] = {"kind": c.local_kind}
        providers[local]["url"] = c.ollama_url.rstrip("/")
    name_of = {"claude": claude, "local": local}

    def place(member: dict, role: str) -> None:
        member["provider"] = name_of[c.provider(role)]
        member["model"] = c.model(role)
        if c.provider(role) != "claude":
            member.pop("effort", None)

    agents: list[dict] = d["agents"]
    keep: list[dict] = []
    for role, name in (("lead", CORE["lead"]),):
        keep.append(_one(agents, role, name, c))
    builders = [a for a in agents if a.get("role") == "builder"][:c.builders]
    taken = {a.get("name") for a in agents}
    for name in BUILDER_NAMES:
        if len(builders) >= c.builders:
            break
        if name not in taken:
            builders.append({"name": name, "role": "builder"})
            taken.add(name)
    keep += builders
    for role in ("marketing", "devops"):
        keep.append(_one(agents, role, CORE[role], c))
    for role in EXTRAS:
        if role in c.extras:
            m = _one(agents, role, EXTRAS[role][0], c)
            if role == "security":
                m.setdefault("owns", ["*"])
            elif role == "qa":
                m.setdefault("owns", [c.test_dir])
            keep.append(m)
    # Members with other roles (fact-check, custom ones) stay as they are.
    keep += [a for a in agents if a.get("role") not in ("lead", "builder", "marketing", "devops", *EXTRAS)]
    for m in keep:
        if m.get("role") in CLAUDE_MODEL:
            place(m, m["role"])
    names = {m["name"] for m in keep}
    for m in keep:
        if m.get("escalate_to") and m["escalate_to"] not in names:
            m.pop("escalate_to")
    d["agents"] = keep

    used = {m["provider"] for m in keep}
    d["providers"] = {n: p for n, p in providers.items()
                      if n in used or p.get("kind") not in ("anthropic", "ollama")}
    if not c.uses_claude:
        d["routing"].pop("light_model", None)    # it only applies to Claude members
    if not c.keep_limits:
        d["limits"] = {k: v for k, v in d["limits"].items() if k not in ("per_run", "per_day")}
        if c.per_run:
            d["limits"]["per_run"] = float(c.per_run)
        if c.per_day:
            d["limits"]["per_day"] = float(c.per_day)
    return d


def _one(agents: list[dict], role: str, name: str, c: Composition) -> dict:
    """The team's member with this role, or a new one with this name."""
    found = next((a for a in agents if a.get("role") == role), None)
    if found is not None:
        return found
    taken = {a.get("name") for a in agents}
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name}{n}", n + 1
    return {"name": candidate, "role": role}


def from_data(data: dict) -> Composition:
    """The composition an existing team is closest to (what the dashboard's form starts from)."""
    providers = data.get("providers", {})
    agents = data.get("agents", [])
    kind = {a["name"]: providers.get(a.get("provider"), {}).get("kind") for a in agents}
    kinds = set(kind.values())
    models = "claude" if kinds <= {"anthropic"} else "ollama" if "anthropic" not in kinds else "mixed"
    ollama = next((p for n, p in providers.items() if p.get("kind") in ("ollama", "openai")
                   and any(a.get("provider") == n for a in agents)), None) \
        or next((p for p in providers.values() if p.get("kind") == "ollama"), {})
    local_kind = ollama.get("kind") or "ollama"
    on_ollama = [a.get("model") for a in agents if kind.get(a["name"]) == local_kind and a.get("model")]
    limits = data.get("limits", {})
    return Composition(
        models=models, ollama_url=ollama.get("url") or DEFAULT_OLLAMA, local_kind=local_kind,
        ollama_model=on_ollama[0] if on_ollama else DEFAULT_MODEL,
        extras=tuple(r for r in EXTRAS if any(a.get("role") == r for a in agents)),
        builders=max(1, min(MAX_BUILDERS, sum(a.get("role") == "builder" for a in agents))),
        per_run=float(limits.get("per_run") or 0), per_day=float(limits.get("per_day") or 0))


def from_form(form: dict) -> Composition:
    """A Composition from the dashboard's JSON (strings and lists as the browser sends them)."""
    def money(v) -> float:
        try:
            return max(0.0, float(v or 0))
        except (TypeError, ValueError):
            raise ValueError(f"spend limits are numbers of US dollars, not {v!r}")
    try:
        builders = int(form.get("builders") or 1)
    except (TypeError, ValueError):
        raise ValueError("builders is a number")
    c = Composition(models=str(form.get("models") or "mixed"),
                    ollama_url=str(form.get("ollama_url") or DEFAULT_OLLAMA).strip(),
                    ollama_model=str(form.get("ollama_model") or DEFAULT_MODEL).strip(),
                    local_kind=str(form.get("local_kind") or "ollama"),
                    extras=tuple(form.get("extras") or ()), builders=builders,
                    per_run=money(form.get("per_run")), per_day=money(form.get("per_day")),
                    keep_limits="per_run" not in form and "per_day" not in form)
    if c.uses_ollama and not c.ollama_url.startswith(("http://", "https://")):
        raise ValueError("the local server's address starts with http:// (e.g. http://192.168.1.20:11434)")
    from .config import address_problem
    if c.uses_ollama and address_problem(c.ollama_url):
        raise ValueError(address_problem(c.ollama_url))
    c.check()
    return c
