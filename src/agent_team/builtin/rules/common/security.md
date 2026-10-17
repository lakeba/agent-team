---
name: security
description: Security rules for every change
---
- Never put secrets (keys, tokens, passwords, connection strings) in code, tests, logs or examples.
  Read them from the environment or a secret store.
- Treat all input from outside the process as untrusted: validate type, length and range at the boundary.
- Build SQL, shell commands, HTML and file paths with the safe API (parameters, argument lists,
  escaping, path joining under a known root), never by string concatenation with input.
- Check authorisation on the server for every request, not only in the UI.
- Log enough to investigate, never personal data or secrets.
- Prefer well-known libraries for crypto, auth and parsing. Never write your own crypto.
- Pin dependencies and don't add ones that are unmaintained or have known vulnerabilities.
