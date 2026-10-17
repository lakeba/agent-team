"""Browser steps in plain words, for behaviour scenarios people and models write:

    goto /settings
    fill textbox "Project" with "client-a"
    click button "Start"
    press textbox "Project" Enter
    check checkbox "Remember me"            (uncheck works the same way)
    select combobox "Plan" option "Pro"
    wait for text "Running: client-a"       (or: wait for button "Stop")
    wait 500                                (milliseconds)

Elements are named the way people and screen readers see them: a role (button, link, textbox,
checkbox, combobox, heading, ...) and its accessible name. `css "#start"` and `testid "start"`
work too, where a page has no good names. Each line becomes one of REA's browser actions.

Electron apps take fewer steps, because REA's Electron capture clicks CSS selectors and waits:

    click css "#inc"                        (or: click testid "inc")
    wait 500
    reload                                  (reloads the window's page)
"""
from __future__ import annotations

import shlex

ROLES = ("button", "link", "textbox", "checkbox", "radio", "combobox", "listbox", "option", "menuitem", "tab",
         "heading", "img", "searchbox", "switch", "slider", "spinbutton", "dialog", "row", "cell", "listitem")
KEYS = ("Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
        "Home", "End", "PageUp", "PageDown", "Space")


class StepError(ValueError):
    pass


def _locator(words: list[str], line: str) -> tuple[dict, list[str]]:
    """The element a step names, and the words after it."""
    if len(words) < 2:
        raise StepError(f"{line!r}: name an element, e.g. button \"Start\"")
    kind, value, rest = words[0], words[1], words[2:]
    if kind == "css":
        return {"kind": "css", "selector": value}, rest
    if kind == "testid":
        return {"kind": "test_id", "value": value}, rest
    if kind == "text":
        return {"kind": "css", "selector": f"text={value}"}, rest
    if kind not in ROLES:
        raise StepError(f"{line!r}: {kind!r} isn't a role this understands ({', '.join(ROLES[:8])}, ...), "
                        f"css or testid")
    return {"kind": "role", "role": kind, "name": value}, rest


def parse_step(line: str, index: int) -> dict:
    try:
        words = shlex.split(line)
    except ValueError as e:
        raise StepError(f"{line!r}: {e}") from None
    if not words:
        raise StepError("an empty step")
    verb, args, sid = words[0].lower(), words[1:], f"step-{index + 1}"
    if verb == "goto" and len(args) == 1:
        return {"step_id": sid, "action": "goto", "destination": {"url": args[0]}, "wait_until": "load"}
    if verb == "wait" and len(args) == 1 and args[0].isdigit():
        return {"step_id": sid, "action": "wait_for_timeout", "duration_ms": int(args[0])}
    if verb == "wait" and args[:1] == ["for"]:
        locator, rest = _locator(args[1:], line)
        if rest:
            raise StepError(f"{line!r}: nothing goes after the element")
        return {"step_id": sid, "action": "wait_for", "locator": locator, "state": "visible"}
    if verb in ("click", "check", "uncheck"):
        locator, rest = _locator(args, line)
        if rest:
            raise StepError(f"{line!r}: nothing goes after the element")
        return {"step_id": sid, "action": verb, "locator": locator}
    if verb == "fill":
        locator, rest = _locator(args, line)
        if len(rest) != 2 or rest[0] != "with":
            raise StepError(f"{line!r}: write fill textbox \"Name\" with \"text\"")
        return {"step_id": sid, "action": "fill", "locator": locator, "value": {"source": "literal", "value": rest[1]}}
    if verb == "press":
        locator, rest = _locator(args, line)
        if len(rest) != 1 or rest[0] not in KEYS:
            raise StepError(f"{line!r}: press an element and one key ({', '.join(KEYS[:5])}, ...)")
        return {"step_id": sid, "action": "press", "locator": locator, "key": rest[0]}
    if verb == "select":
        locator, rest = _locator(args, line)
        if len(rest) != 2 or rest[0] != "option":
            raise StepError(f"{line!r}: write select combobox \"Name\" option \"Value\"")
        return {"step_id": sid, "action": "select_option", "locator": locator,
                "value": {"source": "literal", "value": rest[1]}}
    raise StepError(f"{line!r}: steps start with goto, click, fill, press, check, uncheck, select or wait")


def parse_steps(lines: list[str]) -> list[dict]:
    return [parse_step(line, i) for i, line in enumerate(lines)]


def parse_electron_step(line: str, index: int) -> dict:
    try:
        words = shlex.split(line)
    except ValueError as e:
        raise StepError(f"{line!r}: {e}") from None
    sid = f"step-{index + 1}"
    if len(words) == 2 and words[0].lower() == "wait" and words[1].isdigit():
        return {"step_id": sid, "kind": "wait", "duration_ms": int(words[1])}
    if words == ["reload"]:
        return {"step_id": sid, "kind": "renderer-reload"}
    if len(words) == 3 and words[0].lower() == "click" and words[1] in ("css", "testid"):
        selector = words[2] if words[1] == "css" else f'[data-testid="{words[2]}"]'
        return {"step_id": sid, "kind": "click", "selector": selector}
    raise StepError(f"{line!r}: Electron steps are click css \"#id\", click testid \"name\", wait 500 or reload "
                    f"(REA's Electron capture clicks CSS selectors)")


def parse_electron_steps(lines: list[str]) -> list[dict]:
    return [parse_electron_step(line, i) for i, line in enumerate(lines)]
