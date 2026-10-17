---
name: style
description: Go
---
- `gofmt` and `go vet` clean. Small interfaces, defined where they are used.
- Return errors, wrap them with context (`fmt.Errorf("...: %w", err)`), and check every one.
- Pass `context.Context` first in functions that do I/O or may block.
- No goroutine without a way to stop it; protect shared state or share by communicating.
- Table-driven tests with `t.Run`; `-race` in CI.
