"""agent-team's own keys file, so API keys reach every command however it is started.

Shells differ in which profile files they read: Ubuntu's ~/.bashrc stops early for
non-interactive shells, launchd and cron read none. So agent-team also reads
`~/.config/agent-team/env` (or `$XDG_CONFIG_HOME/agent-team/env`), readable only by you:

    ANTHROPIC_API_KEY=...
    STUDIO_NODE_TOKEN=...

A variable already set in the environment wins over the file. `agent-team keys set NAME` asks
for the value without echoing it; no command ever prints a value.
"""
from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_loaded: dict[str, str] = {}      # names that came from the file (not from the environment)


def path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "agent-team" / "env"


def read() -> dict[str, str]:
    p = path()
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if NAME_RE.match(name):
            out[name] = value
    return out


def load_into_env() -> None:
    """Fill in variables the environment doesn't already have. Never overrides the environment."""
    try:
        values = read()
    except OSError:
        return
    for name, value in values.items():
        if value and not os.environ.get(name):
            os.environ[name] = value
            _loaded[name] = value


def where(name: str) -> str:
    """'keys file', 'environment' or '' (not set): where a variable's value comes from."""
    if not os.environ.get(name):
        return ""
    return "keys file" if _loaded.get(name) == os.environ.get(name) else "environment"


def loose_permissions() -> bool:
    p = path()
    return p.exists() and bool(p.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))


def _write(values: dict[str, str]) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(p.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".env.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# agent-team keys. Readable only by you; never commit or share this file.\n")
            for name, value in sorted(values.items()):
                f.write(f"{name}={value}\n")
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def set_key(name: str, value: str) -> None:
    if not NAME_RE.match(name):
        raise ValueError(f"{name!r} isn't a valid variable name")
    if not value or "\n" in value:
        raise ValueError("the value must be one non-empty line")
    values = read()
    values[name] = value.strip()
    _write(values)
    if _loaded.get(name) == os.environ.get(name) or not os.environ.get(name):
        os.environ[name] = value.strip()
        _loaded[name] = value.strip()


def remove(name: str) -> bool:
    values = read()
    if name not in values:
        return False
    del values[name]
    _write(values)
    if _loaded.pop(name, None) is not None:
        os.environ.pop(name, None)
    return True
