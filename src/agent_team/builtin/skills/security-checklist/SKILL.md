---
name: security-checklist
description: A practical security checklist for web apps and services (OWASP Top 10 based)
---
# Security checklist

Access control
- Every request checks the caller may do this to this object (not only that they are logged in).
- Deny by default; no IDs in URLs that grant access by themselves.

Injection
- Parameterised queries; argument lists for processes (no shell strings); context-aware output escaping;
  safe template APIs; no `eval` of input.

Authentication and sessions
- Use a proven library or provider. Hash passwords with bcrypt/scrypt/argon2. Rate-limit logins.
- Session cookies: Secure, HttpOnly, SameSite. Rotate session ids on login. CSRF protection for cookie auth.

Data
- TLS everywhere. Encrypt sensitive data at rest. Minimise what you collect and log.

Configuration
- Secrets from environment or a vault. Debug off in production. Security headers (CSP, HSTS,
  X-Content-Type-Options). CORS allow-list, not `*` with credentials.

Dependencies and supply chain
- Lock files, pinned versions, automated vulnerability alerts, review new packages.

Files and uploads
- Validate type and size; store outside the web root with generated names; never trust client paths.
