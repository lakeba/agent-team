---
name: caching
description: Adding caches that are correct: keys, invalidation, expiry and stampedes
---
# Caching

- Cache only what is expensive and read far more often than written; measure first.
- The key includes every input that changes the result (user, locale, version, parameters).
- Decide invalidation up front: time-based expiry, explicit invalidation on writes, or versioned keys.
- Bound the cache size; choose an eviction policy.
- Protect against stampedes: request coalescing, early refresh, or locks for expensive misses.
- Never cache per-user data in a shared cache without the user in the key. Never cache errors for long.
- Make the cache optional: the system must be correct (if slower) without it.
