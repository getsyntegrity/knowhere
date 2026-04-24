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
