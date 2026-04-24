# API Migration Tests

Migration and schema guarantees live here.

This suite should prove:

- migrations apply cleanly from an empty database
- required constraints exist in runtime behavior
- important schema guarantees hold under real inserts and updates

Prefer runtime-backed checks over tests that only inspect migration file text.
