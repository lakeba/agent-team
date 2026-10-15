"""Terminal output: coloured speaker labels and dimmed reasoning, so people can watch the team."""
import contextlib
import io
import sys
import threading

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
COLORS = {
    "orange": "\033[38;5;208m", "cyan": "\033[36m", "pink": "\033[38;5;213m", "green": "\033[32m",
    "yellow": "\033[33m", "blue": "\033[34m", "magenta": "\033[35m", "red": "\033[31m",
}
_ROLE_COLORS = {"lead": "orange", "builder": "cyan", "marketing": "pink", "devops": "green",
                "factcheck": "blue", "reviewer": "yellow", "security": "red", "qa": "blue", "docs": "yellow"}


def color_for(role: str, explicit: str = "") -> str:
    return COLORS.get(explicit or _ROLE_COLORS.get(role, "magenta"), "")


def label(name: str, role: str, color: str = "") -> str:
    return f"{color_for(role, color)}{BOLD}{name} · {role}{RESET}"


_local = threading.local()
_print_lock = threading.Lock()


def say(text: str = "", end: str = "\n") -> None:
    buf = getattr(_local, "buffer", None)
    if buf is not None:
        buf.write(text + end)
        return
    with _print_lock:
        print(text, end=end, flush=True)


@contextlib.contextmanager
def buffered():
    """Collect this thread's output and print it in one piece at the end, so members working in
    parallel don't interleave their streamed replies."""
    _local.buffer = io.StringIO()
    try:
        yield
    finally:
        text, _local.buffer = _local.buffer.getvalue(), None
        with _print_lock:
            print(text, end="", flush=True)


def heading(text: str) -> None:
    say(f"\n{BOLD}{text}{RESET}")


def action(text: str) -> None:
    say(f"  \033[32m▸ {text}{RESET}")


def warn(text: str) -> None:
    print(f"  ! {text}", file=sys.stderr, flush=True)
