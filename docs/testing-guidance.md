# Testing Guidance

## Goal

Keep the main test suites focused on the project surface rather than internal implementation details.

The important things to verify are:

- HTTP contract: request shape, response shape, status codes, and headers
- Observable side effects: database writes, database updates, Redis state, and queued work
- Runtime guarantees: auth behavior, rate limiting, conflict handling, and validation handling
- Migration and persistence correctness: schema, constraints, and SQL-backed behavior

The important things to avoid are:

- Internal function boundary assertions
- Repository or service call-sequence assertions
- Mock-heavy tests that change the behavior under test in a material way

## Test Taxonomy

- `apps/api/tests/contract`
  API endpoint and surface specifications
- `apps/api/tests/support`
  app bootstrap, test environment, database reset, Redis reset, and seed helpers
- `apps/api/tests/migrations`
  Alembic and schema guarantees
- `apps/worker/tests/contract`
  worker entrypoint, queued-work boundary, and durable side-effect specifications
- `apps/api/tests` and `apps/worker/tests`
  narrow app-level component tests only when they protect pure logic or deterministic edge-case parsing

Do not add a standalone shared-package test tree for behavior that belongs to the API or worker surface.

## Contract Test Rules

- A contract test must call the project surface, not an internal helper.
- A contract test must assert an externally visible result or durable side effect.
- API contract tests should use the real FastAPI lifespan.
- Contract tests should use real PostgreSQL where SQL behavior depends on it.
- API and worker contract tests use `fakeredis` for Redis behavior while keeping the same Redis service interfaces.
- Mock only hard-to-control external boundaries such as third-party HTTP, storage providers, time, or filesystem edges.

## Naming Rules

- File names should follow the surface area being specified.
- Contract test functions should prefer `test_should_<observable_behavior>`.
- Test names should describe user-visible behavior, not implementation details.

## Fixture Boundaries

- `apps/api/tests/support` owns API bootstrap, environment setup, lifespan control, and seed data.
- API contract tests should not override core dependencies such as auth, database access, or rate limiting for the behavior under test.
- Worker contract tests own worker task entrypoints, queued-work boundaries, and durable task outcomes.

## Coverage Expectations

- API contract coverage should track every mounted router group in `apps/api/app/api/v1/api_v1.py`.
- Worker contract coverage should track every registered Celery task in `apps/worker/app/core/tasks`.
- When a stronger contract test replaces an old mock-heavy test, remove the weaker test or reduce it to a narrow component test.

## Local Environment

- API and worker contract tests require PostgreSQL server binaries and contrib extensions for `pytest-postgresql`.
- API and worker contract tests do not require a running local PostgreSQL or Redis service.
- API and worker contract tests use isolated `pytest-postgresql` processes and `fakeredis`.

## Commands

- `uv run python apps/api/scripts/ensure_test_environment.py --install`
- `uv run python apps/api/scripts/ensure_test_environment.py`
- `uv run pytest apps/api/tests/contract -q`
- `uv run pytest apps/api/tests/migrations -q`
- `uv run pytest apps/api/tests -q`
- `uv run pytest apps/worker/tests/contract -q`
- `uv run pytest apps/api/tests apps/worker/tests/contract -q`

## Failure Triage

- Re-run the smallest affected suite first.
- Re-run from a clean `pytest-postgresql` process when the failure depends on database side effects.
- Prefer fixing the harness or production behavior over adding more mocks.
