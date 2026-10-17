---
name: api-design
description: Designing HTTP/REST APIs: resources, methods, status codes, errors, pagination, versioning
---
# API design

Resources and methods
- Nouns for resources (`/orders/{id}/items`), HTTP methods for actions: GET reads, POST creates or runs a
  command, PUT replaces, PATCH changes part, DELETE removes. GET never changes state.
- Use plural collection names and stable identifiers. Nest only for true ownership, at most two levels.

Status codes
- 200 OK, 201 Created (with Location), 202 Accepted for async work, 204 No Content.
- 400 invalid input, 401 not authenticated, 403 not allowed, 404 not found, 409 conflict,
  422 valid syntax but failed rules, 429 rate limited. 5xx only for server faults.

Errors
- One error shape everywhere, e.g. `{"error": {"code": "order_not_found", "message": "...", "details": {...}}}`.
- Machine-readable codes, human-readable messages, field-level details for validation errors.
  Never leak stack traces or internal names.

Collections
- Paginate everything that can grow: cursor-based for large or changing data, limit/offset for small.
  Return the next cursor; cap the page size.
- Filtering and sorting through query parameters with an allow-list of fields.

Change and safety
- Additive changes are safe; removing or renaming fields breaks clients. Version (`/v2` or a header)
  or deprecate with a date.
- Support idempotency keys on POSTs that create things, so retries are safe.
- Document rate limits, timeouts and authentication on every endpoint.
