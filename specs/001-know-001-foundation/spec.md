# Feature Specification: KNOW-001 Foundation Architecture

**Feature Branch**: `001-know-001-foundation`
**Created**: 2026-06-11
**Status**: Draft | **Last Clarified**: 2026-06-11
**Input**: User description: "Establecer la arquitectura fundacional de Knowhere para soportar: Compatibilidad permanente con upstream, Extensiones propias de Syntegrity, Memoria semántica, Memoria de código, Reducción de contexto (70–90%), Determinismo para futuras capacidades de Atlas, Múltiples backends vectoriales, Evolución incremental sin forks destructivos."

## Clarifications

### Session 2026-06-11

- **Q1 (GAP-001 Knowledge Source Model)**: What is the foundational entity model for knowledge sources? → **A**: Introduce a root entity `KnowledgeSource` from which `Repository`, `Document`, `Dataset`, `Image`, and `Memory` derive (Option A).
- **Q2 (GAP-002 Ingestion Layer)**: Should a formal Ingestion Layer exist? → **A**: Yes, as a new layer between API and Storage, with extensible architecture for any source from the start — Git, filesystem, documents (PDF, Markdown, DOCX), and future sources (Option A + D).
- **Q3 (GAP-003 Knowledge Graph)**: What role should the graph have? → **A**: First-class component with its own Graph Layer, representing all indexed knowledge — code relationships, memories, and any knowledge entity (Option B + C).
- **Q4 (GAP-004 Ranking Layer)**: Should ranking be separated from retrieval? → **A**: Yes, as a new Ranking Layer between Retrieval and Compression, modeling Similarity + BM25 + Hybrid + Reranking strategies from the architecture (do not implement all, only model) (Option A + D).
- **Q5 (GAP-005 Context Assembly)**: Should an explicit Context Builder exist after Compression? → **A**: Yes, with responsibilities: order, prioritize, deduplicate, and apply token budget (Option A + D).
- **Q6 (GAP-006 Token Reduction Objective)**: Is the 70–90% reduction a hard requirement? → **A**: Metric is configurable per workload; the system shall support a balanced, configurable tradeoff between quality, latency, and reduction (Option C + D).
- **Q7 (GAP-007 Deterministic Retrieval)**: What must be reconstructable for audit? → **A**: Full chain — query + retrieval + ranking + compression + context final — with determinism scoped per knowledge version (Option D + C).
- **Q8 (Clarify 14 — Knowledge Version Definition)**: What is a "knowledge version"? → **A**: A complete snapshot of the entire index — all ingested knowledge at a point in time, versioned atomically (Option C). Enables full reproducibility for Atlas.
- **Q9 (Clarify 15 — Graph vs Vector Source of Truth)**: Who is the source of truth among Graph, Vector Store, and Storage? → **A**: Storage is the authoritative source of truth; Graph and Vector are derived indices computed from Storage (Option C).
- **Q10 (Clarify 16 — Code Parsing Strategy)**: How are code entities (Repository, File, Symbol, Dependency, Reference) extracted? → **A**: Language-specific parsing providers — a `CodeParserProvider` per language (Option C). Supports Rust, Go, Python, Java, TypeScript, and future languages.
- **Q11 (Clarify 17 — Retrieval Strategy Model)**: What architectural model for retrieval (Vector + Graph + Keyword)? → **A**: Configurable pipeline — not a single retriever and not a planner — a composed pipeline where strategies are selected and ordered per workload (Option B).
- **Q12 (Clarify 18 — Compression Quality Metrics)**: What quality metrics should complement token reduction? → **A**: Recall + Precision + Faithfulness — three complementary metrics beyond raw token reduction (Option D).
- **Q19 (KnowledgeChunk Model — user-identified gap)**: The entity model lacks a `Chunk` or `KnowledgeFragment` — yet all retrieval operates on fragments, not whole sources. → **A**: Introduce `KnowledgeChunk` as the atomic retrieval unit: `chunk_id`, `source_id`, `knowledge_version`, `content`, `embedding`, `metadata`. Chunks are produced by Ingestion (from documents, code files, memories), stored in VectorStore, returned by Retrieval, selected by Ranking, compressed by Compression, and assembled by Context Builder.

## Summary

Establish the foundational architecture of Knowhere that enables clean separation of concerns through a multi-layer module architecture with abstract provider interfaces. The architecture introduces: a unified Ingestion Layer with a `KnowledgeSource` root entity for any knowledge type; `KnowledgeChunk` as the atomic retrieval unit (produced by ingestion, indexed in vector/graph stores, retrieved, ranked, compressed, and assembled by Context Builder); a Knowledge Graph Layer as a first-class component; a separate Ranking Layer between Retrieval and Compression; a Context Builder Layer that assembles final output with token budget enforcement; a configurable Retrieval Pipeline model (vector + graph + keyword); language-specific `CodeParserProvider` for code memory; and quality metrics (Recall + Precision + Faithfulness) for compression evaluation. Storage is the authoritative source of truth; Graph and Vector are derived indices. Determinism is scoped per complete index snapshot (knowledge version). This foundation supports future Atlas capabilities, semantic and code memory, configurable context compression, deterministic retrieval, and multiple vector backends — all while maintaining permanent upstream compatibility through plugin-based extension points rather than destructive forks.

**Architecture decision**: `KnowledgeSource` represents **origin**. `KnowledgeChunk` represents the **retrieval unit**. `KnowledgeVersion` represents the **reproducibility boundary**. `Storage` represents the **source of truth**. `GraphStore` and `VectorStore` represent **derived indices** — computed views rebuildable from Storage. All layers, providers, and operations serve these fundamental distinctions.

---

## Architectural Principles

### 1. Upstream First
Every change must:
- Avoid modifying core upstream code when possible.
- Implement via plugins, adapters, or extension points.
- Permit periodic merge from upstream.
- **Rule**: If a feature can live outside the core, it must live outside the core.

### 2. Python Remains Primary Runtime
Knowhere continues as Python. No Rust migration. Rationale: maximize upstream compatibility, leverage the AI ecosystem, lower maintenance cost, and increase community adoption. Rust may appear later only as an external service, a worker, or an optional FFI library — never as a requirement.

### 3. Clean Layer Separation

```
                Applications (Atlas / IDE / Agents)
                         │
                    Knowhere API
                         │
                    Ingestion Layer
                         │
            ┌────────────┼────────────┐
            │            │            │
       Knowledge     Memory       Code Memory
      Graph Layer     Layer         Layer
            │            │            │
            └────────────┼────────────┘
                         │
                  Retrieval Layer
                         │
                   Ranking Layer
                         │
                  Compression Layer
                         │
                Context Builder Layer
                         │
               Storage Abstractions
            ┌────────────┼────────────┐
            │            │            │
          Qdrant      PgVector     Future
```

**Layer flow (retrieval pipeline)**:

```
Ingestion → Storage → Retrieval → Ranking → Compression → Context Builder
```

---

## Module Architecture

### Core Layer
**Responsibility**: entities, embeddings, retrieval, storage abstraction
**Contains**: entity definitions (including `KnowledgeChunk` as the atomic retrieval unit), embedding interfaces, base retrieval contracts, abstract storage interfaces
**Does NOT contain**: Atlas logic, IDE logic, business logic

### Ingestion Layer (NEW)
**Responsibility**: knowledge source ingestion — accepting content from any source type, normalizing it into the unified `KnowledgeSource` model, producing `KnowledgeChunk` units, and persisting through storage abstractions
**Entities**: `KnowledgeSource` (root entity — see Key Entities), `KnowledgeChunk` (atomic retrieval unit), `IngestionPipeline`, `IngestionJob`
**Interfaces**: `SourceProvider` (pluggable per source type), `ChunkingStrategy` (pluggable chunking per source type)
**Source types**: Git repositories, local filesystem, documents (PDF, Markdown, DOCX), datasets, images — extensible for any future source
**Purpose**: Decouple knowledge acquisition from all downstream layers; single entry point that feeds Memory, Code Memory, and Knowledge Graph layers with chunked, indexed content

### Knowledge Graph Layer (NEW)
**Responsibility**: graph representation of all indexed knowledge — entities, their attributes, and typed relationships across domains
**Entities**: `GraphNode`, `GraphEdge`, `GraphRelationship`
**Interfaces**: `GraphProvider` (delegates to configurable backend)
**Scope**: Represents all indexed knowledge — code relationships, semantic memories, documents, and cross-domain connections
**Purpose**: First-class graph abstraction enabling graph traversal queries, relationship discovery, and structural retrieval

### Memory Layer
**Responsibility**: semantic memories, facts, summaries, relationships
**Entities**: `Memory`, `MemoryFact`, `MemoryRelationship`, `MemorySummary`

### Code Memory Layer (NEW)
**Responsibility**: source files, symbols, dependencies, repositories
**Entities**: `Repository`, `File`, `Symbol`, `Dependency`, `Reference`
**Parsing**: Language-specific `CodeParserProvider` — each language (Python, TypeScript, Rust, Go, Java) has its own parsing provider implementing the common interface
**Interfaces**: `CodeParserProvider` (parse file, extract symbols, resolve dependencies, find references)
**Purpose**: Foundation for Atlas code awareness, context reduction, and semantic code navigation

### Retrieval Layer
**Responsibility**: hybrid search, semantic retrieval, graph retrieval, keyword search over `KnowledgeChunk` units
**Interfaces**: `Retriever`, `CodeRetriever`, `MemoryRetriever`, `HybridRetriever`
**Model**: Configurable pipeline (`RetrievalPipeline` entity) — not a single retriever, not a planner — a composed pipeline supporting vector search, graph traversal, and keyword (BM25) strategies, ordered and selected per workload
**Pipeline composition**: Strategies (vector, graph, keyword) are combinable as a pipeline definition (`RetrievalPipeline.pipeline_id`); each workload selects its strategy composition, ordering, and fusion method
**Return type**: All retrieval operations return references to `KnowledgeChunk` objects — not whole sources, not raw text — enabling unified handling regardless of source type

### Ranking Layer (NEW)
**Responsibility**: rank candidates produced by Retrieval before passing to Compression
**Interfaces**: `RankingStrategy`
**Strategies (modeled, not all implemented)**: similarity scoring, BM25 lexical scoring, hybrid fusion (RRF), reranking via learned model
**Purpose**: Separate ranking from retrieval so new ranking strategies can be added without modifying retrieval logic

### Compression Layer (Strategic)
**Responsibility**: reduce context before reaching the LLM
**Objective**: configurable per workload (baseline target 70–90%)
**Techniques**: semantic chunk selection, repository summaries, symbol summaries, hierarchical retrieval
**Balancing**: configurable tradeoff between quality, latency, and reduction (per workload)
**Quality Metrics**: compression quality is measured by three complementary metrics beyond token count:
- **Recall**: what fraction of relevant information from the original context is preserved in the compressed output
- **Precision**: what fraction of the compressed output is relevant to the query
- **Faithfulness**: the compressed output does not introduce information not present in the original context (hallucination prevention)

### Context Builder Layer (NEW)
**Responsibility**: assemble the final prompt-ready context from compressed `KnowledgeChunk` fragments
**Interfaces**: `ContextBuilder`
**Responsibilities**: order fragments by relevance, prioritize critical content, deduplicate overlapping passages, apply token budget constraints
**Purpose**: Ensures the final context passed to the LLM is structured, within budget, and maximally informative

### Storage Layer
**Responsibility**: all persistent access through abstract interfaces, including indexing and querying of `KnowledgeChunk` objects
**Interfaces**: `MemoryStore`, `VectorStore`, `GraphStore`
**Implementations**: Qdrant, PgVector, Neo4j (future)
**Chunk Indexing**: `KnowledgeChunk` objects are the primary unit persisted in VectorStore (for similarity search) and referenced in GraphStore (for relationship traversal)
**Source of Truth**: Storage is the authoritative source of truth for all data. Vector stores and graph stores are **derived indices** — computed views that can be rebuilt from Storage. Storage must never be reconstructed from Vector or Graph.

```
Storage (authoritative)
   ├── VectorStore (derived index over KnowledgeChunk embeddings)
   ├── GraphStore (derived index over KnowledgeChunk relationships)
   └── KnowledgeSource + KnowledgeChunk entities (canonical records)
```

---

## Extensibility Provider Model

Every subsystem is abstracted behind an interchangeable provider:

| Provider | Purpose |
|----------|---------|
| `SourceProvider` | Knowledge source ingestion (Git, filesystem, documents, images) |
| `ChunkingStrategy` | Pluggable chunking strategy per source type — splits `KnowledgeSource` content into `KnowledgeChunk` units |
| `CodeParserProvider` | Language-specific code parsing — one per language (Python, TypeScript, Rust, Go, Java) |
| `EmbeddingProvider` | Text-to-vector embedding |
| `VectorProvider` | Vector storage and similarity search over `KnowledgeChunk` embeddings |
| `GraphProvider` | Graph storage and traversal (nodes/edges reference `KnowledgeChunk` and `KnowledgeSource`) |
| `RankingStrategy` | Candidate ranking (similarity, BM25, hybrid, reranking) |
| `CompressionProvider` | Context compression strategies over `KnowledgeChunk` candidates |
| `ContextBuilder` | Final context assembly (ordering, dedup, token budget) from compressed `KnowledgeChunk` fragments |
| `StorageProvider` | Persistent entity storage for `KnowledgeSource`, `KnowledgeChunk`, and all other entities |

Each provider is independently swappable via configuration, enabling multiple backends without core changes. Every provider MUST expose `provider_name`, `provider_version`, and `provider_capabilities` for deterministic replay, debugging, and compatibility validation.

---

## Observability

Minimum mandatory metrics for every layer and provider:

- **Latency**: per-operation timing (p50, p95, p99)
- **Retrieval count**: number of retrieval operations per query
- **Compression ratio**: input tokens vs. output tokens after compression
- **Embedding cost**: tokens consumed by embedding models
- **Token reduction**: absolute and percentage token savings from compression

### Compression Quality Metrics

Compression quality is measured by three metrics that complement token reduction:

- **Recall**: What fraction of relevant information from the original context is preserved in the compressed output
- **Precision**: What fraction of the compressed output is relevant to the query
- **Faithfulness**: The compressed output does not introduce hallucinated information — all facts in the output are present in the original context

These metrics are evaluated on a benchmark suite, not per-query in production. Token reduction is the primary runtime metric; Recall, Precision, and Faithfulness are validated during compression strategy evaluation and regression testing.

---

## Determinism

Foundation for future Atlas capabilities. Every retrieval must be:

- **Traceable**: able to reconstruct the full retrieval path
- **Reproducible**: same query + same knowledge version produces identical results
- **Auditable**: each response can reconstruct: query → knowledge version → documents selected → ranking strategy and scores → compression strategy and decisions → context builder assembly → final context

Determinism is scoped **per knowledge version** (`KnowledgeVersion` entity) — a complete, atomic snapshot of the entire index at a point in time. A knowledge version captures:
- All ingested `KnowledgeSource` entities and their derivations (documents, code, memories, graph nodes)
- All embedding vectors and vector index state
- All graph nodes and edges
- All chunk metadata and content

Changes to knowledge (new ingestion, re-indexing, deletion) create a new version. Within a version, all queries are fully reproducible and produce deterministically equivalent results given identical query parameters.

This means all provider calls, ranking decisions, compression operations, and context building steps must be logged with sufficient context for full replay across the entire pipeline.


**Implementation note**: Implementations MAY use incremental snapshots internally, provided that replay semantics remain equivalent to a full atomic snapshot. This prevents forcing a full index dump for every version in large-scale deployments (e.g., 1M LOC, 10M chunks).

**Storage is the authoritative source of truth. Vector indices and graph indices are derived views computed from Storage. If a vector index is corrupted or a graph index is stale, they can be rebuilt from Storage. Storage must never be reconstructed from Graph or Vector.

---

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Vendor Adds a New Vector Database Backend (Priority: P1)

A platform engineer needs to add support for a new vector database (e.g., Weaviate, Pinecone, Milvus) without modifying any core retrieval or storage logic. They implement the `VectorProvider` interface for the new database, register it via configuration, and all existing retrieval features work unchanged.

**Why this priority**: This is the core value proposition of the foundation architecture — enabling extensibility without forks. All other capabilities depend on this abstraction layer being correct.

**Independent Test**: Can be fully tested by implementing a mock VectorProvider, switching configuration to use it, and verifying that all retrieval operations produce correct results through the provider boundary.

**Acceptance Scenarios**:

1. **Given** a new VectorProvider implementation that conforms to the provider interface, **When** the system configuration is updated to use this provider, **Then** all retrieval operations complete successfully using the new backend.
2. **Given** a VectorProvider that returns known results, **When** a retrieval query is executed through the `Retriever` interface, **Then** the results match the expected provider output without any backend-specific code in the retrieval layer.
3. **Given** an upstream release with new retrieval features, **When** the upstream code is merged, **Then** no conflicts arise because the provider abstraction layer is part of the extension system, not a fork.

---

### User Story 2 - Developer Integrates Code Memory for a Large Repository (Priority: P1)

An Atlas developer needs to index a repository with over 1M lines of code and run context-reduced queries against it. They use the Code Memory Layer to ingest source files, extract symbols and dependencies, and then query through the `CodeRetriever` interface — obtaining compressed context that fits within LLM token limits.

**Why this priority**: Code Memory is a new layer that enables Atlas capabilities and meets the 70–90% context reduction target. Without it, the system cannot support large-repository use cases.

**Independent Test**: Can be tested independently by ingesting a known repository, running a query through CodeRetriever, and verifying that the returned context is a valid subset of the full repository content.

**Acceptance Scenarios**:

1. **Given** a repository with 100K+ lines of code ingested into Code Memory, **When** a developer queries for specific symbols or files, **Then** results include the relevant symbols, their definitions, and their dependencies.
2. **Given** a repository with over 1M LOC, **When** a retrieval query is made, **Then** the compressed context returned consumes at most 30% of the tokens that the raw files would require.
3. **Given** Code Memory contains multiple repositories, **When** a cross-repository symbol query is executed, **Then** results include references across repository boundaries.

---

### User Story 3 - Platform Team Adds Context Compression Strategy (Priority: P2)

The platform team wants to implement a new compression strategy (e.g., hierarchical summarization with section pruning). They implement the `CompressionProvider` interface, register it, and existing retrieval pipelines automatically apply the new strategy without changes to query logic.

**Why this priority**: The Compression Layer is strategically important for delivering the 70–90% reduction target but can be developed after the core abstraction layer is proven with a baseline compression strategy.

**Independent Test**: Can be tested by implementing a simple truncation-based CompressionProvider, then verifying that compressed contexts are shorter and still contain relevant information for the original query.

**Acceptance Scenarios**:

1. **Given** a query with a large result set, **When** the CompressionProvider is applied, **Then** the output context is measurably 70–90% smaller than the raw input.
2. **Given** a CompressionProvider implementation, **When** compression is enabled, **Then** retrieval latency increases by no more than 20% compared to uncompressed retrieval.

---

### User Story 4 - Developer Verifies Deterministic Retrieval (Priority: P2)

A quality engineer needs to verify that a retrieval pipeline is deterministic for auditing and reproducibility. They run the same query twice against the same data, and both runs produce identical results with a full audit trail.

**Why this priority**: Determinism is foundational for future Atlas capabilities but can be layered on after the primary abstraction and provider interfaces are stable.

**Independent Test**: Can be tested by running a query twice with the same parameters and data, then comparing the full result set and audit log for identity.

**Acceptance Scenarios**:

1. **Given** a fixed dataset and a fixed query, **When** the query is executed twice, **Then** both runs return identical ranked results with identical compression output.
2. **Given** a retrieval operation, **When** the audit log is inspected, **Then** it contains the full chain: original query → candidate documents → ranking scores → compression decisions → final context.

---

### User Story 5 - Core Team Merges Upstream Release (Priority: P3)

The core team needs to merge a new upstream release with changes to the retrieval engine. Because all Syntegrity extensions live outside core files (in provider implementations and adapter layers), the merge is clean with no conflicts in core modules.

**Why this priority**: Upstream compatibility is a guiding principle but the value is realized over time, not in a single feature delivery.

**Independent Test**: Can be tested by simulating an upstream merge in a CI environment and verifying zero conflicts in core files.

**Acceptance Scenarios**:

1. **Given** an upstream release with changes to core retrieval logic, **When** the merge is attempted, **Then** the only conflicts (if any) are in the Syntegrity-specific abstraction wrappers, not in core files.

---

### Edge Cases

- **Missing provider implementation**: What happens when a configured provider has no registered implementation? System must fail gracefully with a clear configuration error and guidance on how to register the provider.
- **Provider fallback by category**: What happens when a primary backend is unavailable? System should support configurable fallback chains (primary → secondary → error) only for provider categories where fallback is appropriate (e.g., `EmbeddingProvider`, `VectorProvider`) — categories like `StorageProvider` should fail fast.
- **Mixed provider configurations**: What happens when different providers are configured for different data types (e.g., Qdrant for documents, PgVector for code memory)? System must support per-layer provider configuration.
- **Incomplete audit log**: What happens when a provider in the chain does not support full audit logging? System must define minimum audit requirements and handle missing audit data gracefully.
- **Compression over-application**: What happens when compression reduces context below a useful minimum? Compression must have configurable minimum context size guards and per-workload configurable targets.
- **Cross-layer dependency cycles**: What happens if Code Memory depends on Retrieval and Retrieval depends on Code Memory? Architecture must enforce acyclic layer dependencies.
- **Large-scale ingestion failure**: What happens when indexing a 1M+ LOC repository fails partway through? Ingestion must support checkpoint/resume.
- **Knowledge version conflict**: What happens when a query runs while a new knowledge version is being indexed? System must support atomic version activation; in-flight queries complete against the old version.
- **Unsupported source type**: What happens when a user submits a knowledge source type with no registered `SourceProvider`? System must reject with a clear error and list available source types.
- **Empty ingestion result**: What happens when an `IngestionPipeline` produces zero entities? System must handle gracefully — log a warning, report in `IngestionJob` status, and not break downstream layers.
- **Context Builder token budget conflict**: What happens when the token budget is so small that no fragment fits? Context Builder must have a minimum output floor and report a budget warning.
- **Ranking strategy fallback**: What happens when a configured `RankingStrategy` fails at runtime? System should fall back to a default strategy (e.g., similarity-only) and log the failure.
- **Storage vs derived index inconsistency**: What happens when a VectorStore or GraphStore becomes inconsistent with Storage (e.g., after partial re-indexing)? The system must support a rebuild operation that reconstructs derived indices from authoritative Storage.
- **Unsupported language in Code Memory**: What happens when a repository contains a language with no registered `CodeParserProvider`? System should skip those files with a warning, continue parsing supported languages, and report the skipped languages.
- **Parser provider version skew**: What happens when a `CodeParserProvider` update produces different symbols than the previous version for the same file? Parsing results must be versioned with the provider version to ensure traceability.
- **Knowledge version corruption**: What happens when a knowledge version snapshot is corrupted? System must support version integrity checks (hash verification) and allow rollback to the previous uncorrupted version.
- **Pipeline strategy selection conflict**: What happens when a workload requests a retrieval pipeline composition that has no valid configuration (e.g., vector-only but no VectorProvider configured)? System must reject with a clear configuration validation error before query execution.
- **Chunk with missing embedding**: What happens when a `KnowledgeChunk` lacks an embedding (e.g., chunking before embedding provider is configured)? System must detect missing embeddings at publish time and either compute them or reject the chunk with a clear error.

---

## Requirements _(mandatory)_

### Functional Requirements

#### Module Architecture

- **FR-001**: System MUST define a Core Layer with abstract interfaces for entities, embeddings, retrieval, and storage — containing no application-specific logic.
- **FR-002**: System MUST define a Memory Layer with entities for `Memory`, `MemoryFact`, `MemoryRelationship`, and `MemorySummary`.
- **FR-003**: System MUST define a Code Memory Layer with entities for `Repository`, `File`, `Symbol`, `Dependency`, and `Reference`.
- **FR-004**: System MUST define a `CodeParserProvider` interface per supported programming language for extracting symbols, dependencies, and references from source code.
- **FR-005**: System MUST define a Retrieval Layer with interfaces `Retriever`, `CodeRetriever`, `MemoryRetriever`, and `HybridRetriever`.
- **FR-006**: Retrieval MUST support a configurable pipeline model combining vector search, graph traversal, and keyword (BM25) strategies, with per-workload strategy selection and ordering.
- **FR-007**: System MUST define a Compression Layer with an abstract `CompressionProvider` interface supporting pluggable compression strategies.
- **FR-008**: System MUST define a Storage Layer with abstract interfaces `MemoryStore`, `VectorStore`, and `GraphStore`.
- **FR-009**: Storage MUST be the authoritative source of truth; VectorStore and GraphStore are derived indices rebuildable from Storage.
- **FR-010**: System MUST define a Ranking Layer with a `RankingStrategy` interface between Retrieval and Compression, covering similarity, BM25, hybrid fusion, and reranking strategies.
- **FR-011**: System MUST define a Context Builder Layer with a `ContextBuilder` interface that assembles final context by ordering, prioritizing, deduplicating, and applying token budget constraints.
- **FR-012**: All layers MUST be organized such that dependencies flow downward only (no upward or circular cross-layer dependencies).
- **FR-013**: A knowledge version MUST be a complete atomic snapshot of the entire index — all KnowledgeSource entities, vector indices, graph nodes/edges, and chunk metadata at a point in time.
- **FR-014**: The system MUST define a `KnowledgeChunk` entity as the atomic retrieval unit with fields: `chunk_id` (deterministic content hash), `source_id`, `knowledge_version`, `chunk_type` (from the ChunkType enum), `content`, `embedding`, `parent_chunk_id` (optional), `root_chunk_id` (optional), and `metadata` including provenance (`source_type`, `source_path`, `source_reference`, `ingestion_timestamp`, `provider_version`).
- **FR-015**: All retrieval operations across all layers MUST operate on `KnowledgeChunk` objects — not on raw KnowledgeSource representations.

#### Provider Model

- **FR-016**: System MUST define a `SourceProvider` interface that abstracts ingestion from any knowledge source type (Git, filesystem, documents, images).
- **FR-017**: System MUST define a `CodeParserProvider` interface per supported programming language (Python, TypeScript, Rust, Go, Java) for extracting symbols, dependencies, and references from source code.
- **FR-018**: System MUST define a `VectorProvider` interface that abstracts vector storage and similarity search operations.
- **FR-019**: System MUST define an `EmbeddingProvider` interface that abstracts text-to-vector operations.
- **FR-020**: System MUST define a `GraphProvider` interface that abstracts graph storage and traversal operations.
- **FR-021**: System MUST define a `RankingStrategy` interface that abstracts candidate ranking methods (similarity, BM25, hybrid, reranking).
- **FR-022**: System MUST define a `CompressionProvider` interface that abstracts context compression strategies.
- **FR-023**: System MUST define a `ContextBuilder` interface that abstracts final context assembly (ordering, dedup, prioritization, token budget).
- **FR-024**: System MUST define a `StorageProvider` interface that abstracts persistent entity storage.
- **FR-025**: Providers MUST be configurable and swappable without modifying core code — via configuration files or environment-based registration.
- **FR-026**: System MUST support per-layer provider configuration (e.g., different vector stores for different data types).

#### Extensibility

- **FR-027**: All Syntegrity-specific extensions MUST live outside upstream core files.
- **FR-028**: System MUST support plugin-based discovery of provider implementations (including `SourceProvider`, `RankingStrategy`, `ContextBuilder`, and all other providers).
- **FR-029**: System MUST support configurable provider fallback, where fallback behavior is defined per provider category (e.g., `EmbeddingProvider` may fallback, `StorageProvider` may not). Fallback chains (primary → secondary → error) MUST be opt-in per provider type, not universal.

#### Observability

- **FR-030**: Every provider MUST expose per-operation latency metrics (p50, p95, p99).
- **FR-031**: Every retrieval operation MUST report total retrieval count.
- **FR-032**: Every compression operation MUST report compression ratio (input tokens / output tokens).
- **FR-033**: Every embedding operation MUST report token consumption.
- **FR-034**: The system MUST expose a configurable balance between quality, latency, and token reduction — adjustable per workload via configuration.
- **FR-035**: System MUST expose a unified metrics interface that aggregates observability data from all layers and providers.

#### Determinism

- **FR-036**: Every retrieval operation MUST produce an audit log that includes the full chain: original query, candidate documents selected, ranking strategy and scores, compression strategy and decisions, context builder assembly, and final context.
- **FR-037**: Given the same knowledge version and the same query, the system MUST produce identical results across repeated executions (determinism scoped per knowledge version).
- **FR-038**: Each decision point in the retrieval pipeline MUST record its input state to enable full reconstruction of the retrieval path.

#### Context Compression

- **FR-039**: The Compression Layer MUST support at least one baseline compression strategy (e.g., semantic chunk selection with hierarchical summarization).
- **FR-040**: Compressed context MUST retain all entity references and relationships present in the original context.
- **FR-041**: Compression ratio MUST be configurable per workload (baseline target 70–90%, adjustable higher or lower per use case).
- **FR-042**: Compression MUST support a configurable tradeoff between quality, latency, and reduction.
- **FR-043**: Compression MUST have configurable minimum context size to prevent over-compression.
- **FR-044**: Compression quality MUST be measured by three complementary metrics: Recall (fraction of relevant info preserved), Precision (fraction of output relevant to query), and Faithfulness (output does not introduce hallucinated information).
- **FR-045**: The system MUST define a benchmark suite for evaluating compression quality metrics (Recall, Precision, Faithfulness), run as part of compression strategy validation and regression testing.

#### Upstream Compatibility

- **FR-046**: All extension points MUST be implementable without modifying upstream code.
- **FR-047**: Provider interfaces MUST be designed to not conflict with upstream retrieval or storage interfaces.

#### Retrieval Pipeline & Entities

- **FR-048**: The system MUST define a `RetrievalPipeline` entity containing: `pipeline_id`, ordered list of `strategies` (vector, graph, keyword), `fusion_method`, `ranking_strategy` reference, `compression_strategy` reference, and `context_builder` reference — enabling per-workload retrieval pipeline configuration.
- **FR-049**: The system MUST define a `KnowledgeVersion` entity containing: `version_id`, `created_at`, `parent_version` (optional), `status` (sealing, sealed, corrupted), and `checksum` — representing a sealed, verifiable snapshot of the complete index.

#### Index Rebuild & Consistency

- **FR-050**: The system MUST support a rebuild operation that reconstructs the `VectorStore` index from authoritative Storage data.
- **FR-051**: The system MUST support a rebuild operation that reconstructs the `GraphStore` index from authoritative Storage data.
- **FR-052**: The system MUST support an index consistency verification operation that compares derived indices (VectorStore, GraphStore) against Storage and reports any discrepancies.

#### Provider Versioning

- **FR-053**: Every provider MUST expose metadata: `provider_name` (unique identifier), `provider_version` (semantic version), and `provider_capabilities` — a structured list where each capability declares a `name`, `version` (semver), and `stability` (stable, beta, deprecated). This ensures capabilities are machine-verifiable, not free-form strings.
- **FR-054**: Provider version MUST be recorded in the audit log for every operation to enable deterministic replay and compatibility validation.

### Key Entities

- **KnowledgeSource** (NEW — root entity): Universal foundation entity representing any indexed knowledge origin. All source types derive from this: `Repository`, `Document`, `Dataset`, `Image`, `Memory`, and future source types. Contains common attributes (source ID, source type, ingestion timestamp, hash, status). Enables uniform handling across all layers regardless of source origin.
- **KnowledgeChunk** (NEW — atomic retrieval unit): The fundamental unit of retrieval across all layers. Every chunk contains:
  - `chunk_id` (deterministic hash of content)
  - `source_id` (origin KnowledgeSource)
  - `knowledge_version` (index snapshot version)
  - `chunk_type` — one of: `CODE_FILE`, `CODE_CLASS`, `CODE_FUNCTION`, `CODE_INTERFACE`, `CODE_SYMBOL`, `DOCUMENT`, `DOCUMENT_SECTION`, `DOCUMENT_PARAGRAPH`, `MEMORY`, `MEMORY_FACT`, `MEMORY_SUMMARY`, `DATASET`, `IMAGE`, `CUSTOM`, `UNKNOWN`
  - `content` (text or HTML)
  - `embedding` (vector representation)
  - `parent_chunk_id` (optional — for hierarchical chunking, points to containing chunk)
  - `root_chunk_id` (optional — for lineage tracking, points to the topmost ancestor)
  - `metadata` including provenance: `source_type`, `source_path`, `source_reference`, `ingestion_timestamp`, `provider_version`, plus structured properties (page numbers, summaries, keywords, tokens, cross-references)

Chunks are produced by Ingestion, stored in VectorStore, retrieved by Retrieval, selected by Ranking, compressed by Compression, and assembled by Context Builder. Chunk type enables retrieval filtering, ranking specialization, compression strategy selection, and future Atlas reasoning. Lineage (`parent_chunk_id` / `root_chunk_id`) enables hierarchical chunking, summary ancestry tracking, compression traceability, and deterministic reconstruction. Provenance enables full auditability, deterministic replay, and compliance. All retrieval, regardless of source type (document, code, memory), operates on `KnowledgeChunk` units.
- **RetrievalPipeline** (NEW): First-class entity defining the retrieval execution plan for a workload. Contains: `pipeline_id`, `strategies` ordered list (vector, graph, keyword), `fusion_method` (RRF, weighted, etc.), `ranking_strategy` reference, `compression_strategy` reference, `context_builder` reference. Enables workload-specific retrieval, deterministic execution, and full audit logging for every query.
- **KnowledgeVersion** (NEW): A named, sealed snapshot of the complete index at a point in time. Contains: `version_id` (unique identifier), `created_at` (timestamp), `parent_version` (optional — for chained versions), `status` (sealing, sealed, corrupted), `checksum` (cryptographic hash of the full snapshot). Enables deterministic replay, rollback to previous versions, and snapshot integrity verification.
- **IngestionPipeline**: A configured sequence of steps (fetch, normalize, validate, index) that processes a `KnowledgeSource` into downstream layer entities.
- **IngestionJob**: A single execution of an `IngestionPipeline` against a specific `KnowledgeSource`. Contains status, progress, error log, and result references.
- **GraphNode**: A node in the Knowledge Graph, representing any indexed entity (document, code symbol, memory, file). Contains type, label, property map, and embedding reference.
- **GraphEdge**: A typed, weighted relationship between two `GraphNode` instances. Contains source/target node IDs, relationship type, weight, and property map.
- **Memory**: A semantic memory record containing content, metadata, embedding vector, and timestamp. Connected to facts, summaries, and relationships.
- **MemoryFact**: An atomic statement extracted from or associated with a Memory. Represents a single verifiable piece of information.
- **MemoryRelationship**: A directional or bidirectional connection between two Memory entities, with a typed relationship label and weight.
- **MemorySummary**: A condensed representation of one or more Memory entities, generated by a configurable summarization strategy.
- **Repository**: A source code repository tracked by the Code Memory Layer. Contains metadata (URL, language, branch, last indexed commit).
- **File**: A single source file within a Repository. Contains path, language, content hash, and parsed symbol references.
- **Symbol**: A named code entity (class, function, variable, interface, type) with its definition location, type signature, and documentation.
- **Dependency**: A typed relationship between two Symbols or between a File and external dependencies (imports, requires, includes).
- **Reference**: A usage of a Symbol at a specific location (file + line + column), enabling cross-reference queries.
- **SourceProvider**: Interface contract for ingestion from a specific source type (Git clone, filesystem crawl, document parse).
- **CodeParserProvider** (NEW): Interface contract for language-specific code parsing — extracts symbols, dependencies, references from source files. One implementation per supported language (Python, TypeScript, Rust, Go, Java).
- **RankingStrategy**: Interface contract for candidate ranking (similarity scoring, BM25 scoring, hybrid fusion, reranking).
- **ContextBuilder**: Interface contract for final context assembly (order fragments, deduplicate, apply token budget, emit structured context).
- **VectorProvider**: Interface contract for vector storage backends (upsert, search, delete, list collections).
- **EmbeddingProvider**: Interface contract for embedding models (embed text, embed batch, dimensionality).
- **GraphProvider**: Interface contract for graph storage backends (create node, create edge, traverse, query by property).
- **CompressionProvider**: Interface contract for context compression strategies (compress, estimate compression ratio, minimum output size).
- **StorageProvider**: Interface contract for persistent entity storage (CRUD for Memories, Facts, Summaries, Repositories, Files, Symbols).

---

## Success Criteria _(mandatory)_

### Measurable Outcomes

#### Functional Acceptance Criteria

- **SC-F01**: A developer can add a new vector database backend by implementing only the `VectorProvider` interface (approximately 5–15 methods) — no changes to retrieval, ranking, or query logic required.
- **SC-F02**: A developer can add a new compression strategy by implementing only the `CompressionProvider` interface — no changes to retrieval or storage layers required.
- **SC-F03**: Code Memory Layer can ingest a repository with 1M+ LOC and respond to symbol queries within acceptable latency for the deployment environment. (Specific performance targets — e.g., 5s first query, 2s cached — are hardware-dependent and should be defined in a dedicated Performance Benchmark specification.)
- **SC-F04**: Memory Layer can store, retrieve, and search semantic memories with associated facts, summaries, and relationships through abstract interfaces.
- **SC-F05**: A developer can add a new knowledge source type by implementing only the `SourceProvider` interface — no changes to ingestion pipeline or downstream layers required.
- **SC-F06**: A developer can add a new ranking strategy by implementing only the `RankingStrategy` interface — no changes to retrieval or compression layers required.
- **SC-F07**: The Context Builder correctly orders, deduplicates, prioritizes, and enforces token budget on compressed fragments before emitting final context.
- **SC-F08**: The Ingestion Layer accepts at least three knowledge source types (Git repository, local filesystem directory, PDF document) through the same `SourceProvider` interface.
- **SC-F09**: The Knowledge Graph Layer stores nodes and edges representing code symbols, semantic memories, and cross-domain relationships, queryable through `GraphProvider`.
- **SC-F10**: A developer can add support for a new programming language in Code Memory by implementing only the `CodeParserProvider` interface for that language — no changes to Code Memory ingestion, storage, or retrieval logic required.
- **SC-F11**: The Retrieval Layer supports at least three pipeline strategies (vector-only, keyword-only, hybrid vector+keyword) configurable per workload without code changes.
- **SC-F12**: If a VectorStore or GraphStore is rebuilt from Storage, the resulting index produces identical query results to the original (Storage as source of truth verified).
- **SC-F13**: A knowledge version, once sealed, produces deterministically equivalent retrieval results for any query across repeated executions.
- **SC-F14**: All nine provider interfaces (Source, CodeParser, Vector, Embedding, Graph, Ranking, Compression, ContextBuilder, Storage) are defined, documented, and have at least one reference implementation each.
- **SC-F15**: After ingesting a document, repository, or memory, the system produces `KnowledgeChunk` objects with valid `chunk_id`, `source_id`, `knowledge_version`, `content`, and `metadata` for each fragment.
- **SC-F16**: A retrieval query against any source type (document, code, memory) returns results as `KnowledgeChunk` objects — the caller never needs to reach behind the chunk abstraction.
- **SC-F17**: The `KnowledgeChunk.chunk_type` field is populated with a valid ChunkType value for every chunk produced by Ingestion, enabling retrieval filtering by type without inspecting content.
- **SC-F18**: A `RetrievalPipeline` entity can be defined, configured with strategies and fusion method, and executed as the retrieval plan for a workload — all without modifying pipeline execution code.
- **SC-F19**: A `KnowledgeVersion` entity is created for each sealed index snapshot, with a unique `version_id` and verifiable `checksum`.

#### Non-Functional Acceptance Criteria

- **SC-NF01**: Context compression reduces token consumption per workload by a configurable target (baseline 70–90%), measured across a benchmark of 100 realistic queries against repositories of varying sizes.
- **SC-NF02**: The system supports at least two vector backend implementations (e.g., in-memory mock + one production backend) with identical retrieval results for the same query and data.
- **SC-NF03**: Merging an upstream release with changes to core retrieval or storage modules produces zero conflicts in Syntegrity extension code — all Syntegrity modifications reside outside upstream core files.
- **SC-NF04**: A full retrieval query (Ingestion → Retrieval → Ranking → Compression → Context Builder) completes in under 10 seconds for a 100K+ chunk corpus.
- **SC-NF05**: Deterministic audit log contains sufficient information to fully reconstruct the retrieval pipeline for any given query: input query → knowledge version → retrieved candidates → ranking scores → compression decisions → context builder assembly → final output.
- **SC-NF06**: The same query executed against the same knowledge version produces identical results across repeated runs.
- **SC-NF07**: The entire architecture is implementable and testable without any Rust toolchain or Rust runtime dependency.
- **SC-NF08**: The architecture does not import or depend on any Atlas-specific package or module — Atlas must be able to depend on Knowhere, not the reverse.
- **SC-NF09**: Token reduction, latency, and retrieval quality targets are independently configurable per workload, not globally fixed.
- **SC-NF10**: Compression quality metrics (Recall, Precision, Faithfulness) are measured on a benchmark suite of 100 queries and scored against baseline (uncompressed) retrieval results.
- **SC-NF11**: The Retrieval Pipeline supports at least 3 strategy compositions (vector-only, keyword-only, vector+keyword hybrid) selectable per workload.
- **SC-NF12**: A `CodeParserProvider` implementation exists for at least one programming language (e.g., Python) and can extract symbols, dependencies, and references from real-world source files.
- **SC-NF13**: Rebuilding a vector index from Storage produces identical query results to the original index (Storage source-of-truth property).
- **SC-NF14**: A KnowledgeChunk assigned to a knowledge version, when re-queried against the same version, returns the identical chunk content and metadata across repeated runs.
- **SC-NF15**: Chunk deduplication across documents (same content from different sources) produces the same deterministic `chunk_id` for identical content regardless of source.
- **SC-NF16**: A VectorStore rebuild from Storage produces query results identical to the original VectorStore index (rebuild correctness).
- **SC-NF17**: A GraphStore rebuild from Storage produces queries identical to the original GraphStore index (rebuild correctness).
- **SC-NF18**: Every provider operation in the audit log includes `provider_name`, `provider_version`, and `provider_capabilities` sufficient to identify the exact implementation used.
- **SC-NF19**: KnowledgeChunk lineage (`parent_chunk_id`, `root_chunk_id`) can be traversed to reconstruct the full hierarchical ancestry of any chunk.

---

## Out of Scope

- The actual implementation of Atlas capabilities (agents, IDE integration, autonomous workflows).
- The actual implementation of the Semantic Memory user-facing features (memory CRUD API endpoints).
- The actual implementation of the Code Memory user-facing features (repository ingestion API endpoints).
- The actual implementation of specific compression strategies beyond the provider interface definition and one baseline implementation.
- Full implementation of all ranking strategies (similarity, BM25, hybrid, reranking) — only the `RankingStrategy` interface and one baseline strategy need implementation.
- Real-time repository indexing (ingestion is offline/batch).
- Rust-based optimization libraries or services.
- Production deployment infrastructure (Docker, Kubernetes, CI/CD).
- User authentication, authorization, or multi-tenancy.
- Migration tooling for existing data from legacy storage to new provider interfaces.
- Knowledge versioning and snapshot management beyond the audit log requirements.

## Assumptions

- Provider implementations will be registered via a simple configuration mechanism (e.g., YAML config or environment variables) rather than runtime plugin discovery in the first iteration.
- The baseline CompressionProvider will be a semantic chunk selection strategy — more sophisticated approaches (hierarchical summarization, agent-guided extraction) are future work.
- Deterministic retrieval is scoped per knowledge version — changes to indexed knowledge (new ingestion, re-indexing) create a new version; within a version, results are fully reproducible.
- The Ingestion Layer initially supports at least three source types (Git, filesystem, PDF documents) via `SourceProvider` — additional source types are added via new provider implementations.
- The `KnowledgeSource` entity serves as the root abstraction for all source types; each specific source type derives from it and adds its own attributes.
- The Knowledge Graph Layer represents all indexed knowledge — not just code. It is a first-class architectural component, not an optional add-on.
- The Ranking Layer models four strategies (similarity, BM25, hybrid, reranking) but only one baseline strategy is implemented initially.
- The Context Builder always executes after Compression; it is not bypassable in the standard retrieval pipeline.
- The in-memory mock VectorProvider will serve as both the test double and the default development provider.
- Code Memory ingestion is assumed to be an offline/batch process — real-time repository indexing is out of scope for the initial architecture.
- The upstream codebase that this architecture must remain compatible with is the `knowhere` repository as defined in the project structure (apps/api, apps/worker, packages/shared-python).

## Dependencies

- Existing `knowhere` repository structure and module layout (apps/api, apps/worker, packages/shared-python).
- Existing SQLAlchemy ORM models and PostgreSQL schema for any persisted entities that bridge to database storage.
- Existing Pydantic schema patterns for provider interface contracts.
- Existing Celery task infrastructure for any async ingestion workflows.
- Configuration system (environment variables / config files) for provider registration.
- Observability infrastructure (existing metrics/logging patterns in the project).
- For Git source ingestion: `git` CLI or a Git library (e.g., GitPython).
- For document ingestion: existing document parsing infrastructure (apps/worker/app/services/document_parser/).
