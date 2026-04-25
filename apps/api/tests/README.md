# API Test Layout

This directory is the new home for API tests.

## Structure

- `contract/`: HTTP-surface specifications
- `support/`: fixtures, environment bootstrap, seeds, reset helpers
- `migrations/`: Alembic and schema behavior checks

## Rules

- New API behavior tests go here.
- This tree is the default-discovered API test suite.
- Contract tests must call the API through HTTP.
- Contract tests must assert response contract and observable side effects.
- Contract tests must not patch route handlers, repositories, or service internals for the behavior under test.

## Commands

- `uv run pytest apps/api/tests/contract -q`: fast API HTTP contract checks
- `uv run pytest apps/api/tests/migrations -q`: migration and schema guarantees
- `uv run pytest apps/api/tests -q`: full API test tree under the new taxonomy

## Local Prerequisites

- PostgreSQL reachable at `127.0.0.1:5432`
- Redis reachable at `127.0.0.1:6379`
- The shared contract bootstrap will create or reuse `Knowhere_contract_test`
- The shared contract bootstrap uses Redis DB `14`
- Do not run this suite in parallel with other contract suites that reuse the same database and Redis DB
