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
#   --no-rea             don't install REA (behaviour checks and Inspire use it)
#   --no-ui              don't open the dashboard at the end of a first install
#   --no-shortcut        don't add the Lakeba OS app/launcher (macOS: ~/Applications; Linux: the app menu)
#   --force              replace an `agent-team` command this script didn't create
#   --uninstall          remove the CLI, its environment, its source copy, its own Node.js and REA, and the plugin
#                        (your saved keys and project list are kept)
#   --purge              with --uninstall: also delete your saved keys and project list
#                        (~/.config/agent-team); asks first unless --yes
#   --yes                don't ask before --purge deletes them
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
REA=1
UI=1
SHORTCUT=1
FORCE=0
UNINSTALL=0
PURGE=0
YES=0
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/agent-team"
COMPLETIONS="${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions/agent-team"

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a value}"; shift 2 ;;
    --no-plugin) PLUGIN=0; shift ;;
    --no-rea) REA=0; shift ;;
    --no-ui) UI=0; shift ;;
    --no-shortcut) SHORTCUT=0; shift ;;
    --force) FORCE=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
    --yes|-y) YES=1; shift ;;
    -h|--help) sed -n '2,25p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31mx\033[0m %s\n' "$*" >&2; exit 1; }

ours() { [ -L "$BIN_DIR/agent-team" ] && [ "$(readlink "$BIN_DIR/agent-team")" = "$VENV/bin/agent-team" ]; }

[ "$PURGE" = 1 ] && [ "$UNINSTALL" = 0 ] && die "--purge goes with --uninstall."

# A yes/no question, read from the terminal even when this script arrives through a pipe.
confirm() {
  [ "$YES" = 1 ] && return 0
  local answer=""
  if { : > /dev/tty; } 2>/dev/null; then   # a terminal we can actually open, not just a device file
    printf '%s [y/N] ' "$1" > /dev/tty
    read -r answer < /dev/tty || answer=""
  else
    warn "no terminal to ask in; add --yes to confirm"
    return 1
  fi
  case "$answer" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

if [ "$UNINSTALL" = 1 ]; then
  if command -v claude >/dev/null 2>&1; then
    claude plugin uninstall agent-team@lakeba-agent-team >/dev/null 2>&1 && say "removed the Claude Code plugin" || true
    claude plugin marketplace remove lakeba-agent-team >/dev/null 2>&1 || true
  fi
  if ours; then rm "$BIN_DIR/agent-team"; say "removed $BIN_DIR/agent-team"; fi
  rm -rf "$VENV" "$SRC" "$HOME_DIR/node"
  REA_COPY="${XDG_DATA_HOME:-$HOME/.local/share}/agent-team/rea"
  if [ -d "$REA_COPY" ]; then rm -rf "$REA_COPY"; say "removed agent-team's REA copy"; fi
  rmdir "${XDG_DATA_HOME:-$HOME/.local/share}/agent-team" 2>/dev/null || true
  rmdir "$HOME_DIR" 2>/dev/null || true
  if [ -d "$HOME/Applications/Lakeba OS.app" ]; then rm -rf "$HOME/Applications/Lakeba OS.app"; say "removed the Lakeba OS app"; fi
  LAUNCHER="${XDG_DATA_HOME:-$HOME/.local/share}/applications/lakeba-os.desktop"
  if [ -f "$LAUNCHER" ]; then rm -f "$LAUNCHER"; say "removed the Lakeba OS menu entry"; fi
  if [ -f "$COMPLETIONS" ] && grep -q "agent-team" "$COMPLETIONS" 2>/dev/null; then rm -f "$COMPLETIONS"; say "removed the bash completion"; fi
  say "agent-team uninstalled (project .team.toml files and .team/ logs are left alone)"
  if command -v pipx >/dev/null 2>&1 && pipx list --short 2>/dev/null | grep -q '^agent-team '; then
    warn "agent-team is also installed with pipx; remove that copy with: pipx uninstall agent-team"
  elif command -v agent-team >/dev/null 2>&1; then
    warn "another agent-team is still on your PATH: $(command -v agent-team)"
  fi
  if [ -d "$CONFIG_DIR" ]; then
    if [ "$PURGE" = 1 ]; then
      if confirm "Delete $CONFIG_DIR (your saved API keys and the dashboard's project list)?"; then
        rm -rf "$CONFIG_DIR"; say "deleted $CONFIG_DIR"
      else
        say "kept $CONFIG_DIR"
      fi
    else
      say "kept your saved keys and project list in $CONFIG_DIR (delete them with --uninstall --purge)"
    fi
  fi
  exit 0
fi

# 1. git. On a Mac it comes with Apple's command-line developer tools: when they're missing, ask macOS
#    to install them and wait here until they're in, so a double-click goes straight on to the setup.
#    (Before looking for Python: on a Mac without them, even running python3 pops up the same window.)
if [ "${LAKEBA_OS_STARTER:-0}" = 1 ]; then AGAIN="double-click Lakeba OS again"; else AGAIN="run this installer again"; fi
if [ "$(uname)" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install >/dev/null 2>&1 || true
  say "agent-team needs Apple's developer tools (git is part of them), and macOS has opened a window to install them."
  say "In that window, click Install, then Agree. It usually takes 5 to 20 minutes; leave this window open."
  say "waiting for Apple's developer tools to finish installing..."
  POLL="${AGENT_TEAM_CLT_POLL:-5}"; WAIT="${AGENT_TEAM_CLT_WAIT:-5400}"   # seconds between checks; give up after 90 min
  waited=0; seen=0; gone=0; hinted=0; note=300
  while :; do
    if pgrep -f "Install Command Line Developer Tools" >/dev/null 2>&1; then
      seen=1; gone=0
    elif xcode-select -p >/dev/null 2>&1 && git --version >/dev/null 2>&1; then
      break
    elif [ "$seen" = 1 ]; then
      gone=$((gone + 1))   # the window closed without the tools: a few more checks, in case they're just landing
      [ "$gone" -ge 4 ] && die "Apple's developer tools weren't installed (the window was closed, or Cancel was clicked). When you're ready, $AGAIN and click Install in the window that opens."
    elif [ "$waited" -ge 90 ] && [ "$hinted" = 0 ]; then
      hinted=1   # keep waiting all the same: this only tells the person what to do if they see no window
      say "No window to install them? Close this one and $AGAIN to bring it back."
    fi
    [ "$waited" -ge "$WAIT" ] && die "Apple's developer tools are still not installed after $((WAIT / 60)) minutes. Let the install finish, then $AGAIN."
    sleep "$POLL"; waited=$((waited + (POLL > 0 ? POLL : 1)))   # tests check with no pause, still counting
    if [ "$waited" -ge "$note" ]; then say "still waiting for the developer tools ($((waited / 60)) min so far)..."; note=$((note + 300)); fi
  done
  say "Apple's developer tools are installed: carrying on"
fi
command -v git >/dev/null 2>&1 || die "git is required (Ubuntu/Debian: sudo apt install git)."
# 2. A Python new enough (3.11+). macOS's own python3 is often older, so look for newer ones first.
PY=""
for c in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
         /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
# No Python 3.11+? Use uv (https://docs.astral.sh/uv/) to get a private one, without touching the system's.
if [ -z "$PY" ] && [ "${AGENT_TEAM_NO_UV:-0}" != 1 ]; then
  UV="$(command -v uv || true)"
  [ -n "$UV" ] || [ ! -x "$HOME/.local/bin/uv" ] || UV="$HOME/.local/bin/uv"
  if [ -z "$UV" ]; then
    say "no Python 3.11+ here: getting uv to install a private Python for agent-team"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 || true
    [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
  fi
  if [ -n "$UV" ]; then
    "$UV" python install 3.12 >/dev/null 2>&1 || true
    PY="$("$UV" python find 3.12 2>/dev/null || true)"
  fi
fi
[ -n "$PY" ] || die "agent-team needs Python 3.11 or newer (macOS: brew install python@3.12; Ubuntu/Debian: sudo apt install python3 python3-venv)."
say "using $("$PY" --version) at $PY"

# 3. The source: clone once, then update. gh is used when signed in (it also reaches private forks).
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

# 4. Its own environment, so it never touches the system Python or your projects' packages.
say "installing into $VENV"
FIRST_INSTALL=0
[ -x "$VENV/bin/agent-team" ] || FIRST_INSTALL=1
if [ ! -x "$VENV/bin/python" ]; then
  "$PY" -m venv "$VENV" 2>/dev/null || {
    rm -rf "$VENV"
    die "Python can't create an environment. On Ubuntu/Debian: sudo apt install python3-venv (or python3.12-venv), then run this again."
  }
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade "$SRC[screenshots]"

# 5. The command on your PATH.
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
  *)
    # Ubuntu and Debian's ~/.profile add ~/.local/bin for new logins once it exists: a new terminal is enough.
    if [ "$BIN_DIR" = "$HOME/.local/bin" ] && grep -qs '\.local/bin' "$HOME/.profile"; then
      say "open a new terminal (or log in again) to use agent-team: $BIN_DIR goes on your PATH then"
    else
      warn "$BIN_DIR is not on your PATH. Add this to your shell profile: export PATH=\"$BIN_DIR:\$PATH\""
    fi ;;
esac
say "installed $("$VENV/bin/agent-team" --version)"
if "$VENV/bin/agent-team" completion install --shell bash >/dev/null 2>&1; then
  say "Tab completion for bash installed (new terminals)"
fi
case "${SHELL:-}" in
  *zsh) say "Tab completion for zsh: run  agent-team completion install  (it adds one line to ~/.zshrc)" ;;
esac

# 4b. REA, which behaviour checks and Inspire use: agent-team's own copy, at the version agent-team was
#     tried with (brought up to date each time this script runs). It needs Node.js 22.19+, 24.11+ or 26+.
#     Without one, agent-team gets its own Node.js 24 from nodejs.org into $HOME_DIR/node, checked against
#     nodejs.org's published SHA-256 checksums, the way it gets its own Python with uv: nothing system-wide,
#     no administrator password, no question.
node_ok() {
  "$1" -e 'const [a, b] = process.versions.node.split(".").map(Number); process.exit((a === 22 && b >= 19) || (a === 24 && b >= 11) || a >= 26 ? 0 : 1)' 2>/dev/null
}
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
private_node() {
  local os arch dist sums file want tmp
  case "$(uname -s)" in Darwin) os=darwin ;; Linux) os=linux ;; *) return 1 ;; esac
  case "$(uname -m)" in arm64|aarch64) arch=arm64 ;; x86_64|amd64) arch=x64 ;; *) return 1 ;; esac
  dist="https://nodejs.org/dist/latest-v24.x"
  sums="$(curl -fsSL "$dist/SHASUMS256.txt")" || return 1
  file="$(printf '%s\n' "$sums" | awk -v s="-$os-$arch.tar.gz" '$2 ~ s"$" && $2 ~ /^node-v24\./ {print $2; exit}')"
  want="$(printf '%s\n' "$sums" | awk -v f="$file" '$2 == f {print $1; exit}')"
  [ -n "$file" ] && [ -n "$want" ] || return 1
  tmp="$(mktemp -d)"
  if curl -fsSL "$dist/$file" -o "$tmp/$file" && [ "$(sha256 "$tmp/$file")" = "$want" ]; then
    rm -rf "$HOME_DIR/node" && mkdir -p "$HOME_DIR/node" && tar -xzf "$tmp/$file" -C "$HOME_DIR/node" --strip-components 1
  else
    warn "the Node.js download didn't match nodejs.org's checksum, so it wasn't used"
    rm -rf "$tmp"; return 1
  fi
  rm -rf "$tmp"
  node_ok "$HOME_DIR/node/bin/node"
}
if [ "$REA" = 1 ]; then
  NODE_BIN=""
  if command -v node >/dev/null 2>&1 && node_ok "$(command -v node)"; then
    NODE_BIN="$(dirname "$(command -v node)")"
  elif [ -x "$HOME_DIR/node/bin/node" ] && node_ok "$HOME_DIR/node/bin/node"; then
    NODE_BIN="$HOME_DIR/node/bin"
  else
    say "no Node.js 22.19+, 24.11+ or 26+ here: getting a private Node.js 24 for REA from nodejs.org (about 50 MB)"
    private_node && NODE_BIN="$HOME_DIR/node/bin"
  fi
  if [ -n "$NODE_BIN" ]; then
    say "installing REA for behaviour checks and Inspire (a minute or two)"
    if (cd "$HOME" && PATH="$NODE_BIN:$PATH" "$VENV/bin/agent-team" rea setup --yes >/dev/null 2>&1); then
      say "REA ready (agent-team keeps it up to date)"
    else
      warn "REA couldn't be installed now; later: agent-team rea setup"
    fi
  else
    warn "REA needs Node.js 22.19+, 24.11+ or 26+, and it couldn't be downloaded (https://nodejs.org); then run: agent-team rea setup"
  fi
fi

# 6. The Claude Code plugin, read from the local copy so updates arrive with the next run.
if [ "$PLUGIN" = 1 ] && command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add "$SRC" >/dev/null 2>&1 || true
  claude plugin marketplace update lakeba-agent-team >/dev/null 2>&1 || true
  if claude plugin install agent-team@lakeba-agent-team --scope user >/dev/null 2>&1; then
    # A new install, or one already loading in place from $SRC. An install from another source
    # (a cached copy, e.g. /plugin marketplace add lakeba/agent-team) moves with the version.
    claude plugin update agent-team@lakeba-agent-team --scope user -y >/dev/null 2>&1 || true
    say "Claude Code plugin ready: /team-init, /team-doctor, /team-plan, /team-build, /team-fix, /team-ship, /team-autopilot, /team-issues, /team-schedule, /team-market, /team-ui, /team-panel, /team-run"
    say "Open Claude Code sessions keep the old commands: run /reload-plugins in each, or start a new one."
  else
    warn "the Claude Code plugin could not be installed; in Claude Code run: /plugin marketplace add $SRC, then /plugin install agent-team@lakeba-agent-team"
  fi
elif [ "$PLUGIN" = 1 ]; then
  say "Claude Code not found; skipped the plugin."
fi

# 7. A way back in without a terminal: an app (macOS) or a menu entry (Linux) that opens the dashboard.
APP="$HOME/Applications/Lakeba OS.app"
DESKTOP_ENTRY="${XDG_DATA_HOME:-$HOME/.local/share}/applications/lakeba-os.desktop"
if [ "$SHORTCUT" = 1 ]; then
  if [ "$(uname)" = "Darwin" ] && command -v osacompile >/dev/null 2>&1; then
    mkdir -p "$HOME/Applications"
    rm -rf "$APP"
    if osacompile -o "$APP" -e "do shell script \"cd ~ && nohup '$VENV/bin/agent-team' ui --from-app >/dev/null 2>&1 &\"" >/dev/null 2>&1; then
      say "Lakeba OS is in your Applications folder: open it any time to get back to the dashboard"
    fi
  elif [ "$(uname)" = "Linux" ]; then
    mkdir -p "$(dirname "$DESKTOP_ENTRY")"
    cat > "$DESKTOP_ENTRY" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Lakeba OS
Comment=Open the agent-team dashboard
Exec=sh -c 'cd ~ && "$VENV/bin/agent-team" ui --from-app'
Terminal=false
Categories=Development;
DESKTOP
    say "Lakeba OS is in your applications menu: open it any time to get back to the dashboard"
  fi
fi

# 8. The first time: open the dashboard, where a short guided setup starts.
if [ "$UI" = 1 ] && [ "$FIRST_INSTALL" = 1 ] && { [ "$(uname)" = "Darwin" ] || [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; }; then
  (cd "$HOME" && nohup "$VENV/bin/agent-team" ui --from-app >/dev/null 2>&1 &)
  say "Opening Lakeba OS in your browser: a short guided setup takes you from your idea to a team at work."
fi

cat <<EOF

Next:
  Without a terminal: open Lakeba OS (or run  agent-team ui) for the guided setup in your browser.
  In a terminal:
  1. In a project:  agent-team ready  &&  agent-team init  (or /team-init in Claude Code)
     init asks where the models run (Claude, Ollama or both), which members and how many builders.
  2. Members on Claude need your Anthropic key, saved once:  agent-team keys set ANTHROPIC_API_KEY
  Press Tab twice after agent-team for its commands, options and your members' names.
  Update later by running this script again; remove with --uninstall (add --purge to delete saved keys).
EOF
