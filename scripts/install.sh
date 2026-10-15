#!/usr/bin/env bash
# Install or update agent-team (the CLI and, if Claude Code is installed, its plugin).
#
#   curl -fsSL https://raw.githubusercontent.com/lakeba/agent-team/main/scripts/install.sh | bash
#   ~/.agent-team/src/scripts/install.sh            # update an existing install
#   ... | bash -s -- --no-plugin --ref v0.1.0     # options
#
# Options:
#   --ref <branch|tag>   version to install (default: main)
#   --no-plugin          don't install the Claude Code plugin
#   --force              replace an `agent-team` command this script didn't create
#   --uninstall          remove the CLI, its environment, its source copy and the plugin
#
# Environment: AGENT_TEAM_HOME (default ~/.agent-team), BIN_DIR (default ~/.local/bin),
#              AGENT_TEAM_REPO (default lakeba/agent-team), AGENT_TEAM_SOURCE (a git URL or local
#              path to clone instead, e.g. a fork).
set -euo pipefail

REPO="${AGENT_TEAM_REPO:-lakeba/agent-team}"
SOURCE="${AGENT_TEAM_SOURCE:-}"
HOME_DIR="${AGENT_TEAM_HOME:-$HOME/.agent-team}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
SRC="$HOME_DIR/src"
VENV="$HOME_DIR/venv"
REF="main"
PLUGIN=1
FORCE=0
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a value}"; shift 2 ;;
    --no-plugin) PLUGIN=0; shift ;;
    --force) FORCE=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '2,19p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31mx\033[0m %s\n' "$*" >&2; exit 1; }

ours() { [ -L "$BIN_DIR/agent-team" ] && [ "$(readlink "$BIN_DIR/agent-team")" = "$VENV/bin/agent-team" ]; }

if [ "$UNINSTALL" = 1 ]; then
  if command -v claude >/dev/null 2>&1; then
    claude plugin uninstall agent-team@lakeba-agent-team >/dev/null 2>&1 && say "removed the Claude Code plugin" || true
    claude plugin marketplace remove lakeba-agent-team >/dev/null 2>&1 || true
  fi
  if ours; then rm "$BIN_DIR/agent-team"; say "removed $BIN_DIR/agent-team"; fi
  rm -rf "$VENV" "$SRC"
  rmdir "$HOME_DIR" 2>/dev/null || true
  say "agent-team uninstalled (project .team.toml files and .team/ logs are left alone)"
  exit 0
fi

# 1. A Python new enough (3.11+). macOS's own python3 is often older, so look for newer ones first.
PY=""
for c in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
         /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
[ -n "$PY" ] || die "agent-team needs Python 3.11 or newer (macOS: brew install python@3.12; Ubuntu/Debian: sudo apt install python3 python3-venv)."
say "using $("$PY" --version) at $PY"
command -v git >/dev/null 2>&1 || die "git is required."

# 2. The source: clone once, then update. gh is used when signed in (it also reaches private forks).
mkdir -p "$HOME_DIR"
if [ -d "$SRC/.git" ]; then
  say "updating $SRC to $REF"
  git -C "$SRC" fetch -q --tags origin
  git -C "$SRC" checkout -q "$REF"
  git -C "$SRC" symbolic-ref -q HEAD >/dev/null && git -C "$SRC" pull -q --ff-only origin "$REF"
else
  say "downloading ${SOURCE:-$REPO} ($REF) to $SRC"
  if [ -n "$SOURCE" ]; then
    git clone -q "$SOURCE" "$SRC"
  elif command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh repo clone "$REPO" "$SRC" -- -q
  else
    git clone -q "https://github.com/$REPO.git" "$SRC" \
      || die "could not clone $REPO. Check the network; for a private fork, sign in with 'gh auth login' first."
  fi
  git -C "$SRC" checkout -q "$REF"
fi

# 3. Its own environment, so it never touches the system Python or your projects' packages.
say "installing into $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  "$PY" -m venv "$VENV" 2>/dev/null || {
    rm -rf "$VENV"
    die "Python can't create an environment. On Ubuntu/Debian: sudo apt install python3-venv (or python3.12-venv), then run this again."
  }
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade "$SRC[screenshots]"

# 4. The command on your PATH.
mkdir -p "$BIN_DIR"
if [ -e "$BIN_DIR/agent-team" ] || [ -L "$BIN_DIR/agent-team" ]; then
  if ours; then :
  elif [ "$FORCE" = 1 ]; then rm -f "$BIN_DIR/agent-team"
  else
    warn "$BIN_DIR/agent-team already exists and wasn't created by this script (a development copy?)."
    warn "left it alone; rerun with --force to replace it. The installed CLI is $VENV/bin/agent-team."
  fi
fi
[ -e "$BIN_DIR/agent-team" ] || ln -s "$VENV/bin/agent-team" "$BIN_DIR/agent-team"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR is not on your PATH. Add this to your shell profile: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac
say "installed $("$VENV/bin/agent-team" --version)"

# 5. The Claude Code plugin, read from the local copy so updates arrive with the next run.
if [ "$PLUGIN" = 1 ] && command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add "$SRC" >/dev/null 2>&1 || true
  claude plugin marketplace update lakeba-agent-team >/dev/null 2>&1 || true
  if claude plugin install agent-team@lakeba-agent-team --scope user >/dev/null 2>&1; then
    # A new install, or one already loading in place from $SRC. An install from another source
    # (a cached copy, e.g. /plugin marketplace add lakeba/agent-team) moves with the version.
    claude plugin update agent-team@lakeba-agent-team --scope user -y >/dev/null 2>&1 || true
    say "Claude Code plugin ready: /team-init, /team-doctor, /team-plan, /team-build, /team-ship, /team-schedule, /team-market, /team-ui, /team-panel, /team-run"
    say "Open Claude Code sessions keep the old commands: run /reload-plugins in each, or start a new one."
  else
    warn "the Claude Code plugin could not be installed; in Claude Code run: /plugin marketplace add $SRC, then /plugin install agent-team@lakeba-agent-team"
  fi
elif [ "$PLUGIN" = 1 ]; then
  say "Claude Code not found; skipped the plugin."
fi

cat <<EOF

Next:
  1. Save your Anthropic key once:  agent-team keys set ANTHROPIC_API_KEY
  2. In a project:  agent-team ready  &&  agent-team init  (or /team-init in Claude Code)
  Update later by running this script again; remove with --uninstall.
EOF
