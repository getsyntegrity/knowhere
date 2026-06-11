# Implementation Plan: KNOW-001 Foundation Architecture

**Branch**: `001-know-001-foundation` | **Date**: 2026-06-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-know-001-foundation/spec.md`
**Status**: Draft

## Summary

Establish the foundational architecture of Knowhere with clean separation of concerns through a multi-layer module architecture (10 layers) with abstract provider interfaces. The architecture introduces a unified Ingestion Layer with `KnowledgeSource` root entity, `KnowledgeChunk` as the atomic retrieval unit, a configurable `RetrievalPipeline` model, a formal `KnowledgeVersion` system for deterministic snapshots, language-specific `CodeParserProvider`, a `RankingLayer`, `ContextBuilder`, and 10 swappable provider interfaces — all while maintaining permanent upstream compatibility through plugin-based extension points.

**Primary constraint**: Python 3.11+ only. No Rust. No Atlas dependencies. All Syntegrity extensions live outside upstream core files.

## Technical Context

**Language/Version**: Python 3.11+ (existing workspace: `knowhere-api`, `shared-python`)  
**Primary Dependencies**: 
- Existing: FastAPI, Celery, SQLAlchemy, Pydantic, Redis
- New: `abc.ABC` for interfaces (stdlib), pluggy or entry-point-based plugin discovery, Qdrant client, pgvector/asyncpg
- Type checking: pyright (existing config)
- Linting: ruff (existing config)  
**Storage**: PostgreSQL (existing via SQLAlchemy) + Qdrant (new — vector store) + PgVector (new — alternative vector store)  
**Testing**: pytest (existing) — contract tests per provider, integration tests for pipelines, unit tests for entities  
**Target Platform**: Linux server (existing deployment)  
**Project Type**: Library / framework — new `packages/knowhere-core/` package within the existing workspace  
**Performance Goals**: Full retrieval query (Ingestion→Retrieval→Ranking→Compression→ContextBuilder) <10s for 100K+ chunk corpus (SC-NF04)  
**Constraints**: 
- No Rust toolchain or runtime dependency (SC-NF07)
- No Atlas imports or dependencies (SC-NF08)
- All extensions must live outside upstream core files (FR-027)
- Layer dependencies flow downward only (FR-012)
- Storage is authoritative source of truth (FR-009)
- Determinism scoped per knowledge version — bitwise not required, deterministically equivalent required (OBS-002)  
**Scale/Scope**: 1M+ LOC repositories, 100K+ chunk corpora, configurable per-workload tuning

## Constitution Check

_GATE: Passes. Constitution template is not yet filled in for this project. No violations or overrides needed._

The architecture respects all default principles:
- **Upstream First** (Principle 1): All extensions via providers outside core — no forks
- **Python Primary** (Principle 2): No Rust migration, no new runtimes
- **Layer Separation** (Principle 3): Strict downward-only dependency flow
- **Storage as Truth** (FR-009): Derived indices rebuildable from authoritative storage

## Project Structure

### Documentation (this feature)

```text
specs/001-know-001-foundation/
├── plan.md                  # This file — implementation plan
├── research.md              # Phase 0: existing code analysis
├── data-model.md            # Phase 1: entity definitions, type system, relationships
├── quickstart.md            # Phase 1: developer setup and first implementation
├── contracts/               # Phase 1: interface contracts
│   ├── provider_interfaces.py    # All 10 provider ABCs
│   ├── entities.py               # Core entity types
│   └── types.py                  # Enums, type aliases, and data classes
├── checklists/
│   └── requirements.md       # Quality validation checklist
└── spec.md                   # Full feature specification
```

### Source Code (repository root)

```text
packages/knowhere-core/               # NEW — core architecture library
├── pyproject.toml                    # Package config
├── src/knowhere/
│   ├── __init__.py
│   ├── entities/                     # Entity definitions
│   │   ├── __init__.py
│   │   ├── source.py                 # KnowledgeSource
│   │   ├── chunk.py                  # KnowledgeChunk
│   │   ├── pipeline.py              # RetrievalPipeline
│   │   ├── version.py               # KnowledgeVersion
│   │   └── graph.py                 # GraphNode, GraphEdge
│   ├── providers/                    # All provider interfaces
│   │   ├── __init__.py
│   │   ├── source.py                 # SourceProvider
│   │   ├── code_parser.py            # CodeParserProvider
│   │   ├── embedding.py              # EmbeddingProvider
│   │   ├── vector.py                 # VectorProvider
│   │   ├── graph.py                  # GraphProvider
│   │   ├── ranking.py                # RankingStrategy
│   │   ├── compression.py            # CompressionProvider
│   │   ├── context_builder.py        # ContextBuilder
│   │   ├── storage.py                # StorageProvider
│   │   └── chunking.py               # ChunkingStrategy
│   ├── layers/                       # Layer orchestration (optional — higher-level)
│   │   ├── __init__.py
│   │   ├── ingestion.py              # IngestionLayer
│   │   ├── retrieval.py              # RetrievalLayer
│   │   ├── ranking.py                # RankingLayer
│   │   ├── compression.py            # CompressionLayer
│   │   └── context_builder.py        # ContextBuilderLayer
│   ├── types/                        # Shared enums and types
│   │   ├── __init__.py
│   │   ├── chunk_type.py             # ChunkType enum (14 values)
│   │   ├── version.py                # KnowledgeVersionStatus enum
│   │   └── metrics.py                # Quality metrics types
│   └── exceptions/                   # Domain exceptions
│       ├── __init__.py
│       └── exceptions.py             # ProviderNotFound, VersionCorrupted, etc.
├── tests/
│   ├── contract/                     # Provider interface contract tests
│   │   ├── test_vector_provider.py
│   │   ├── test_embedding_provider.py
│   │   ├── test_compression_provider.py
│   │   └── ...
│   ├── unit/                         # Entity and layer unit tests
│   │   ├── test_knowledge_chunk.py
│   │   ├── test_knowledge_source.py
│   │   └── ...
│   └── integration/                  # Layer integration tests
│       └── test_ingestion_pipeline.py
└── examples/                         # Reference provider implementations
    ├── vector_mock.py                # In-memory VectorProvider for testing
    ├── embedding_mock.py             # Stub EmbeddingProvider
    └── compression_truncate.py       # Simple truncation CompressionProvider
```

### Integration with existing workspace

```text
packages/shared-python/shared/        # EXISTING — upstream shared library
├── core/                             # Core utilities (unchanged)
├── models/                           # DB models (unchanged)
├── services/                         # Business services (will depend on knowhere-core)
└── ...

packages/knowhere-core/               # NEW — referenced via workspace member
├── src/knowhere/
├── tests/
└── pyproject.toml
```

**Workspace changes**: Add `packages/knowhere-core` to `[tool.uv.workspace]` members in root `pyproject.toml`, and add it to pyright `executionEnvironments`.

**Structure Decision**: New `packages/knowhere-core/` module — NOT embedded inside `shared-python/` — because:
- The architecture must be upstream-compatible (Principle 1). Core interfaces must live outside the existing upstream codebase to allow clean merges.
- `shared-python` is the existing upstream shared library. `knowhere-core` is the abstraction layer. `shared-python` services (retrieval, AI, storage) will gradually depend on `knowhere-core` interfaces, not the reverse.
- Clean separation enables the architecture to evolve independently of the upstream codebase.

## Phase 0: Research Summary

See [research.md](./research.md) for full analysis of existing code, patterns, and constraints.

Key findings:
- Workspace is a uv-managed monorepo with 3 members: `apps/api`, `apps/worker`, `packages/shared-python`
- Existing retrieval in `shared/services/retrieval/` is concrete — uses BM25 channels, PostgreSQL TSVECTOR, and agentic workflows. No abstract provider layer exists.
- Existing storage adapters exist in `shared/services/storage/adapters/` (S3, OSS, filesystem) — but these are file storage, not entity/vector stores.
- Python 3.11+ with FastAPI, SQLAlchemy, Celery — all familiar patterns.
- Existing chunk model: `ChunkPayload` in publication models — concrete, bound to document parsing pipeline.

## Phase 1: Design Artifacts

| Artifact | File | Description |
|----------|------|-------------|
| Data Model | [data-model.md](./data-model.md) | Complete entity definitions, relationships, enums, and type system |
| Provider Contracts | [contracts/](./contracts/) | Python ABC interfaces for all 10 providers |
| Quickstart | [quickstart.md](./quickstart.md) | How to set up + implement first provider |

## Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Provider discovery | Entry-point-based (via `importlib.metadata` entry_points) | Python-native, no extra deps, used by pluggy/pytest | 
| Vector store abstraction | `VectorProvider` ABC with CRUD + search | Decouples retrieval from any specific backend |
| Source of truth | Storage (PostgreSQL or equivalent) | Graph/Vector are derived indices rebuildable from Storage |
| Knowledge version | Complete atomic snapshot with optional incremental internals | Enables deterministic replay without forcing full index dump for every version |
| Chunk determinism | SHA-based content hash as `chunk_id` | Cross-document dedup, deterministic identity |
| Plugin isolation | All extensions in `knowhere-core/providers/` | No modifications to upstream `shared-python/` |
| Compression quality | 3-metric system: Recall + Precision + Faithfulness | Prevents perverse optimization toward token reduction alone |
| Provider fallback | Per-category configuration (opt-in per provider type) | Storage must fail fast; Embedding may fallback |

## Complexity Tracking

No constitution violations. The architecture is more complex (10 layers, 10 providers) than a simple 3-layer design, but this is justified by:

| Concern | Why Needed | Simpler Alternative Rejected |
|---------|-----------|------------------------------|
| 10 provider interfaces | Each maps one swappable concern (embedding ≠ vector ≠ compression ≠ ranking) | Single monolithic provider would violate SRP and prevent independent swapping |
| 10 layers | Each layer has distinct responsibility (ingestion ≠ knowledge graph ≠ retrieval ≠ ranking ≠ compression ≠ context builder) | Merging would create circular dependencies and coupling |
| KnowledgeVersion as snapshot | Atlas requires full reproducibility; partial versioning breaks determinism guarantee | Per-source versioning (Option B) cannot guarantee cross-source consistency |
| Storage as SoT + derived indices | Enables rebuild without data loss; Vector/Graph are acceleration structures only | Direct-vector SoT would lose relational context; Direct-graph SoT would lose vector search |

## Next Steps

1. Review and approve this plan
2. Execute `/spec tasks` to break into implementation tasks
3. Implement Phase 1 tasks: `packages/knowhere-core/` scaffold, entity models, provider ABCs
4. Implement Phase 2 tasks: reference provider implementations, contract tests
5. Implement Phase 3 tasks: layer orchestration, ingestion/retrieval pipeline wiring
