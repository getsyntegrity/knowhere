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
- Keep `fakeredis` only for narrow app-level component tests, not for main endpoint contract tests.
- Mock only hard-to-control boundaries such as time, filesystem edge cases, and outbound third-party HTTP.

## Current Findings

- The current API suite is mostly mock-driven.
- The main API test fixture overrides auth, billing, and database access.
- The real API lifespan runs migrations, warms the database pool, initializes Redis, and loads rate-limit rules.
- Config, database engine, and the FastAPI app are created at import time, which makes integration harness setup more fragile.
- The repository now has real API contract coverage for health, guest registration, authenticated file-mode and URL-mode job creation, authenticated `400`/`401`/`403`/`404`/`409` paths, all live jobs `429` layers, confirm-upload handoff, job list/detail reads, and API key revoke through HTTP only.
- The current API contract and migration suites are green with `uv run pytest apps/api/tests/contract -q`, `uv run pytest apps/api/tests/migrations -q`, and `uv run pytest apps/api/tests -q`.
- The combined API + worker contract command is now green and warning-clean with `uv run pytest apps/api/tests apps/worker/tests/contract -q -W error::pytest.PytestDeprecationWarning -W error::DeprecationWarning -W error::sqlalchemy.exc.SAWarning -W error::UserWarning`.
- The checked-in harness currently assumes PostgreSQL on `127.0.0.1:5432` and Redis on `127.0.0.1:6379`, isolated through `Knowhere_contract_test` and Redis DB `14`.
- Dedicated migration tests are now in place with `pytest-alembic`.
- The worker suite now has real contract slices for stale-job sweeping, URL-upload task handling, and parse-task execution against real Postgres and Redis, with outbound URL/S3 boundaries mocked only at the edge.
- No standalone shared-package test tree is planned; narrow deterministic checks should live under the owning app or worker test tree only when they protect project-level behavior.
- The remaining route-group API backlog is tracked in `docs/api-contract-backlog.md`.

## Working Rules

- Legacy mock-heavy suites may be removed once the project commits to the new taxonomy.
- Reintroduce still-important scenarios only in the new app- or worker-level suites; do not preserve them in the deleted legacy tree.
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
- App-level component tests, if retained later, should live under `apps/api/tests` or `apps/worker/tests`, never under `packages/shared-python`

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
- App-level component tests are reserved for pure logic, deterministic transformations, or adapter behavior that still protects a project-level surface without pretending to prove the full application contract.

Removal policy for old tests:

- `apps/api/__tests__` has been removed.
- New API behavior tests must live under `apps/api/tests`.
- If an old scenario still matters, it must be reintroduced in the new taxonomy as an API contract, worker contract, migration, or app-level component test.

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

Status: `[x]`

Actions:

- [x] Cover validation failures and `400` behavior
- [x] Cover auth failures and `401` behavior
- [x] Cover permission failures and `403` behavior
- [x] Cover conflict paths and `409` behavior
- [x] Cover not-found paths and `404` behavior
- [x] Cover rate limiting and `429` behavior across system, billing, concurrency, and daily-quota layers with real Redis-backed state
- [x] Cover file and URL job creation side effects
- [x] Cover upload confirmation handoff
- [x] Cover job retrieval and lifecycle response shape
- [x] Cover API key revoke behavior through HTTP only

Suggested rollout order:

- `POST /api/v1/jobs` conflict behavior for an active job on the same document
- `POST /api/v1/jobs` not-found behavior for update flows with an unknown or archived `document_id`
- `GET /api/v1/jobs` list response shape after a created job exists
- `GET /api/v1/jobs/{job_id}` normal flow, not-found, and ownership boundaries
- `429` coverage only after the authenticated jobs baseline is stable

Current Phase 4 snapshot:

- File-mode `POST /api/v1/jobs` now has happy-path contract coverage with persisted DB and Redis side effects.
- URL-mode `POST /api/v1/jobs` now has happy-path contract coverage for URL file-type resolution, persisted DB and Redis side effects, and worker handoff.
- `400 INVALID_ARGUMENT` for missing `file_name`
- `400 INVALID_ARGUMENT` for unsupported file type
- `401 UNAUTHENTICATED` for missing `Authorization`
- `401 UNAUTHENTICATED` for malformed `Authorization`
- `403 PERMISSION_DENIED` for cross-user job access
- `404 NOT_FOUND` for missing jobs and unknown or archived update-flow documents
- `409 ABORTED` for active-document ingestion conflicts
- `POST /api/v1/jobs/{job_id}/confirm-upload` now has contract coverage for file verification, transition to `pending`, and workflow handoff.
- `429 RESOURCE_EXHAUSTED` now covers the system limit, billing RPM, concurrent-job throttling, and daily-quota branches
- `GET /api/v1/jobs` list response shape after a created job exists
- `GET /api/v1/jobs/{job_id}` detail response shape, not-found behavior, and ownership boundaries
- `POST /api/v1/auth/revoke` verified through HTTP-only creation, revoke, list, and rejected reuse of the revoked key

Exit criteria:

- The covered API surfaces have contract coverage for normal flow and main failure modes.

### Phase 5: Migration and Persistence Guarantees

Status: `[x]`

Actions:

- [x] Add `pytest-alembic`
- [x] Verify migrations apply cleanly from an empty database
- [x] Verify schema constraints required by the contracts
- [x] Verify important uniqueness and conflict guarantees through real inserts
- [ ] Remove tests that only inspect migration file text when a stronger runtime test exists

Current note:

- `apps/api/tests/migrations` now runs `pytest-alembic` against a fresh throwaway local Postgres database per test.
- The suite now proves head upgrades, autogenerate drift checks, downgrade/upgrade consistency, and the active-document uniqueness guarantees through real inserts.
- Alembic autogenerate now ignores the generated TSV search columns and the `documents` to `job_results` cycle no longer emits drift-check warnings during `test_model_definitions_match_ddl`.

Exit criteria:

- Schema behavior is proven through migrations and runtime persistence checks.

### Phase 6: Worker Surface Tests

Status: `[~]`

Actions:

- [x] Define the worker surface that should be specified by tests
- [x] Cover task entrypoints and durable side effects
- [x] Use real storage/database/Redis where stability depends on them
- [x] Mock outbound provider calls only at external boundaries
- [ ] Keep parser algorithm micro-tests only where they protect deterministic pure logic

Current note:

- `apps/worker/tests/contract/test_stale_job_sweeper_contract.py` now covers the stale-job sweeper entrypoint with real Postgres and Redis side effects, including durable failure transitions and the Redis-backed duplicate-Beat lock.
- `apps/worker/tests/contract/test_url_upload_contract.py` now covers the URL-upload worker entrypoint against the real contract Redis and database bootstrap, asserting the storage target, Redis progress publication, and the stable `waiting-file` job state while mocking only outbound URL/S3 boundaries.
- `apps/worker/tests/contract/test_parse_task_contract.py` now covers parse-task success, terminal-skip behavior, and failure cleanup/refund behavior with real billing, finalization, and retrieval publication state.
- `apps/worker/tests/tasks/test_kb_tasks.py` has been removed; narrow deterministic parse-name coverage now lives in `apps/worker/tests/services/document_parser/test_internal_parse_name.py`.
- `apps/worker/tests` is still dominated by config and service-level tests outside those contract slices.

Exit criteria:

- Worker tests describe task behavior and durable outcomes rather than internal helper choreography.

### Phase 7: Test Suite Cleanup

Status: `[~]`

Actions:

- [ ] Review old tests one feature area at a time
- [ ] Delete tests replaced by stronger contract coverage
- [ ] Keep a small number of app-level component tests only where they protect pure domain logic or edge-case parsing
- [ ] Remove shared mock fixtures that no longer belong in the new architecture
- [ ] Simplify pytest configuration after migration

Current note:

- No standalone shared-package test tree is planned; remaining narrow deterministic checks should stay under `apps/api/tests` or `apps/worker/tests` when they still protect project-level behavior.
- `apps/worker/tests/tasks/test_kb_tasks.py` has been removed after its task-surface behavior moved into worker contracts and its filename-normalization checks moved into a narrow helper test.
- Repo-root pytest configuration now mirrors the async fixture loop settings used by the app-level suites so combined root-level runs do not emit `pytest-asyncio` deprecation noise.

Exit criteria:

- The suite is smaller, clearer, and dominated by surface-level specifications.

### Phase 8: CI and Developer Workflow

Status: `[x]`

Actions:

- [x] Define fast local commands for contract tests
- [x] Define CI commands and execution order
- [x] Split fast checks and slower contract checks if needed
- [x] Document how to run the new suite locally
- [x] Document how to seed or inspect failures

Current local commands:

- `uv run pytest apps/api/tests/contract -q`
- `uv run pytest apps/api/tests/migrations -q`
- `uv run pytest apps/api/tests -q`
- `uv run pytest apps/worker/tests/contract -q`
- `uv run pytest apps/api/tests apps/worker/tests/contract -q`

Local prerequisites:

- PostgreSQL reachable at `127.0.0.1:5432`
- Redis reachable at `127.0.0.1:6379`
- The default contract bootstrap will create or reuse `Knowhere_contract_test` and Redis DB `14`
- Contract tests should not be run in parallel today because they reuse the same contract database and Redis DB.

Recommended CI execution order:

- Fast API HTTP contracts: `uv run pytest apps/api/tests/contract -q`
- Migration guarantees: `uv run pytest apps/api/tests/migrations -q`
- Worker contract slice: `uv run pytest apps/worker/tests/contract -q`
- Full API tree when needed: `uv run pytest apps/api/tests -q`

Failure inspection notes:

- Re-run a single suite first; the shared contract database and Redis DB are intentionally stable and inspectable between failures.
- Check the persisted rows in `Knowhere_contract_test` and the Redis keys in DB `14` before re-running if the failure depends on side effects.

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
- [x] Add URL-mode and confirm-upload contracts for the jobs surface.
- [x] Add the first authenticated `400` and `401` contracts for `POST /api/v1/jobs`.
- [x] Expand authenticated API coverage to `404`, `409`, and all live jobs `429` cases.
- [x] Add read-side contracts for `GET /api/v1/jobs` and `GET /api/v1/jobs/{job_id}`.
- [x] Add migration verification with `pytest-alembic`.
- [x] Move worker tests toward task-surface contracts.
- [x] Update local developer docs and CI commands.

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
- URL-mode creation and confirm-upload cross Celery scheduling and Redis-backed handoff, so future jobs tests should keep those boundaries observable at the API surface instead of retreating to helper-level tests.

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

- Review and migrate the remaining worker mock-heavy tests into task-surface contracts or narrow app-level component tests, continuing with provider-specific parse/publication flows and the cleanup they unlock.
