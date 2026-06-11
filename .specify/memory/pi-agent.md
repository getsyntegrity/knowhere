# knowhere Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-06-11

## Active Technologies

### From KNOW-001 Foundation Architecture (current)

### From KNOW-002 Canonical Knowledge Model (planning)

- **Pydantic v2** — Entity definitions (frozen BaseModel with field validation)
- **hashlib (stdlib)** — Deterministic identifier generation (SHA-256, PERMANENT contract)
- **abc (stdlib)** — Abstract adapter and factory contracts
- **uuid (stdlib)** — Non-deterministic Snapshot identifiers

### Know-002 scope

- **In scope**: 7 entities, CodeLocation, IdentifierService (permanent SHA-256), CanonicalFactory, JsonSerializer, CanonicalRepository (query), adapter contract tests
- **Out of scope (deferred)**: Persistence (SQLAlchemy, Postgres), Snapshot lifecycle (create/verify/restore/rollback) → KNOW-004

### Canonical Entities (7)

- `Repository` — Sole aggregate root
- `File` — Source file within a repository
- `Symbol` — Named code/document symbol (function, class, variable)
- `Chunk` — Contiguous text span with composite ID (repo + file + location)
- `Relationship` — Typed edge between any two entities
- `Reference` — Occurrence-based pointer with location context
- `Snapshot` — Sealed, timestamped repository state (lifecycle deferred to KNOW-004)

### Key Distinction: chunk_id vs semantic_hash

- `chunk_id` = `sha256(repository_id + "|" + file_id + "|" + location)` — unique within Repository
- `semantic_hash` = `sha256(text_bytes)` — cross-provider dedup and semantic equivalence

### Package Location

- `packages/canonical-knowledge/` — new library package (separate from shared-python to enforce Constraint 2)

### Provider Adapter Contracts (abstract)

- `FileAdapter` — Provider-specific file → canonical File
- `SymbolAdapter` — Provider-specific symbol → canonical Symbol
- `ChunkAdapter` — Provider-specific chunk → canonical Chunk
- `RelationshipAdapter` — Provider-specific edge → canonical Relationship

### CanonicalRepository (Query & Navigation)

- In-memory, backend-agnostic query interface
- Retrieval: `get_file(id)`, `get_symbol(id)`, `get_chunk(id)`, etc.
- Discovery: `find_symbols(file_id)`, `find_chunks(file_id)`, `find_relationships(source_id)`, etc.
- Repository scope: `get_file_by_path(repo, path)`, `get_symbol_by_name(repo, qualified_name)`

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
- **KNOW-002 Canonical Knowledge Model** (planning): 7 canonical entities (Repository, File, Symbol, Chunk, Relationship, Reference, Snapshot), CodeLocation value object, CanonicalFactory with deterministic identifiers (SHA-256, permanent contract), CanonicalRepository query interface, JsonSerializer with version markers, 4 adapter contracts (FileAdapter, SymbolAdapter, ChunkAdapter, RelationshipAdapter). ACL pattern between upstream providers and Syntegrity consumers. Package: `packages/canonical-knowledge/`. Persistence and Snapshot lifecycle deferred to KNOW-004. 32 FRs, 21 ACs (AC-007–009 deferred), 5 SCs (SC-003 deferred).

### Key KNOW-002 Decisions
- **Chunk identity** = repository_id + file_id + location; `semantic_hash` = text-only content hash
- **Repository** is the sole aggregate root
- **CodeLocation** value object shared across Symbol, Chunk, Reference
- **source_uri** replaces origin_uri for multi-provider neutrality
- **KnowledgeAsset** reserved for future non-code assets
- **Identifier permanence** — identifier generation is part of the public contract and MUST NOT change after release. `Repository.id`, `File.id`, `Symbol.id`, `Chunk.id`, `Relationship.id`, `Reference.id` are permanent. Snapshot identifiers excluded (non-deterministic).
- **No persistence in KNOW-002** — SQLAlchemy, PostgreSQL, and all storage backends deferred to KNOW-004
- **No snapshot lifecycle in KNOW-002** — create/verify/restore/rollback deferred to KNOW-004
- **CanonicalRepository** — in-memory query/navigation interface added (replaces persistence repository)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
