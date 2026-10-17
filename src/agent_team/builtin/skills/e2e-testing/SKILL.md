---
name: e2e-testing
description: End-to-end tests for web apps: stable selectors, isolation, and avoiding flakiness
---
# End-to-end testing

- Test the critical user journeys (sign up, checkout, the main workflow), not every detail; unit and
  integration tests cover the rest.
- Select elements the way users find them: by role and accessible name, label or text. Use test ids
  only when there's no user-facing handle.
- Wait for conditions (element visible, request finished), never fixed sleeps.
- Each test creates its own data and cleans up, so tests run in any order and in parallel.
- Stub third-party services at the network layer; keep one smoke test against the real integration.
- Keep traces, screenshots and videos for failures in CI.
- A flaky test is a bug: find the race, don't add retries.
