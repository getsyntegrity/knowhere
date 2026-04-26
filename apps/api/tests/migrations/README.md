# API Migration Tests

Migration and schema guarantees live here.

This suite should prove:

- migrations apply cleanly from an empty database
- required constraints exist in runtime behavior
- important schema guarantees hold under real inserts and updates

Prefer runtime-backed checks over tests that only inspect migration file text.

## Command

- `uv run pytest apps/api/tests/migrations -q`

## Notes

- The migration suite uses `pytest-alembic` against a fresh throwaway database inside the `pytest-postgresql` process.
- The suite bootstraps only the external `user` table that application tables reference via foreign keys.
