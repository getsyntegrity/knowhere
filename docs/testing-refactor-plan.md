# Testing Refactor Plan

Last updated: 2026-04-25
Owner: Codex + repository maintainers
Status: In progress

## Goal

Rebuild the test system so the main suite specifies the project surface instead of the implementation details.

The new suite must verify:

- HTTP contract: request shape, response shape, status codes, headers
- Observable side effects: database writes, database updates, Redis state, queued work
- Runtime guarantees: auth behavior, rate limiting, conflict handling, validation handling
- Migration and persistence correctness: schema, constraints, SQL-backed behavior

The new suite must avoid coupling tests to:

- Internal function boundaries
- Service method calls
- Repository method calls
- Temporary implementation structure

## Decision Summary

- Keep `pytest` as the main test runner.
- Keep `pytest-asyncio` for async support.
- Use `httpx.AsyncClient` + `ASGITransport` for API contract tests.
- Drive startup and shutdown through the FastAPI lifespan context.
- Use real PostgreSQL and real Redis for contract tests.
- Use a dedicated contract-only database and Redis DB on the local services the repo already expects.
- Defer `testcontainers-python` unless local setup or CI isolation becomes a recurring blocker.
- Add `pytest-alembic` for migration checks.
- Keep `fakeredis` only for small component tests, not for main endpoint contract tests.
- Mock only hard-to-control boundaries such as time, filesystem edge cases, and outbound third-party HTTP.

## Current Findings

- The current API suite is mostly mock-driven.
- The main API test fixture overrides auth, billing, and database access.
- The real API lifespan runs migrations, warms the database pool, initializes Redis, and loads rate-limit rules.
- Config, database engine, and the FastAPI app are created at import time, which makes integration harness setup more fragile.
- The repository now has real API contract coverage for health, guest registration, authenticated file-mode job creation, and the first authenticated `400`/`401` job failure paths, but the authenticated API surface is still mostly uncovered.
- The current API contract suite is green with `uv run pytest apps/api/tests/contract -q` and `uv run pytest apps/api/tests -q`.
- The checked-in harness currently assumes PostgreSQL on `127.0.0.1:5432` and Redis on `127.0.0.1:6379`, isolated through `Knowhere_contract_test` and Redis DB `14`.
- Dedicated migration tests, worker contract tests, and shared component-test migration have not started yet.

## Working Rules

- Do not delete all existing tests first.
- Replace coverage feature by feature, then remove obsolete tests.
- A contract test must call the project surface, not internal functions.
- A contract test must assert an externally visible result or side effect.
- If a test only proves that an internal method was called, it should not live in the main contract suite.
- If a mock changes the behavior under test in a material way, the test is not a contract test.

## Phases

### Phase 0: Discovery and Principles

Status: `[x]`

Actions:

- [x] Audit the current test layout in `apps/api`, `apps/worker`, and `packages/shared-python`
- [x] Audit app startup and runtime boundaries
- [x] Identify which dependencies must stay real in contract tests
- [x] Choose the preferred framework stack
- [x] Write down the testing principles for the repo

Exit criteria:

- We have a stable testing direction and a clear framework choice.

### Phase 1: Contract Test Architecture

Status: `[x]`

Actions:

- [x] Define the new test taxonomy
- [x] Define directory layout for contract tests, support helpers, and retained component tests
- [x] Decide naming rules for contract tests
- [x] Define what belongs in API contract tests, worker contract tests, migration tests, and small component tests
- [x] Define a deprecation policy for old mock-heavy tests

Final taxonomy:

- `apps/api/tests/contract`: endpoint and API-surface specifications
- `apps/api/tests/support`: fixtures, seeds, builders, env bootstrapping
- `apps/api/tests/migrations`: Alembic and schema checks
- `apps/worker/tests/contract`: worker entrypoint and task-surface specifications
- `packages/shared-python/shared/tests/component`: narrow tests that still provide value without pretending to be full contracts

Naming rules:

- Contract test names must read like requirements statements.
- Contract tests should prefer `test_should_<observable_behavior>` at the function level.
- File names should follow surface areas, for example `test_guest_registration.py` or `test_job_creation.py`.
- A contract test name must mention the user-visible behavior, not an internal helper or implementation detail.

Fixture boundaries:

- `apps/api/tests/support` owns app bootstrap, test environment, lifespan control, database reset, Redis reset, and seed data.
- `apps/api/tests/contract` may use support fixtures but may not override core dependencies such as database access, auth flow, or rate limiting for the behavior under test.
- `apps/api/tests/migrations` owns migration lifecycle checks and schema guarantees.
- `apps/worker/tests/contract` owns worker entrypoints, queued-work boundaries, and durable side effects.
- `packages/shared-python/shared/tests/component` is reserved for pure logic, deterministic transformations, or adapter behavior that does not claim to prove the full application contract.

Removal policy for old tests:

- `apps/api/__tests__` has been removed.
- New API behavior tests must live under `apps/api/tests`.
- If an old scenario still matters, it must be reintroduced in the new taxonomy as a contract, migration, or component test.

Exit criteria:

- The repository has one clear testing map and each suite has a defined purpose.

### Phase 2: Test Harness Bootstrap

Status: `[x]`

Actions:

- [x] Finalize the base harness dependency set
- [x] Create isolated Postgres and Redis test infrastructure
- [x] Create deterministic test environment loading
- [x] Ensure migrations run against the isolated test database before contract tests
- [x] Build reusable fixtures for database reset and Redis reset
- [x] Build a reusable app client harness
- [x] Ensure FastAPI lifespan is executed in tests
- [x] Ensure the harness can seed required rate-limit and auth data

Important implementation note:

- Because config, engine, and app are created at import time today, this phase may require a small bootstrap refactor so tests can set environment and initialize services before those globals are created.

Current Phase 2 snapshot:

- The new API test directories are scaffolded.
- A deterministic API test bootstrap path now exists.
- The first HTTP contract test is green: API health boots through the real lifespan and responds over HTTP.
- The API harness now uses a dedicated contract database and dedicated Redis DB.
- Contract storage prep now creates the isolated database, bootstraps the external `user` table, runs Alembic migrations, and resets mutable state.
- Reset helpers now preserve static rate-limit configuration while clearing mutable application state.
- The harness can now seed a deterministic authenticated local-developer profile for later endpoint contracts.
- API `pytest` discovery now points at `apps/api/tests` by default.
- During this work we found and fixed a real shutdown bug in `safe_dispose_engine()` where async engine disposal was not awaited.
- Current green command: `uv run pytest apps/api/tests/contract -q`
- Current green command: `uv run pytest apps/api/tests -q`
- The current harness uses dedicated local infrastructure, not containers.
- PostgreSQL contract database: `Knowhere_contract_test`
- Redis contract database index: `14`
- Shared authenticated API test support now exists for the seeded local developer profile.

Exit criteria:

- A single contract test can run against a real app, real Postgres, and real Redis without dependency overrides for core behavior.

### Phase 3: First Vertical Slice

Status: `[x]`

Actions:

- [x] Implement the first full contract test path for guest registration
- [x] Assert response contract
- [x] Assert persisted user, device, API key, and tier state
- [x] Assert duplicate device conflict behavior
- [x] Remove the obsolete legacy API suite and move default discovery to the new test tree

Suggested first targets:

- `POST /api/v1/guest`
- `POST /api/v1/jobs`

Exit criteria:

- At least one feature is fully covered by new contract tests and no longer depends on the old unit-style surface simulation.

### Phase 4: API Contract Coverage Expansion

Status: `[~]`

Actions:

- [x] Cover validation failures and `400` behavior
- [x] Cover auth failures and `401` behavior
- [ ] Cover permission failures and `403` behavior
- [ ] Cover conflict paths and `409` behavior
- [ ] Cover not-found paths and `404` behavior
- [ ] Cover rate limiting and `429` behavior with real Redis-backed state
- [x] Cover job creation side effects
- [ ] Cover job retrieval and lifecycle response shape
- [ ] Cover API key revoke behavior through HTTP only

Suggested rollout order:

- `POST /api/v1/jobs` conflict behavior for an active job on the same document
- `POST /api/v1/jobs` not-found behavior for update flows with an unknown or archived `document_id`
- `GET /api/v1/jobs` list response shape after a created job exists
- `GET /api/v1/jobs/{job_id}` normal flow, not-found, and ownership boundaries
- `429` coverage only after the authenticated jobs baseline is stable

Current Phase 4 snapshot:

- File-mode `POST /api/v1/jobs` now has happy-path contract coverage with persisted DB and Redis side effects.
- `400 INVALID_ARGUMENT` for missing `file_name`
- `400 INVALID_ARGUMENT` for unsupported file type
- `401 UNAUTHENTICATED` for missing `Authorization`
- `401 UNAUTHENTICATED` for malformed `Authorization`

Exit criteria:

- The core API surface has contract coverage for normal flow and main failure modes.

### Phase 5: Migration and Persistence Guarantees

Status: `[ ]`

Actions:

- [ ] Add `pytest-alembic`
- [ ] Verify migrations apply cleanly from an empty database
- [ ] Verify schema constraints required by the contracts
- [ ] Verify important uniqueness and conflict guarantees through real inserts
- [ ] Remove tests that only inspect migration file text when a stronger runtime test exists

Current note:

- Alembic already runs during contract bootstrap, but there is still no dedicated migration suite or explicit schema-assertion coverage.

Exit criteria:

- Schema behavior is proven through migrations and runtime persistence checks.

### Phase 6: Worker Surface Tests

Status: `[ ]`

Actions:

- [ ] Define the worker surface that should be specified by tests
- [ ] Cover task entrypoints and durable side effects
- [ ] Use real storage/database/Redis where stability depends on them
- [ ] Mock outbound provider calls only at external boundaries
- [ ] Keep parser algorithm micro-tests only where they protect deterministic pure logic

Current note:

- `apps/worker/tests` is still dominated by config, service, and task-level tests rather than queue-surface contracts.

Exit criteria:

- Worker tests describe task behavior and durable outcomes rather than internal helper choreography.

### Phase 7: Test Suite Cleanup

Status: `[ ]`

Actions:

- [ ] Review old tests one feature area at a time
- [ ] Delete tests replaced by stronger contract coverage
- [ ] Keep a small number of component tests only where they protect pure domain logic or edge-case parsing
- [ ] Remove shared mock fixtures that no longer belong in the new architecture
- [ ] Simplify pytest configuration after migration

Current note:

- `packages/shared-python/shared/tests/component` is defined, but the broader shared-test migration into that taxonomy is still pending.

Exit criteria:

- The suite is smaller, clearer, and dominated by surface-level specifications.

### Phase 8: CI and Developer Workflow

Status: `[~]`

Actions:

- [x] Define fast local commands for contract tests
- [ ] Define CI commands and execution order
- [ ] Split fast checks and slower contract checks if needed
- [x] Document how to run the new suite locally
- [ ] Document how to seed or inspect failures

Current local commands:

- `uv run pytest apps/api/tests/contract -q`
- `uv run pytest apps/api/tests -q`

Local prerequisites:

- PostgreSQL reachable at `127.0.0.1:5432`
- Redis reachable at `127.0.0.1:6379`
- The default contract bootstrap will create or reuse `Knowhere_contract_test` and Redis DB `14`
- Contract tests should not be run in parallel today because they reuse the same contract database and Redis DB.

Exit criteria:

- Developers can run the right level of tests locally and CI enforces the contract suite reliably.

## Concrete Action List

This is the exact working order to resume from:

- [x] Finalize the new test taxonomy and directory structure.
- [x] Stabilize the base contract test infrastructure on dedicated local Postgres and Redis.
- [x] Refactor bootstrap points only as much as needed to make test environment initialization deterministic.
- [x] Add database and Redis reset fixtures.
- [x] Add app client fixture with lifespan support.
- [x] Seed minimum required data for auth and rate limiting.
- [x] Write the first contract suite for `POST /api/v1/guest`.
- [x] Add an authenticated request helper that uses the seeded local-developer profile.
- [x] Write the first contract suite for `POST /api/v1/jobs` in file-upload mode.
- [x] Add the first authenticated `400` and `401` contracts for `POST /api/v1/jobs`.
- [ ] Expand authenticated API coverage to `404`, `409`, and `429` cases.
- [ ] Add read-side contracts for `GET /api/v1/jobs` and `GET /api/v1/jobs/{job_id}`.
- [ ] Add migration verification with `pytest-alembic`.
- [ ] Move worker tests toward task-surface contracts.
- [ ] Update local developer docs and CI commands.

## Resume Protocol

When resuming work, start from this checklist:

1. Open this file.
2. Find the first unchecked action in the current phase or concrete action list.
3. Confirm whether any bootstrap refactor is still blocking the harness.
4. Execute only the next smallest complete step.
5. Update the status markers in this file before stopping.

## Stop Points

Safe pause points:

- After test taxonomy is written
- After harness bootstraps a real app successfully
- After each endpoint contract suite lands
- After each feature area cleanup pass
- After CI wiring is updated

Before stopping, always record:

- What changed
- What remains blocked
- What the exact next action is

## Risks and Constraints

- Import-time app and engine creation may force a small architecture change before the new harness is clean.
- Full contract tests will be slower than the current mock-heavy suite.
- The current harness still depends on locally available PostgreSQL and Redis, so local ergonomics and CI isolation are not solved yet.
- Deleting old tests too early would remove behavior inventory before replacement coverage exists.
- Rate-limit tests must use real Redis-backed behavior or they will give false confidence.
- Database conflict tests should prefer real transaction behavior over patched exceptions.
- The first authenticated jobs contract should start with file mode, because URL mode immediately crosses into Celery scheduling and a wider external surface.

## Definition of Done

The refactor is done when:

- The main suite verifies the public project surface instead of internal call structure.
- Core API behaviors are covered by real contract tests.
- Real Postgres and real Redis back the important contract scenarios.
- Migration behavior is verified automatically.
- Old mock-heavy tests are removed or reduced to a small component layer.
- The test layout is documented and easy to continue from later.

## Next Action

Current next action:

- Add the next `POST /api/v1/jobs` state-path contracts for `409` active-document conflicts and `404` update flows against unknown or archived `document_id` values.
