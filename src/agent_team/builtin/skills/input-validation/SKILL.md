---
name: input-validation
description: Validating and normalising data at the boundaries of a system
---
# Input validation

- Validate at every boundary: HTTP requests, CLI arguments, files, queues, environment, third-party responses.
- Use a schema (pydantic, zod, JSON Schema, FluentValidation) rather than scattered ifs.
- Check type, presence, length, range, format and allowed values; reject unknown fields where it matters.
- Normalise before validating (trim, unicode normalisation, case) and validate after.
- Return all validation errors at once with field names, not just the first.
- Inside the boundary, rely on the validated types instead of re-checking everywhere.
