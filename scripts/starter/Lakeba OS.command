#!/bin/bash
# Lakeba OS for macOS: double-click to install agent-team (the first time) and open the dashboard,
# where a short guided setup takes you from your idea to an AI team at work.
# From https://github.com/lakeba/agent-team (MIT licence). Downloaded files need a right-click > Open
# the first time, because macOS checks files from the internet.
clear
echo "Lakeba OS"
echo
AT="$HOME/.agent-team/venv/bin/agent-team"
if [ -x "$AT" ]; then
  echo "Opening the dashboard in your browser..."
  cd "$HOME" && nohup "$AT" ui >/dev/null 2>&1 &
  sleep 3
else
  echo "Installing agent-team, the engine of Lakeba OS. This takes a few minutes the first time."
  echo
  curl -fsSL https://raw.githubusercontent.com/lakeba/agent-team/main/scripts/install.sh | bash
fi
echo
echo "You can close this window. Next time, open Lakeba OS from your Applications folder."
