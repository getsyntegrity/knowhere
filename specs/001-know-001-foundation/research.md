# Research: KNOW-001 Foundation Architecture

**Date**: 2026-06-11 | **Spec**: [spec.md](./spec.md)

## Overview

This document consolidates all architectural decisions made during the specification and clarification phases for KNOW-001 Foundation Architecture. No new research was needed — the spec emerged fully clarified after 3 clarification passes (19 decisions) and 1 refinement pass (8 FIX items), with 0 [NEEDS CLARIFICATION] markers remaining.

## Clarification Decisions

### GAP-001: Knowledge Source Model

- **Decision**: Root entity `KnowledgeSource` with derivations (Repository, Document, Dataset, Image, Memory)
- **Rationale**: Atlas will process much more than code; a unified root entity enables uniform handling
- **Alternatives considered**: Direct derivation per type without root (rejected — would require type-specific code in every layer)

### GAP-002: Ingestion Layer

- **Decision**: New formal Ingestion Layer between API and Storage, extensible for any source from the start
- **Rationale**: Decouple knowledge acquisition from all downstream layers
- **Alternatives considered**: Ingestion as module responsibility (rejected — coupling violation), Postpone (rejected — blocks all downstream work)

### GAP-003: Knowledge Graph

- **Decision**: First-class component with its own layer, representing all indexed knowledge
- **Rationale**: Code-only graph would miss cross-domain relationships; full-knowledge graph enables richer retrieval
- **Alternatives considered**: Optional backend (rejected — too weak), code-only (rejected — misses cross-domain value)

### GAP-004: Ranking Layer

- **Decision**: Separate Ranking Layer between Retrieval and Compression, modeling 4 strategies
- **Rationale**: Ranking has distinct concerns (scoring, fusion) that shouldn't be coupled to search
- **Alternatives considered**: Ranking inside Retrieval (rejected — coupling), only if multiple strategies (rejected — predictably needed)

### GAP-005: Context Assembly

- **Decision**: Explicit Context Builder layer with ordering, prioritization, deduplication, token budget
- **Rationale**: Compression output needs final shaping before reaching LLM
- **Alternatives considered**: Compression returns prompt directly (rejected — no budget enforcement)

### GAP-006: Token Reduction Objective

- **Decision**: Configurable per workload; balanced tradeoff between quality, latency, and reduction
- **Rationale**: Different use cases have different priorities (speed vs. quality vs. cost)
- **Alternatives considered**: Hard 70-90% requirement (rejected — too rigid for diverse workloads)

### GAP-007: Deterministic Retrieval

- **Decision**: Full chain audit (query → retrieval → ranking → compression → context), per knowledge version
- **Rationale**: Atlas needs full reproducibility and traceability for audit
- **Alternatives considered**: Partial audit (rejected — insufficient for replay), per-execution determinism (rejected — impractical)

### Clarify 14-18: Architecture Refinements

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Knowledge Version Definition | Complete atomic index snapshot | Enables full Atlas reproducibility |
| Graph vs Vector Source of Truth | Storage is truth, Graph/Vector derived | Enables rebuild, prevents data loss |
| Code Parsing Strategy | Language-specific `CodeParserProvider` | Supports future languages without core changes |
| Retrieval Strategy Model | Configurable pipeline | Most flexible — not rigid single retriever, not complex planner |
| Compression Quality Metrics | Recall + Precision + Faithfulness | Beyond token reduction, measures actual quality |

## Technology Decisions

| Technology | Decision | Rationale |
|------------|----------|-----------|
| Language | Python 3.11+ | Project standard, AI ecosystem, upstream compatibility |
| ORM | SQLAlchemy 2.0 | Existing project standard |
| Validation | Pydantic v2 | Existing project standard for schemas |
| Vector DB (prod) | Qdrant | Existing infrastructure |
| Vector DB (test) | In-memory mock | Lightweight, no external dependency |
| Graph DB (initial) | PgVector | Existing infrastructure; Neo4j deferred |
| Code Parsing | tree-sitter (Python bindings) | Multi-language, deterministic, no Rust runtime |
| Task Queue | Celery | Existing infrastructure |
| Testing | pytest | Existing project standard |
| API Framework | FastAPI | Existing project standard |
| Provider Registration | YAML config + env vars | Simple, no runtime plugin loader needed initially |

## Architectural Patterns

### Layer Dependency Direction

```
Applications → API → Ingestion → [KnowledgeGraph | Memory | CodeMemory] → Retrieval → Ranking → Compression → ContextBuilder → Storage
```

Each layer depends only on layers below it. No upward or circular dependencies.

### Provider Model

Every provider:
1. Inherits from an abstract base class defining the interface contract
2. Exposes `provider_name`, `provider_version`, `provider_capabilities` (structured: name, version, stability)
3. Is registered via configuration, not hard-coded imports
4. Is independently testable via contract tests
5. Records its version in the audit log for every operation

### Source of Truth Hierarchy

```
Storage (authoritative, canonical records)
    ├── KnowledgeSource entities (ingested origins)
    ├── KnowledgeChunk entities (atomic retrieval units)
    ├── KnowledgeVersion entities (sealed snapshots)
    ├── Memory/MemoryFact/MemoryRelationship/MemorySummary
    ├── Repository/File/Symbol/Dependency/Reference
    └── ...
VectorStore (derived index — rebuildable from Storage)
    └── KnowledgeChunk embeddings, indexed for similarity search
GraphStore (derived index — rebuildable from Storage)
    └── GraphNode/GraphEdge relationships, indexed for traversal
```

### Knowledge Version Lifecycle

```
Ingestion → New KnowledgeVersion (status: sealing)
    ↓
Indexing complete → KnowledgeVersion sealed (status: sealed, checksum computed)
    ↓
Query executes against sealed version → deterministically equivalent results
    ↓
New ingestion → New KnowledgeVersion (parent_version: previous)
    ↓
Rollback → Activate previous KnowledgeVersion
```

## Design Constraints

1. All Syntegrity extensions live outside upstream core files (FR-046)
2. No Atlas package may be imported by Knowhere (SC-NF08)
3. No Rust toolchain required (SC-NF07)
4. Provider interfaces must not conflict with upstream interfaces (FR-047)
5. Storage is authoritative; all indices are rebuildable (FR-009)
6. Compression is configurable per workload, not globally fixed (FR-039)
7. Provider fallback is opt-in per provider category (FR-029)
8. KnowledgeVersion MAY use incremental snapshots internally (OBS-001)
