---
name: auth-patterns
description: Authentication and authorisation done safely
---
# Authentication and authorisation

- Use an established provider or library (OIDC/OAuth 2.1, framework auth). Never invent token formats.
- Passwords: argon2id/bcrypt/scrypt, rate limits, breach checks, MFA support.
- Tokens: short-lived access tokens, refresh with rotation, validate signature, issuer, audience and expiry.
- Sessions: secure cookies (Secure, HttpOnly, SameSite), rotate on privilege change, server-side revocation.
- Authorisation: check per object and action on the server; centralise policy; deny by default; test the
  "other user's object" case for every endpoint.
- Log authentication events without credentials.
