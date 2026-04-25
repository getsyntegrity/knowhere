# Worker Contract Tests

Put worker surface specifications here.

These tests should verify:

- task entrypoint behavior
- durable side effects
- queue-facing or task-facing contracts

These tests should avoid:

- asserting helper call sequences
- patching internal services that define the behavior under test
- turning task tests into unit tests disguised as contracts

## Current Surface

- `app.core.tasks.stale_job_sweeper.expire_stale_jobs`
  verifies stale-job expiration, durable failure state, audit logging, and the Redis-backed duplicate-Beat lock

## Command

- `uv run pytest apps/worker/tests/contract -q`

## Local Prerequisites

- PostgreSQL reachable at `127.0.0.1:5432`
- Redis reachable at `127.0.0.1:6379`
- The current worker contract slice reuses the API contract database bootstrap and Redis DB `14`
- Do not run this suite in parallel with the API contract or migration suites
