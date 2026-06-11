# Tasks: KNOW-002 Canonical Knowledge Model

**Input**: Design documents from `specs/002-know-002-canonical/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Approach**: Test-first — write and see each test fail before implementing.

> **Non-normative**: This document describes the Python reference implementation. The canonical contract itself is defined in `spec.md` and `data-model.md` and is implementation-agnostic.

**Format**: `- [ ] [TaskID] [P?] [Story?] Description (effort: S/M/L) — [file path]`
- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to user story (US1, US2, US3, US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and package structure

- [x] T001 [P] Create package structure in `packages/canonical-knowledge/` — pyproject.toml, src/canonical/, tests/ directories per plan.md (effort: S)
- [x] T002 [P] Configure pytest and test fixtures in `tests/conftest.py` — shared fixtures for entity creation (effort: S)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### CodeLocation Value Object

- [x] T003 [P] **TEST**: CodeLocation in `tests/test_code_location.py` — validate required fields, `start_line ≤ end_line` invariant, column consistency, immutability, equality, string serialization (effort: S)
- [x] T004 [P] Implement CodeLocation in `src/canonical/value_objects/code_location.py` as Pydantic frozen model with field validators (effort: S)

### Entity Definitions (All 6)

- [x] T005 [P] **TEST**: Repository entity in `tests/test_entities.py` — `source_uri` and `name` required; `id`, `source_uri`, `source` immutable; metadata defaults; serialization roundtrip (effort: S)
- [x] T006 [P] **TEST**: File entity in `tests/test_entities.py` — `path` + `repository_id` identity; `checksum` and `size_bytes` required; language optional; symbol/chunk/reference collection defaults (effort: S)
- [x] T007 [P] **TEST**: Symbol entity in `tests/test_entities.py` — `qualified_name` unique per repository; CodeLocation bounds; optional `signature`, `documentation`, `children`, `scope`; no circular children (effort: S)
- [x] T008 [P] **TEST**: Chunk entity + chunk identity in `tests/test_entities.py` — AC-024: same text + same location → same `chunk_id`; same text + different location → different `chunk_id` → same `semantic_hash`; different text → different `semantic_hash`; non-overlapping location per file; unique ordering (effort: M)
- [x] T009 [P] **TEST**: Relationship entity in `tests/test_entities.py` — duplicate (source, target, type) rejection per repository; self-reference support; custom `provider_name:type` prefix; optional `weight` 0.0–1.0 (effort: S)
- [x] T010 [P] **TEST**: Reference entity in `tests/test_entities.py` — multiple refs between same source/target at different locations are distinct; CodeLocation bounds; source_file_id and target_file_id required (effort: S)
- [x] T011 [P] Implement Repository in `src/canonical/entities/repository.py` (effort: S)
- [x] T012 [P] Implement File in `src/canonical/entities/file.py` (effort: S)
- [x] T013 [P] Implement Symbol in `src/canonical/entities/symbol.py` (effort: S)
- [x] T014 [P] Implement Chunk in `src/canonical/entities/chunk.py` — `semantic_hash` from `text` only; `chunk_type` categories; CodeLocation validation (effort: M)
- [x] T015 [P] Implement Relationship in `src/canonical/entities/relationship.py` (effort: S)
- [x] T016 [P] Implement Reference in `src/canonical/entities/reference.py` (effort: S)
- [x] T017 [P] Implement exception types in `src/canonical/exceptions.py` — `CanonicalError`, `InvariantViolation`, `IdentifierCollision`, `SerializationError` (effort: S)

### IdentifierService

- [x] T018 [P] **TEST**: IdentifierService in `tests/test_identifiers.py` — same input → same ID across calls; different input → different ID; ID stability across restarts (effort: M)
- [x] T019 [P] Implement `IdentifierService` in `src/canonical/identifiers.py` — SHA-256 per permanent contract; per-entity generators for all 6 deterministic IDs (effort: M)

### Implementation for User Story 1

- [x] T020 [US1] **TEST**: CanonicalFactory in `tests/test_factory.py` — missing required fields → error; invalid field values → error; atomic batch (all pass or none); duplicate IDs within batch; cross-entity reference validation (effort: M)
- [x] T021 [US1] Implement `CanonicalFactory` in `src/canonical/factory.py` — `build_*` per entity type; `build_batch()` for atomic multi-entity creation; invariant + cross-reference validation; structured error reporting (effort: M)
- [x] T022 [US1] **TEST**: Serialization in `tests/test_serialization.py` — lossless roundtrip for all 6 entity types; `canonical_model_version` marker in output; major version mismatch rejection; minor version forward-compat; streaming array support (effort: M)
- [x] T023 [US1] Implement `JsonSerializer` in `src/canonical/serialization.py` — `to_json(entity)` and `from_json(json_str)`; version marker injection; major version gate; `extra="ignore"` for forward compat (effort: M)
- [x] T024 [US1] **TEST**: CanonicalRepository in `tests/test_query.py` — `get_file/symbol/chunk/relationship/reference/repository` by ID; `find_symbols(file_id)`, `find_chunks(file_id)`, `find_references(file_id)`; `find_relationships(source_id)`; `find_relationships_by_target(target_id)`; `get_file_by_path(repo, path)`; `get_symbol_by_name(repo, qualified_name)`; entity not found → error (effort: M)
- [x] T025 [US1] Implement `CanonicalRepository` in `src/canonical/query.py` — in-memory dict-backed lookup; all get/find/find_by methods; cross-entity navigation; stateless (entity collection passed at construction); no persistence dependencies (effort: M)

### Implementation for User Story 2

- [x] T026 [P] [US2] **TEST**: `FileAdapter` contract test suite in `tests/contract/test_file_adapter.py` — validate deterministic ID, checksum, language inference, path normalization (effort: M)
- [x] T027 [P] [US2] **TEST**: `SymbolAdapter` contract test suite in `tests/contract/test_symbol_adapter.py` — validate qualified_name construction, kind mapping, CodeLocation bounds, children hierarchy (effort: M)
- [x] T028 [P] [US2] **TEST**: `ChunkAdapter` contract test suite in `tests/contract/test_chunk_adapter.py` — validate composite ID, semantic_hash, ordering, chunk_type mapping, no embedding leakage (effort: M)
- [x] T029 [P] [US2] **TEST**: `RelationshipAdapter` contract test suite in `tests/contract/test_relationship_adapter.py` — validate composite ID, duplicate rejection, custom type prefix, optional weight (effort: M)
- [x] T030 [P] [US2] Implement in-memory adapter stubs in `src/canonical/adapters/` — `InMemoryFileAdapter`, `InMemorySymbolAdapter`, `InMemoryChunkAdapter`, `InMemoryRelationshipAdapter` for contract test validation (effort: M)

### Implementation for User Story 3

- [x] T031 [US3] Validate **AC-010, AC-011** (provider equivalence) — same `semantic_hash` across providers; `equivalent_to` linking; identical canonical identifiers for same file at same location (effort: M)
- [x] T032 [US3] Validate **AC-012, AC-013** (determinism) — same input → same IDs across runs; reordered creation → identical entities (effort: M)

### Implementation for User Story 4

- [ ] T033 [US4] Validate **AC-003 through AC-006** (navigation) — Symbol → File; Chunk → source location; File → Symbols enumeration; Relationship query by entity (effort: M)

### Polish

- [ ] T034 [P] Validate **AC-001, AC-002** (reconstruction) — full entity graph reconstructable from canonical entities; reconstructed graph identical to original (effort: M)
- [ ] T035 [P] Validate **AC-014 through AC-016** (isolation) — no provider imports in adapter test code; removing adapter leaves others unaffected (effort: S)
- [ ] T036 [P] Validate **AC-017 through AC-024** (boundary conditions) — empty repo; single file; large files; Unicode; circular symbols; binary files; missing optional fields; same `semantic_hash` / different `chunk_id` (AC-024) (effort: M)
- [ ] T037 [P] Validate **SC-001, SC-002** (performance) — reconstruction <5s for 10k entities; cross-provider `semantic_hash` and identifier matching (effort: M)

---

## Summary

| Metric | Count |
|--------|-------|
| **Total tasks** | **37** |
| Test tasks | 18 |
| Implementation tasks | 16 |
| Validation tasks | 3 |
| Parallelizable tasks | 22 |
| Phases | 7 |
| User stories | 4 |
| Acceptance criteria tested | 21 (AC-007–009 moved to KNOW-004) |
| Success criteria validated | 2 (SC-003 moved to KNOW-004) |
| Adapter contract test suites | 4 |

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
  - Phase 2 sub-dependency: CodeLocation (T003-T004) → Entities (T005-T017) → IdentifierService (T018-T019)
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (P1) → MVP: Factory, Serialization, Query (T020-T025)
  - US2 (P1) → Adapters: Contract tests, stubs (T026-T030)
  - US3 (P2) → Determinism: Cross-provider validation (T031-T032)
  - US4 (P3) → Navigation: Relationship traversal (T033)
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories. **MVP scope**.
- **US2 (P1)**: Can start after Foundational (Phase 2) — May integrate with US1 (Factory) but is independently testable via contract tests
- **US3 (P2)**: Can start after Foundational (Phase 2) — Depends on US1 (Factory) and US2 (Adapters) for cross-provider comparison
- **US4 (P3)**: Can start after Foundational (Phase 2) — Depends on US1 (Query) for relationship navigation

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Core implementation before validation
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T001-T002)
- All Foundational tasks marked [P] can run in parallel (T003-T019)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All adapter contract tests (T026-T029) can run in parallel
- All polish validation tasks (T034-T037) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "CanonicalFactory test in tests/test_factory.py"
Task: "Serialization test in tests/test_serialization.py"
Task: "CanonicalRepository test in tests/test_query.py"

# Launch all implementations for User Story 1 together:
Task: "CanonicalFactory in src/canonical/factory.py"
Task: "JsonSerializer in src/canonical/serialization.py"
Task: "CanonicalRepository in src/canonical/query.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (Factory + Serialization + Query)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 (Developer) → Test independently → Deploy/Demo (MVP!)
3. Add US2 (Integrator) → Test independently → Deploy/Demo
4. Add US3 (Engineer) → Test independently → Deploy/Demo
5. Add US4 (Consumer) → Test independently → Deploy/Demo

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Factory + Serialization + Query)
   - Developer B: User Story 2 (Adapter contracts + stubs)
   - Developer C: User Story 3 (Cross-provider validation)
   - Developer D: User Story 4 (Relationship navigation)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence

### Key exclusions from KNOW-002 (moved to KNOW-004)

- Persistence (MemoryRepository, SqlAlchemyRepository, Postgres)
- Snapshot lifecycle (create_snapshot, restore_snapshot, rollback, checksum, manifest, verification) — moved to KNOW-004
- SC-003 (snapshot performance) — moved to KNOW-004
