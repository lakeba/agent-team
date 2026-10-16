"""Tab completion for bash and zsh.

The shell runs `agent-team __complete WORD...` (the words typed after `agent-team`, the last one
being the word under the cursor, possibly empty) and shows what it prints: one candidate per line,
optionally followed by a tab and a short description. The candidates come from the CLI's own
parser, so new commands and options complete without changes here, plus a few things only the
project knows: member names, saved key names, the optional members and the models a team can use.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Options whose value is a member name (or a comma-separated list of them).
MEMBER_OPTIONS = {"--lead", "--builder", "--members"}
COMMA_LISTS = {"--members", "--skip", "--only"}   # behaviour --only takes journey names
KNOWN_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AGENT_TEAM_TOKEN", "AGENT_TEAM_WEBHOOK", "GITHUB_TOKEN")


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, tuple[argparse.ArgumentParser, str]]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {a.dest: a.help or "" for a in action._choices_actions}
            return {name: (sub, helps.get(name, "")) for name, sub in action.choices.items()
                    if not name.startswith("_")}
    return {}


def _options(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    return {opt: a for a in parser._actions for opt in a.option_strings}


def _positionals(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [a for a in parser._actions if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]


def _project(words: list[str]) -> Path:
    for i, w in enumerate(words[:-1]):
        if w in ("-C", "--project"):
            return Path(os.path.expanduser(words[i + 1]))
        if w.startswith("--project="):
            return Path(os.path.expanduser(w.split("=", 1)[1]))
    return Path.cwd()


def _members(words: list[str], role: str = "") -> list[tuple[str, str]]:
    try:
        from .config import find_config, load
        team = load(find_config(_project(words)))
        return [(a.name, f"{a.role}, {a.model}") for a in team.agents.values() if not role or a.role == role]
    except Exception:
        return []


def _value_candidates(cmd: str, option: str, action: argparse.Action, words: list[str]) -> list[tuple[str, str]]:
    if action.choices:
        return [(str(c), "") for c in action.choices if str(c)]
    if cmd == "init" and option == "--members":
        from .composition import EXTRAS
        return [(r, f"{name}: {about}") for r, (name, about) in EXTRAS.items()] + [("all", ""), ("none", "")]
    if cmd == "build" and option == "--skip":
        return [("qa", ""), ("security", ""), ("docs", ""), ("journeys", "")]
    if cmd == "behaviour" and option == "--only":
        try:
            from .config import find_config, load
            return [(s.name, s.kind) for s in load(find_config(_project(words))).behaviour.scenarios]
        except Exception:
            return []
    if cmd == "eval" and option == "--only":
        return [(x, "") for x in ("feature", "bug", "edit", "injection", "fake-release")]
    if cmd == "init" and option == "--builders":
        return [(str(n), "") for n in range(1, 5)]
    if option == "--ollama-url":
        from .readiness import ollama_candidates
        return [(u, "") for u in ollama_candidates()[:4]]
    if option in MEMBER_OPTIONS:
        return _members(words, "builder" if option == "--builder" else "")
    return []   # free text, numbers, paths: the shell falls back to file names


def candidates(parser: argparse.ArgumentParser, words: list[str]) -> list[tuple[str, str]]:
    """(candidate, description) for the last word, given every word typed after `agent-team`."""
    words = words or [""]
    current, before = words[-1], words[:-1]
    subs = _subcommands(parser)
    if not before:   # the command itself
        top = [(name, help_) for name, (_, help_) in subs.items()]
        if current.startswith("-"):
            top = [("--version", ""), ("--help", "")]
        return [(w, d) for w, d in top if w.startswith(current)]
    cmd = before[0]
    if cmd not in subs:
        return []
    sub = subs[cmd][0]
    options = _options(sub)

    # The value of an option: the word right after it, or after "--option=".
    if current.startswith("--") and "=" in current:
        opt, partial = current.split("=", 1)
        action = options.get(opt)
        if action is None or action.nargs == 0:
            return []
        return [(f"{opt}={w}", d) for w, d in _filter(cmd, opt, action, words, partial)]
    prev = before[-1] if len(before) > 1 else ""
    action = options.get(prev)
    if action is not None and action.nargs != 0 and not isinstance(action, (argparse._StoreTrueAction,
                                                                              argparse._StoreFalseAction,
                                                                              argparse._HelpAction)):
        return _filter(cmd, prev, action, words, current)

    used = set(before[1:])
    flags = [(opt, a.help or "") for opt, a in options.items()
             if opt.startswith("--") and opt not in used and not (set(a.option_strings) & used)]
    if current.startswith("-"):
        return [(w, _short(d)) for w, d in flags if w.startswith(current)]

    # A positional argument: which one is this word?
    index, skip = 0, False
    for w in before[1:]:
        if skip:
            skip = False
            continue
        if w.startswith("-"):
            a = options.get(w.split("=", 1)[0])
            skip = a is not None and "=" not in w and a.nargs != 0 and not isinstance(
                a, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._HelpAction))
            continue
        index += 1
    positionals = _positionals(sub)
    if index < len(positionals):
        pos = positionals[index]
        if pos.choices:
            return [(str(c), "") for c in pos.choices if str(c).startswith(current)]
        if cmd == "keys" and pos.dest == "name":
            return [(k, "") for k in _key_names() if k.startswith(current)]
        if cmd == "jobs" and pos.dest == "target" and "start" in before:
            return [(w, "") for w in ("build", "fix", "ship", "discuss", "market", "autopilot", "doctor")
                    if w.startswith(current)]
        if not current:   # nothing typed yet: say what goes here, and the options
            return [(f"<{pos.dest}>", _short(pos.help or "")), *[(w, _short(d)) for w, d in flags]] if pos.nargs != "?" \
                else [(w, _short(d)) for w, d in flags]
        return []
    return [(w, _short(d)) for w, d in flags if w.startswith(current)]


def _filter(cmd: str, option: str, action: argparse.Action, words: list[str], partial: str) -> list[tuple[str, str]]:
    values = _value_candidates(cmd, option, action, words)
    if option in COMMA_LISTS and "," in partial:   # complete the last item of a comma-separated list
        head, last = partial.rsplit(",", 1)
        chosen = set(head.split(","))
        return [(f"{head},{w}", d) for w, d in values if w.startswith(last) and w not in chosen]
    return [(w, d) for w, d in values if w.startswith(partial)]


def _key_names() -> list[str]:
    try:
        from . import keys
        saved = list(keys.read())
    except Exception:
        saved = []
    return list(dict.fromkeys([*saved, *KNOWN_KEYS]))


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 70 else text[:67] + "..."


def main(parser: argparse.ArgumentParser, words: list[str]) -> int:
    try:
        found = candidates(parser, words)
    except Exception:   # completion must never print a traceback into someone's shell
        return 0
    for word, about in found:
        sys.stdout.write(f"{word}\t{about}\n" if about else f"{word}\n")
    return 0


BASH = r'''# agent-team tab completion for bash. Installed by: agent-team completion install
_agent_team() {
  local -a words=("${COMP_WORDS[@]:1:COMP_CWORD}")
  local out
  out=$(agent-team __complete "${words[@]}" 2>/dev/null | cut -f1 | grep -v '^<') || true
  local IFS=$'\n'
  COMPREPLY=($out)   # none: -o default falls back to file names
}
complete -o default -F _agent_team agent-team
'''

ZSH = r'''# agent-team tab completion for zsh. Installed by: agent-team completion install
_agent_team() {
  local -a lines described plain
  local line word about
  lines=("${(@f)$(agent-team __complete "${(@)words[2,CURRENT]}" 2>/dev/null)}")
  for line in "${lines[@]}"; do
    [[ -z "$line" ]] && continue
    word="${line%%$'\t'*}"; about=""
    [[ "$line" == *$'\t'* ]] && about="${line#*$'\t'}"
    if [[ "$word" == "<"* ]]; then
      _message -r "${word} ${about}"
    elif [[ -n "$about" ]]; then
      described+=("${word//:/\\:}:${about}")
    else
      plain+=("$word")
    fi
  done
  (( ${#described} )) && _describe -t commands 'agent-team' described
  (( ${#plain} )) && compadd -- "${plain[@]}"
  (( ${#described} + ${#plain} )) || _files
}
(( $+functions[compdef] )) || { autoload -Uz compinit && compinit -i; }
compdef _agent_team agent-team
'''


def script(shell: str) -> str:
    return {"bash": BASH, "zsh": ZSH}[shell]


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def install(shell: str = "", yes: bool = False) -> int:
    """Install completion for this user. bash: a file bash-completion loads by itself. zsh: a
    script, plus one line in ~/.zshrc (asked first) that loads it."""
    from . import ui
    shell = shell or Path(os.environ.get("SHELL", "bash")).name
    if shell not in ("bash", "zsh"):
        ui.say(f"Completion is available for bash and zsh, not {shell}. Print a script with: agent-team completion bash")
        return 1
    if shell == "bash":
        path = _data_home() / "bash-completion" / "completions" / "agent-team"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(BASH, encoding="utf-8")
        ui.action(f"installed bash completion: {path}")
        ui.say("Open a new terminal, type agent-team and press Tab twice. (It needs the bash-completion "
               "package, which most Linux systems have; on macOS: brew install bash-completion@2.)")
        return 0
    path = _data_home() / "agent-team" / "completion.zsh"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ZSH, encoding="utf-8")
    ui.action(f"installed zsh completion: {path}")
    rc = Path(os.environ.get("ZDOTDIR") or Path.home()) / ".zshrc"
    line = f'[ -f "{path}" ] && source "{path}"   # agent-team tab completion'
    if rc.exists() and str(path) in rc.read_text(encoding="utf-8", errors="replace"):
        ui.say(f"{rc} already loads it. Open a new terminal, type agent-team and press Tab.")
        return 0
    if not yes:
        if not sys.stdin.isatty():
            ui.say(f"To turn it on, add this line to {rc}:\n  {line}")
            return 0
        answer = input(f"Add this line to {rc} so new terminals load it?\n  {line}\n[Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            ui.say(f"Left {rc} alone. To turn it on later, add that line yourself.")
            return 0
    with rc.open("a", encoding="utf-8") as f:
        f.write(f"\n{line}\n")
    ui.action(f"added it to {rc}")
    ui.say("Open a new terminal, type agent-team and press Tab.")
    return 0
