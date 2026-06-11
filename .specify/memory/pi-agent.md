# knowhere Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-06-11

## Active Technologies

### From KNOW-001 Foundation Architecture (current)

- **Python 3.11+** — Primary runtime
- **Pydantic v2** — Interface contracts, schema validation
- **SQLAlchemy 2.0** — ORM, PostgreSQL persistence
- **FastAPI** — API framework (existing)
- **Celery** — Async task queue (existing)
- **Qdrant** — Vector store (existing)
- **PgVector** — Graph store (initial; Neo4j deferred)
- **tree-sitter** — Code parsing (Python bindings, no Rust runtime)
- **pytest** — Contract tests for all provider interfaces

### Provider Interfaces (10 total)

- `SourceProvider` — Knowledge source ingestion
- `ChunkingStrategy` — Content splitting into KnowledgeChunks
- `CodeParserProvider` — Language-specific code parsing
- `EmbeddingProvider` — Text-to-vector embedding
- `VectorProvider` — Vector storage and similarity search
- `GraphProvider` — Graph storage and traversal
- `RankingStrategy` — Candidate ranking
- `CompressionProvider` — Context compression
- `ContextBuilder` — Final context assembly
- `StorageProvider` — Persistent entity storage

### Key Architecture Concepts

- **KnowledgeSource** — Root entity for all knowledge origins
- **KnowledgeChunk** — Atomic retrieval unit (chunk_id, chunk_type, lineage, provenance)
- **KnowledgeVersion** — Sealed, verifiable index snapshot (checksum, parent_version)
- **RetrievalPipeline** — Per-workload pipeline configuration
- **Storage is source of truth** — Vector and Graph are derived indices, rebuildable from Storage
- **Determinism** — Per knowledge version; deterministically equivalent results
- **Provider versioning** — Every provider exposes name, version, structured capabilities
- **ChunkType** — 14 enum values including CUSTOM for client-defined types
- **Compression quality** — Recall + Precision + Faithfulness

## Project Structure

```text
packages/shared-python/shared/
├── models/
│   ├── database/     # SQLAlchemy ORM models
│   └── schemas/      # Pydantic schemas
├── services/
│   ├── ingestion/    # Ingestion Layer
│   ├── knowledge_graph/  # Knowledge Graph Layer
│   ├── retrieval/    # Retrieval Pipeline + Ranking
│   │   ├── ranking/
│   │   ├── compression/
│   │   └── context_builder/
│   └── providers/    # Provider registry + versioning
└── utils/

apps/api/     # API endpoints (extended with ingestion, retrieval, version routes)
apps/worker/  # Worker tasks (extended with ingestion jobs)
```

## Commands

```bash
uv sync --all-packages         # Install all dependencies
pytest tests/contract/         # Run provider contract tests
pytest tests/unit/             # Run unit tests
pytest tests/integration/      # Run integration tests
make lint                      # Ruff lint
make typecheck                 # Pyright
```

## Code Style

- Follow existing project conventions (Python typing, Pydantic v2, SQLAlchemy 2.0)
- Provider interfaces: abstract base classes with `provider_name`, `provider_version`, `provider_capabilities`
- Contract tests: one test class per provider interface, pytest fixture for implementation
- No Rust dependencies; tree-sitter via Python bindings only
- No Atlas imports; Atlas must depend on Knowhere, not reverse

## Recent Changes

- **KNOW-001 Foundation Architecture** (current): 10-layer architecture, 10 provider interfaces, 47 FRs, 38 SCs, deterministic retrieval, KnowledgeChunk model, Storage as source of truth

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
