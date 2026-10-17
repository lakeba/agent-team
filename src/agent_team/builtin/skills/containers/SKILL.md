---
name: containers
description: Writing Dockerfiles and compose files that are small, reproducible and safe
---
# Containers

- Pin base images to a specific version (and ideally digest). Prefer slim or distroless images.
- Multi-stage builds: build tools in one stage, only the runtime artefacts in the final image.
- Order layers from least to most frequently changing; copy lock files and install dependencies before
  copying source, so caching works.
- Run as a non-root user; drop capabilities; read-only filesystem where possible.
- No secrets in images or build args; use runtime secrets or build secrets mounts.
- One process per container; health checks; log to stdout/stderr.
- `.dockerignore` to keep `.git`, local env files and build output out of the context.
