# Tasks: KNOW-002 Canonical Knowledge Model

**Input**: Design documents from `specs/002-know-002-canonical/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/  
**Approach**: Test-first — write and see each test fail before implementing.

> **Non-normative**: This document describes the Python reference implementation. The canonical contract itself is defined in `spec.md` and `data-model.md` and is implementation-agnostic.

**Format**: `- [ ] [TaskID] [P?] Description (effort: S/M/L) — [file path]`
`[P]` = parallelizable with other tasks in the same phase.

## Phase 1: CodeLocation

- [ ] T001 [P] **TEST**: CodeLocation in `tests/test_code_location.py` — validate required fields, `start_line ≤ end_line` invariant, column consistency, immutability, equality, string serialization (effort: S)
- [ ] T002 [P] Implement CodeLocation in `src/canonical/value_objects/code_location.py` as Pydantic frozen model with field validators (effort: S)

## Phase 2: Entities (All 6)

- [ ] T003 [P] **TEST**: Repository entity in `tests/test_entities.py` — `source_uri` and `name` required; `id`, `source_uri`, `source` immutable; metadata defaults; serialization roundtrip (effort: S)
- [ ] T004 [P] **TEST**: File entity in `tests/test_entities.py` — `path` + `repository_id` identity; `checksum` and `size_bytes` required; language optional; symbol/chunk/reference collection defaults (effort: S)
- [ ] T005 [P] **TEST**: Symbol entity in `tests/test_entities.py` — `qualified_name` unique per repository; CodeLocation bounds; optional `signature`, `documentation`, `children`, `scope`; no circular children (effort: S)
- [ ] T006 [P] **TEST**: Chunk entity + chunk identity in `tests/test_entities.py` — AC-024: same text + same location → same `chunk_id`; same text + different location → different `chunk_id` → same `semantic_hash`; different text → different `semantic_hash`; non-overlapping location per file; unique ordering (effort: M)
- [ ] T007 [P] **TEST**: Relationship entity in `tests/test_entities.py` — duplicate (source, target, type) rejection per repository; self-reference support; custom `provider_name:type` prefix; optional `weight` 0.0–1.0 (effort: S)
- [ ] T008 [P] **TEST**: Reference entity in `tests/test_entities.py` — multiple refs between same source/target at different locations are distinct; CodeLocation bounds; source_file_id and target_file_id required (effort: S)
- [ ] T010 [P] Implement Repository in `src/canonical/entities/repository.py` (effort: S)
- [ ] T011 [P] Implement File in `src/canonical/entities/file.py` (effort: S)
- [ ] T012 [P] Implement Symbol in `src/canonical/entities/symbol.py` (effort: S)
- [ ] T013 [P] Implement Chunk in `src/canonical/entities/chunk.py` — `semantic_hash` from `text` only; `chunk_type` categories; CodeLocation validation (effort: M)
- [ ] T014 [P] Implement Relationship in `src/canonical/entities/relationship.py` (effort: S)
- [ ] T015 [P] Implement Reference in `src/canonical/entities/reference.py` (effort: S)
- [ ] T017 [P] Implement exception types in `src/canonical/exceptions.py` — `CanonicalError`, `InvariantViolation`, `IdentifierCollision`, `SerializationError` (effort: S)

## Phase 3: IdentifierService

- [ ] T018 **TEST**: IdentifierService in `tests/test_identifiers.py` — same input → same ID across calls; different input → different ID; ID stability across restarts (effort: M)
- [ ] T019 Implement `IdentifierService` in `src/canonical/identifiers.py` — SHA-256 per permanent contract; per-entity generators for all 6 deterministic IDs (effort: M)

## Phase 4: CanonicalFactory

- [ ] T020 **TEST**: CanonicalFactory in `tests/test_factory.py` — missing required fields → error; invalid field values → error; atomic batch (all pass or none); duplicate IDs within batch; cross-entity reference validation (effort: M)
- [ ] T021 Implement `CanonicalFactory` in `src/canonical/factory.py` — `build_*` per entity type; `build_batch()` for atomic multi-entity creation; invariant + cross-reference validation; structured error reporting (effort: M)

## Phase 5: Serialization

- [ ] T022 **TEST**: Serialization in `tests/test_serialization.py` — lossless roundtrip for all 6 entity types; `canonical_model_version` marker in output; major version mismatch rejection; minor version forward-compat; streaming array support (effort: M)
- [ ] T023 Implement `JsonSerializer` in `src/canonical/serialization.py` — `to_json(entity)` and `from_json(json_str)`; version marker injection; major version gate; `extra="ignore"` for forward compat (effort: M)

## Phase 6: CanonicalRepository (Query & Navigation)

- [ ] T024 **TEST**: CanonicalRepository in `tests/test_query.py` — `get_file/symbol/chunk/relationship/reference/repository` by ID; `find_symbols(file_id)`, `find_chunks(file_id)`, `find_references(file_id)`; `find_relationships(source_id)`; `find_relationships_by_target(target_id)`; `get_file_by_path(repo, path)`; `get_symbol_by_name(repo, qualified_name)`; entity not found → error (effort: M)
- [ ] T025 Implement `CanonicalRepository` in `src/canonical/query.py` — in-memory dict-backed lookup; all get/find/find_by methods; cross-entity navigation; stateless (entity collection passed at construction); no persistence dependencies (effort: M)

## Phase 7: Adapter Contract Tests

- [ ] T026 [P] **TEST**: `FileAdapter` contract test suite in `tests/contract/test_file_adapter.py` — validate deterministic ID, checksum, language inference, path normalization (effort: M)
- [ ] T027 [P] **TEST**: `SymbolAdapter` contract test suite in `tests/contract/test_symbol_adapter.py` — validate qualified_name construction, kind mapping, CodeLocation bounds, children hierarchy (effort: M)
- [ ] T028 [P] **TEST**: `ChunkAdapter` contract test suite in `tests/contract/test_chunk_adapter.py` — validate composite ID, semantic_hash, ordering, chunk_type mapping, no embedding leakage (effort: M)
- [ ] T029 [P] **TEST**: `RelationshipAdapter` contract test suite in `tests/contract/test_relationship_adapter.py` — validate composite ID, duplicate rejection, custom type prefix, optional weight (effort: M)
- [ ] T030 [P] Implement in-memory adapter stubs in `src/canonical/adapters/` — `InMemoryFileAdapter`, `InMemorySymbolAdapter`, `InMemoryChunkAdapter`, `InMemoryRelationshipAdapter` for contract test validation (effort: M)

## Phase 8: Acceptance Criteria

- [ ] T031 Validate **AC-001, AC-002** (reconstruction) — full entity graph reconstructable from canonical entities; reconstructed graph identical to original (effort: M)
- [ ] T032 Validate **AC-003 through AC-006** (navigation) — Symbol → File; Chunk → source location; File → Symbols enumeration; Relationship query by entity (effort: M)
- [ ] T033 Validate **AC-010 through AC-013** (provider equivalence, determinism) — same `semantic_hash` across providers; `equivalent_to` linking; same input → same IDs across runs; reordered creation → identical entities (effort: M)
- [ ] T034 Validate **AC-014 through AC-016** (isolation) — no provider imports in adapter test code; removing adapter leaves others unaffected (effort: S)
- [ ] T035 Validate **AC-017 through AC-024** (boundary conditions) — empty repo; single file; large files; Unicode; circular symbols; binary files; missing optional fields; same `semantic_hash` / different `chunk_id` (AC-024) (effort: M)
- [ ] T036 Validate **SC-001, SC-002** (performance) — reconstruction <5s for 10k entities; cross-provider `semantic_hash` and identifier matching (effort: M)

---

## Summary

| Metric | Count |
|--------|-------|
| **Total tasks** | **34** |
| Test tasks (TDD) | 18 |
| Implementation tasks | 16 |
| Parallelizable tasks | 20 |
| Phases | 8 |
| Acceptance criteria tested | 21 (AC-007–009 moved to KNOW-004) |
| Success criteria validated | 2 (SC-003 moved to KNOW-004) |
| Adapter contract test suites | 4 |

### Key exclusions from KNOW-002 (moved to KNOW-004)
- Persistence (MemoryRepository, SqlAlchemyRepository, Postgres)
- Snapshot lifecycle (create_snapshot, restore_snapshot, rollback, checksum, manifest, verification) — moved to KNOW-004
- SC-003 (snapshot performance) — moved to KNOW-004

### Dependencies

```
Phase 1 (CodeLocation) → Phase 2 (Entities) → Phase 3 (IdentifierService) → Phase 4 (Factory) ──┐
                                                                                                  ├──→ Phase 8 (ACs)
Phase 5 (Serialization) starts after Phase 2 ─────────────────────────────────────────────────────┤
Phase 6 (Query) starts after Phase 2 ─────────────────────────────────────────────────────────────┤
Phase 7 (Contracts) starts after Phase 2 ─────────────────────────────────────────────────────────┘
```
