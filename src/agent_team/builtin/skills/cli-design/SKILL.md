---
name: cli-design
description: Designing command-line tools people enjoy using
---
# Command-line design

- Verbs for subcommands, clear flags with long names (and short ones for the common few).
- Helpful `--help` with examples; errors that say what's wrong and how to fix it.
- Safe defaults; destructive actions ask, or need `--yes`; support `--dry-run` where useful.
- Output for humans by default, `--json` for scripts; exit codes: 0 success, non-zero failures.
- Read from stdin and write to stdout so the tool composes; progress and logs go to stderr.
- Respect `NO_COLOR` and non-TTY output.
