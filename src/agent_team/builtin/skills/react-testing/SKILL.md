---
name: react-testing
description: Testing React components the way users use them (Testing Library)
---
# React testing

- Render with the providers the component needs; query by role and accessible name
  (`getByRole('button', { name: /save/i })`), then label, then text.
- Interact with `user-event`, not `fireEvent`, so focus and keyboard behave realistically.
- Await what appears asynchronously with `findBy*` or `waitFor`; no arbitrary timeouts.
- Mock network at the boundary (MSW); test loading, success, empty and error states.
- Don't test implementation details (state values, hook calls); test what the user sees.
