# Tasks: KNOW-001 Foundation Architecture

**Input**: Design documents from `/specs/001-know-001-foundation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Scope constraint**: KNOW-001 is **foundation only**. Everything related to concrete ingestion (Git, filesystem, PDF), ingestion pipeline, chunking, Qdrant/PgVector, code parsing implementation, compression/ranking implementation, and layer orchestration belongs in KNOW-002+ or benchmark specs. See `# Knowledge Boundaries` section below.

**User Stories**: All 5 from spec.md are retained but their per-story implementation scope is significantly narrowed to foundation-level contracts only.

## Format: `- [ ] [ID] [P?] [Story] Description with file path`

---

## Knowledge Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                     KNOW-001: Foundation                         │
│                                                                  │
│  Entities                │  Provider Contracts                   │
│  ─────────               │  ───────────────────                  │
│  KnowledgeSource         │  StorageProvider  (full ABC)          │
│  KnowledgeChunk          │  VectorProvider   (full ABC)          │
│  KnowledgeVersion        │  GraphProvider    (full ABC)          │
│  RetrievalPipeline       │  EmbeddingProvider(full ABC)          │
│  GraphNode, GraphEdge    │  RankingStrategy  (minimal stub)      │
│  Memory, MemoryFact,     │  CompressionProvider (minimal stub)   │
│    MemoryRelationship,   │  ContextBuilder   (minimal stub)      │
│    MemorySummary         │  CodeParserProvider (minimal stub)    │
│  Repository, File,       │                                        │
│    Symbol, Dependency,   │  Reference implementations:           │
│    Reference             │  InMemoryVectorProvider only          │
│                          │                                        │
│  Observability           │  Determinism                           │
│  (interfaces only)       │  KnowledgeVersion + Audit Contracts   │
└─────────────────────────────────────────────────────────────────┘

MOVED TO KNOW-002+ (NOT in KNOW-001):
  SourceProvider           ChunkingStrategy
  IngestionPipeline       IngestionJob
  Git / Filesystem / PDF  Qdrant / PgVector
  Code parsing impl       Compression impl
  Ranking impl            ContextBuilder impl
  Layer orchestration     Retrieval execution
  1M LOC / 100K chunk benches → KNOW-BENCH-001
```

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `packages/knowhere-core/` package scaffold and integrate into the existing uv workspace. Foundation-level — no implementations are provided in this phase, only the directory structure and package metadata.

- [X] T001 Create `packages/knowhere-core/` directory structure: `src/knowhere/{entities,providers,types,exceptions}/`, `tests/{contract,unit}/`, `examples/`
- [X] T002 [P] Create `packages/knowhere-core/pyproject.toml` with Python 3.11+, Pydantic v2, stdlib-only dependencies (no Qdrant, no tree-sitter, no external vector DB clients)
- [X] T003 [P] Add `packages/knowhere-core` to `[tool.uv.workspace]` members in root `pyproject.toml`
- [X] T004 [P] Add `packages/knowhere-core` to pyright `executionEnvironments` in root `pyproject.toml`
- [X] T005 [P] Create `packages/knowhere-core/src/knowhere/__init__.py` with public API exports

**Checkpoint**: `uv sync --all-packages` succeeds, `uv run --package knowhere-core python -c "import knowhere"` works.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core type system, all entity models, provider ABCs (4 full + 4 stub), domain exceptions, and provider base. **CRITICAL**: Completing this phase unblocks all user stories.

### Type System & Enums

- [X] T006 [P] Define `ChunkType` enum (14 values: CODE_FILE, CODE_CLASS, CODE_FUNCTION, CODE_INTERFACE, CODE_SYMBOL, DOCUMENT, DOCUMENT_SECTION, DOCUMENT_PARAGRAPH, MEMORY, MEMORY_FACT, MEMORY_SUMMARY, DATASET, IMAGE, CUSTOM, UNKNOWN) in `packages/knowhere-core/src/knowhere/types/chunk_type.py`
- [X] T007 [P] Define `KnowledgeVersionStatus` enum (sealing, sealed, corrupted) in `packages/knowhere-core/src/knowhere/types/version.py`
- [X] T008 [P] Define capability type (`Capability` with name, version, stability) and metric/consistency report types in `packages/knowhere-core/src/knowhere/types/metrics.py`

### Entity Models (6 entity groups)

- [X] T009 [P] Implement `KnowledgeSource` entity (source_id, source_type, ingestion_timestamp, hash, status, metadata) — abstract base; subtypes REPOSITORY, DOCUMENT, DATASET, IMAGE, MEMORY, CUSTOM — in `packages/knowhere-core/src/knowhere/entities/source.py`
- [X] T010 [P] Implement `KnowledgeChunk` entity (chunk_id UUID5 deterministic, source_id, knowledge_version, chunk_type, content, embedding nullable, parent_chunk_id, root_chunk_id, metadata with provenance) in `packages/knowhere-core/src/knowhere/entities/chunk.py`
- [X] T011 [P] Implement `KnowledgeVersion` entity (version_id, created_at, parent_version nullable, status, checksum, metadata) in `packages/knowhere-core/src/knowhere/entities/version.py`
- [X] T012 [P] Implement `RetrievalPipeline` entity with minimal fields (pipeline_id, name, config) — **no strategies, fusion, or provider refs** — execution belongs to KNOW-005 — in `packages/knowhere-core/src/knowhere/entities/pipeline.py`
- [X] T013 [P] Implement `GraphNode` and `GraphEdge` entities in `packages/knowhere-core/src/knowhere/entities/graph.py`
- [X] T014 [P] Implement Memory Layer entities (Memory, MemoryFact, MemoryRelationship, MemorySummary) in `packages/knowhere-core/src/knowhere/entities/memory.py`
- [X] T015 [P] Implement Code Memory entities (Repository, File, Symbol, Dependency, Reference) — **data structures only, no CodeParserProvider yet** — in `packages/knowhere-core/src/knowhere/entities/code.py`

### Provider Base & ABCs (4 full + 4 stub)

- [X] T016 [P] Define `ProviderMetadata` base (provider_name, provider_version, provider_capabilities) in `packages/knowhere-core/src/knowhere/providers/__init__.py`
- [X] T017 [P] Implement `VectorProvider` ABC (upsert, search, delete, list_collections, rebuild, verify_consistency) — full interface — in `packages/knowhere-core/src/knowhere/providers/vector.py`
- [X] T018 [P] Implement `EmbeddingProvider` ABC (embed, embed_single, embedding_dimensions) — full interface — in `packages/knowhere-core/src/knowhere/providers/embedding.py`
- [X] T019 [P] Implement `GraphProvider` ABC (create_node, create_edge, traverse, query_by_type, rebuild, verify_consistency) — full interface — in `packages/knowhere-core/src/knowhere/providers/graph.py`
- [X] T020 [P] Implement `StorageProvider` ABC (KnowledgeSource CRUD, KnowledgeChunk CRUD, KnowledgeVersion CRUD, RetrievalPipeline CRUD, GraphNode/GraphEdge CRUD) — full interface — in `packages/knowhere-core/src/knowhere/providers/storage.py`
- [X] T021 [P] Implement `CodeParserProvider` stub ABC (parse_file, supported_languages) — **interface only, no implementation** — in `packages/knowhere-core/src/knowhere/providers/code_parser.py`
- [X] T022 [P] Implement `RankingStrategy` stub ABC (rank) — **interface only, no implementation** — in `packages/knowhere-core/src/knowhere/providers/ranking.py`
- [X] T023 [P] Implement `CompressionProvider` stub ABC (compress, estimate_ratio) — **interface only, no implementation** — in `packages/knowhere-core/src/knowhere/providers/compression.py`
- [X] T024 [P] Implement `ContextBuilder` stub ABC (build) — **interface only, no implementation** — in `packages/knowhere-core/src/knowhere/providers/context_builder.py`

### Domain Exceptions

- [X] T025 [P] Define core domain exceptions (ProviderNotFoundError, VersionCorruptedError, ConfigurationError, ChunkValidationError) in `packages/knowhere-core/src/knowhere/exceptions/__init__.py` — **no ingestion-specific exceptions** (SourceNotFoundError, etc. belong to KNOW-002)

### Entity Unit Tests

- [X] T026 [P] Write KnowledgeChunk unit tests in `packages/knowhere-core/tests/unit/test_knowledge_chunk.py` (deterministic chunk_id, valid chunk_type, lineage validation, non-empty content)
- [X] T027 [P] Write KnowledgeVersion unit tests in `packages/knowhere-core/tests/unit/test_knowledge_version.py` (status transitions, checksum verification)
- [X] T028 [P] Write KnowledgeSource + Code Memory + Memory entity unit tests in `packages/knowhere-core/tests/unit/test_entities.py`
- [X] T029 [P] Write GraphNode/GraphEdge unit tests in `packages/knowhere-core/tests/unit/test_graph_entities.py`
- [X] T030 [P] Write RetrievalPipeline entity unit tests in `packages/knowhere-core/tests/unit/test_retrieval_pipeline.py`

**Checkpoint**: All 6 entity groups, all 8 provider ABCs, exceptions, and type system implemented and tested. Foundation ready.

---

## Phase 3: User Story 1 — Vendor Adds a New Vector Database Backend (Priority: P1) 🎯 MVP

**Goal**: A developer can add a new vector database backend by implementing only the `VectorProvider` interface. KNOW-001 provides the ABC and an `InMemoryVectorProvider` reference — **no Qdrant, no PgVector** (those belong to KNOW-002+).

**Independent Test**: Implement a mock VectorProvider, switch configuration to use it, and verify that all provider operations (upsert, search, delete) work through the provider boundary.

### Tests

- [X] T031 [P] [US1] Write VectorProvider contract tests in `packages/knowhere-core/tests/contract/test_vector_provider.py` (test_upsert_and_search_roundtrip, test_search_returns_top_k, test_delete_removes_from_index, test_rebuild_produces_identical_results, test_provider_metadata)
- [X] T032 [P] [US1] Write EmbeddingProvider contract tests in `packages/knowhere-core/tests/contract/test_embedding_provider.py` (test_embed_returns_correct_dimensionality, test_embed_batch, test_embed_similar_texts, test_provider_metadata)

### Implementation

- [X] T033 [US1] Implement `InMemoryVectorProvider` in `packages/knowhere-core/examples/vector_memory.py` — dict-backed reference implementation fulfilling the full VectorProvider ABC (upsert, search, delete, list_collections, rebuild, verify_consistency)
- [X] T034 [US1] Implement stub `EmbeddingProvider` in `packages/knowhere-core/examples/embedding_stub.py` — fixed-dimension, identity-based similarity
- [X] T035 [US1] Implement provider registration config (YAML-based, env-var override) for VectorProvider in `packages/knowhere-core/src/knowhere/providers/registry.py` — minimal registry, no full plugin discovery
- [X] T036 [US1] Configuration switch test: InMemoryVectorProvider loaded via config → all contract operations pass — in `packages/knowhere-core/tests/integration/test_vector_provider_switch.py`

**Checkpoint**: InMemoryVectorProvider passes all contract tests. Configuration can select it. A developer can write a new VectorProvider implementation and swap it in without touching core code.

---

## Phase 4: User Story 2 — Developer Works with Code Memory Entities (Priority: P1)

**Goal**: A developer can define code memory entities (Repository, File, Symbol, Dependency, Reference) and reference a minimal `CodeParserProvider` stub. **Concrete code parsing implementation belongs to KNOW-002.**

**Independent Test**: Create a Repository + File + Symbol entity graph, verify entity validation and relationships are correct.

### Tests

- [X] T037 [P] [US2] Write CodeParserProvider contract tests in `packages/knowhere-core/tests/contract/test_code_parser_provider.py` (test_provider_metadata, test_supported_languages_list — these pass against the stub; full tests belong to KNOW-002)

### Implementation

- [X] T038 [US2] Implement Code Memory entity validation rules (Repository → File → Symbol → Dependency → Reference relationships) in `packages/knowhere-core/src/knowhere/entities/code.py` (extends T015)

**Checkpoint**: Code Memory entities are defined, validated, and importable. The stub CodeParserProvider ABC exists for KNOW-002 to implement.

---

## Phase 5: User Story 3 — Platform Team Defines Compression Contract (Priority: P2)

**Goal**: A developer can see the CompressionProvider, RankingStrategy, and ContextBuilder interfaces. **No implementations — those belong to KNOW-002+.**

**Independent Test**: Verify the ABCs exist, have correct method signatures, and provider metadata is properly defined.

### Tests

- [X] T039 [P] [US3] Write CompressionProvider contract tests in `packages/knowhere-core/tests/contract/test_compression_provider.py` (test_provider_metadata — only stub-level tests; full contract tests belong to KNOW-002)
- [X] T040 [P] [US3] Write RankingStrategy contract tests in `packages/knowhere-core/tests/contract/test_ranking_strategy.py` (test_provider_metadata — only stub-level tests)
- [X] T041 [P] [US3] Write ContextBuilder contract tests in `packages/knowhere-core/tests/contract/test_context_builder.py` (test_provider_metadata — only stub-level tests)

### Implementation

- [X] T042 [US3] Verify ABC stubs are correctly placed and importable — no implementation required for KNOW-001

**Checkpoint**: Three ABCs exist with correct method signatures. Contract tests for provider metadata pass. KNOW-002 will add implementations.

---

## Phase 6: User Story 4 — Developer Verifies Deterministic Retrieval (Priority: P2)

**Goal**: A quality engineer can see KnowledgeVersion lifecycle and audit contract. **Full pipeline determinism verification belongs to KNOW-005+.**

**Independent Test**: Create a KnowledgeVersion, transition it through sealing → sealed, and verify checksum integrity.

### Tests

- [X] T043 [P] [US4] Write KnowledgeVersion lifecycle integration test in `packages/knowhere-core/tests/integration/test_knowledge_version_lifecycle.py` (test_version_sealing, test_version_checksum, test_corrupted_detection)

### Implementation

- [X] T044 [US4] Implement KnowledgeVersion lifecycle management (sealing → sealed → corrupted state machine, checksum computation) in `packages/knowhere-core/src/knowhere/entities/version.py` (extends T011)
- [X] T045 [US4] Define audit contract — record retrieval chain: query → knowledge version → candidates → final output — as an abstract interface (no concrete logger) in `packages/knowhere-core/src/knowhere/services/audit.py`
- [X] T046 [US4] Write consistency check interfaces (rebuild from Storage, compare results) in `packages/knowhere-core/src/knowhere/services/consistency.py` — abstract only, no concrete rebuild logic

**Checkpoint**: KnowledgeVersion transitions and checksums work. Audit contract interface exists for concrete logging in KNOW-005.

---

## Phase 7: User Story 5 — Core Team Merges Upstream Release (Priority: P3)

**Goal**: The core team can verify that all Syntegrity extensions live outside upstream core files. This is a **placement and configuration validation** story for KNOW-001.

### Tests

- [X] T047 [P] [US5] Write GraphProvider contract tests in `packages/knowhere-core/tests/contract/test_graph_provider.py` (test_provider_metadata, test_create_and_query_node)
- [X] T048 [P] [US5] Write StorageProvider contract tests in `packages/knowhere-core/tests/contract/test_storage_provider.py` (test_create_and_retrieve_source, test_create_and_retrieve_chunk, test_create_and_seal_version)

### Implementation

- [X] T049 [P] [US5] Implement `InMemoryStorageProvider` in `packages/knowhere-core/examples/storage_memory.py` — dict-backed reference implementation fulfilling the full StorageProvider ABC
- [X] T050 [P] [US5] Implement `InMemoryGraphProvider` in `packages/knowhere-core/examples/graph_memory.py` — dict-backed reference implementation fulfilling the full GraphProvider ABC
- [X] T051 [US5] Implement provider configuration validation: missing provider → graceful ConfigurationError; invalid config → clear error message — in `packages/knowhere-core/src/knowhere/providers/registry.py` (extends T035)
- [X] T052 [US5] Verify all extensions live in `packages/knowhere-core/` not in `packages/shared-python/shared/` — upstream boundary check file in `packages/knowhere-core/UPSTREAM_BOUNDARY.md`

**Checkpoint**: All 8 ABCs have contract tests + at least one reference implementation (VectorProvider, StorageProvider, GraphProvider have full refs; EmbeddingProvider has stub; CodeParserProvider, RankingStrategy, CompressionProvider, ContextBuilder have minimal stubs). Provider configuration handles errors gracefully. Extensions are outside upstream core files.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Observability interfaces, documentation, quality checks.

- [X] T053 [P] Define observability interfaces (latency p50/p95/p99, retrieval count, compression ratio, embedding token count — as abstract metrics contracts, no concrete instrumentation) in `packages/knowhere-core/src/knowhere/services/metrics.py`
- [X] T054 [P] Validate no Atlas imports exist in `packages/knowhere-core/` (SC-NF08 compliance)
- [X] T055 [P] Validate no Rust toolchain dependency in `packages/knowhere-core/pyproject.toml` (SC-NF07 compliance)
- [X] T056 [P] Validate no Qdrant, no PgVector, no tree-sitter dependencies in `packages/knowhere-core/pyproject.toml` (belong to KNOW-002+)
- [X] T057 Run full contract test suite: `pytest tests/contract/` — all tests pass
- [X] T058 Run lint (ruff) and typecheck (pyright) across all new code
- [X] T059 Write `packages/knowhere-core/README.md` with architecture overview, entity reference, provider implementation guide, and list of deferred items (what belongs to KNOW-002+)
- [X] T060 Run `uv sync --all-packages` and verify no workspace resolution errors

**Checkpoint**: All contract tests pass. No lint/type errors. No disallowed dependencies. README documents both the foundation and the boundary with future specs.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup ──────────────────────────────────────────── No deps
    │
    ▼
Phase 2: Foundational ───────────────────────────────────── Depends on Phase 1 (BLOCKS all stories)
    │
    ├─────────────────────────────────────────────────────── Foundation done, stories can start
    │
    ├──► Phase 3: US1 — VectorProvider  (P1)  ──────────── Depends on Phase 2  [MVP]
    ├──► Phase 4: US2 — Code Memory      (P1)  ──────────── Depends on Phase 2
    ├──► Phase 5: US3 — Compression      (P2)  ──────────── Depends on Phase 2 (stub only)
    ├──► Phase 6: US4 — Determinism      (P2)  ──────────── Depends on Phase 2
    └──► Phase 7: US5 — Upstream         (P3)  ──────────── Depends on Phase 2
    │
    ▼
Phase 8: Polish & Cross-Cutting ─────────────────────────── Depends on all stories
```

### User Story Dependencies

| Story | Priority | Depends On | Parallelizable With |
|-------|----------|------------|---------------------|
| US1 — VectorProvider | P1 | Phase 2 | US2–US5 (no cross-deps) |
| US2 — Code Memory | P1 | Phase 2 | US1, US3–US5 |
| US3 — Compression stubs | P2 | Phase 2 | US1, US2, US4, US5 |
| US4 — Determinism | P2 | Phase 2 | US1–US3, US5 |
| US5 — Upstream | P3 | Phase 2 | US1–US4 |

**All 5 user stories are independent** once Phase 2 completes. They work on different files with no cross-dependencies.

### Within Each Phase

Entities → Type definitions → Provider ABCs → Domain exceptions → Contract tests → Reference implementations → Integration tests

---

## Parallel Example: Phase 2 Foundational

```bash
# All entity tasks run in parallel:
cd packages/knowhere-core
# src/knowhere/entities/source.py     (T009)
# src/knowhere/entities/chunk.py      (T010)
# src/knowhere/entities/version.py    (T011)
# src/knowhere/entities/pipeline.py   (T012)
# src/knowhere/entities/graph.py      (T013)
# src/knowhere/entities/memory.py     (T014)
# src/knowhere/entities/code.py       (T015)

# All provider ABC tasks run in parallel:
# src/knowhere/providers/__init__.py  (T016)
# src/knowhere/providers/vector.py    (T017)
# src/knowhere/providers/embedding.py (T018)
# src/knowhere/providers/graph.py     (T019)
# src/knowhere/providers/storage.py   (T020)
# src/knowhere/providers/code_parser.py    (T021)
# src/knowhere/providers/ranking.py        (T022)
# src/knowhere/providers/compression.py    (T023)
# src/knowhere/providers/context_builder.py (T024)
```

---

## Implementation Strategy

### MVP First (US1 Only in KNOW-001)

1. Complete Phase 1: Setup (5 tasks)
2. Complete Phase 2: Foundational — all entities + all ABCs (25 tasks)
3. Complete Phase 3: US1 — VectorProvider contract + InMemoryVectorProvider (6 tasks)
4. **MVP STOP**: Foundation package exists with 6 entity groups, 8 ABCs, InMemoryVectorProvider as reference. KNOW-002 can now be planned with SourceProvider, ChunkingStrategy, concrete backends.

### Subsequent Stories (All Parallel After Phase 2)

- US4 (Determinism) can be done immediately after Phase 2 since it only touches KnowledgeVersion + audit interfaces
- US5 (Upstream) is mostly verification — can be early
- US2 + US3 are thin in KNOW-001 (entities + stubs)
- Phase 8 (Polish) caps everything

### What Gets Deferred to KNOW-002+

| Concept | Target |
|---------|--------|
| SourceProvider + ChunkingStrategy | KNOW-002 Ingestion Architecture |
| IngestionPipeline + IngestionJob | KNOW-002 Ingestion Architecture |
| Git/filesystem/PDF source ingestion | KNOW-002 Ingestion Architecture |
| Qdrant vector store implementation | KNOW-003 Vector Backend |
| PgVector vector store implementation | KNOW-003 Vector Backend |
| CodeParserProvider implementation | KNOW-004 Code Memory |
| Compression/ranking implementations | KNOW-005 Retrieval Pipeline |
| Retrieval layer orchestration | KNOW-005 Retrieval Pipeline |
| 1M LOC / 100K chunk benchmarks | KNOW-BENCH-001 |

---

## Task Count Summary

| Phase | Label | Tasks | [P] Tasks |
|-------|-------|-------|-----------|
| Phase 1 | Setup | 5 | 3 |
| Phase 2 | Foundational (BLOCKS all) | 25 | 20 |
| Phase 3 | US1 — VectorProvider (P1) | 6 | 2 |
| Phase 4 | US2 — Code Memory entities (P1) | 2 | 1 |
| Phase 5 | US3 — Compression stubs (P2) | 4 | 3 |
| Phase 6 | US4 — Determinism (P2) | 4 | 1 |
| Phase 7 | US5 — Upstream (P3) | 6 | 4 |
| Phase 8 | Polish & Cross-Cutting | 8 | 4 |
| **Total** | | **60** | **38** |

## Validation Checklist

- [X] All tasks use `- [ ]` markdown checkbox format
- [X] All tasks have sequential Task IDs (T001–T060)
- [X] No SourceProvider, ChunkingStrategy, IngestionPipeline, or IngestionJob tasks exist in KNOW-001
- [X] No Qdrant, PgVector, tree-sitter, or concrete backend dependency
- [X] No 1M LOC or 100K chunk benchmark targets
- [X] No layer orchestration or retrieval execution tasks
- [X] RetrievalPipeline is minimal entity (`id`, `name`, `config`) — no strategies/fusion/provider refs
- [X] CodeParserProvider, RankingStrategy, CompressionProvider, ContextBuilder are stub ABCs only
- [X] VectorProvider, EmbeddingProvider, GraphProvider, StorageProvider are full ABCs
- [X] Only reference implementations: InMemoryVectorProvider, InMemoryStorageProvider, InMemoryGraphProvider, EmbeddingStub
- [X] Setup and Foundational phases have NO story label
- [X] User story phases correctly labeled [US1]–[US5]
- [X] All tasks include exact file paths
- [X] Each user story has independent test criteria
- [X] Knowledge boundary section documents what is deferred to KNOW-002+
