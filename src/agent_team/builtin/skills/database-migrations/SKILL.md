---
name: database-migrations
description: Safe schema and data migrations: reversible, online, staged with code deploys
---
# Database migrations

- **One concern per migration**, named for what it does, checked into the repository.
- **Reversible**: write the down step, or document why there isn't one and how to recover.
- **Expand, migrate, contract** for changes that running code depends on:
  1. Expand: add the new column/table, nullable or with a default; code writes both old and new.
  2. Migrate: backfill in batches; switch reads to the new shape.
  3. Contract: remove the old column once no deployed code uses it.
- **Online-safe**: avoid long table locks. Create indexes concurrently where the database supports it;
  add constraints as not-validated first, validate later.
- **Backfills** run in batches with a checkpoint, can be resumed, and are throttled.
- **Data safety**: take a backup or snapshot before destructive steps; never drop data in the same
  release that stops using it.
- **Test** the migration on a copy of realistic data and time it.
