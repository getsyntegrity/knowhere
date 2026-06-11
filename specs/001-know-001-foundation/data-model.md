# Data Model: KNOW-001 Foundation Architecture

**Date**: 2026-06-11 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

## Model Overview

```mermaid
erDiagram
    KnowledgeSource ||--o{ KnowledgeChunk : "produces"
    KnowledgeSource ||--o{ IngestionJob : "tracks"
    KnowledgeChunk }o--|| KnowledgeVersion : "belongs to"
    KnowledgeChunk ||--o{ GraphNode : "indexed as"
    KnowledgeChunk ||--o{ GraphEdge : "connected by"
    KnowledgeChunk o--o| KnowledgeChunk : "parent/child (lineage)"
    KnowledgeVersion ||--o{ KnowledgeChunk : "snapshots"
    KnowledgeVersion o--o| KnowledgeVersion : "parent"

    KnowledgeSource ||--o{ Repository : "is a"
    KnowledgeSource ||--o{ Memory : "is a"
    KnowledgeSource ||--o{ Document : "is a"

    Repository ||--o{ File : "contains"
    File ||--o{ Symbol : "defines"
    File ||--o{ Dependency : "declares"
    Symbol ||--o{ Reference : "referenced by"
    Symbol ||--o{ Dependency : "depends on"

    Memory ||--o{ MemoryFact : "contains"
    Memory ||--o{ MemorySummary : "summarized by"
    Memory ||--o{ MemoryRelationship : "connects"

    RetrievalPipeline ||--|| RankingStrategy : "uses"
    RetrievalPipeline ||--|| CompressionProvider : "uses"
    RetrievalPipeline ||--|| ContextBuilder : "uses"

    EmbeddingProvider ||--o{ KnowledgeChunk : "embeds"
    VectorProvider ||--o{ KnowledgeChunk : "indexes"
    GraphProvider ||--o{ GraphNode : "stores"
    GraphProvider ||--o{ GraphEdge : "stores"
```

## Entities

### KnowledgeSource

Root entity for all ingested knowledge origins. Abstract base — every source is a concrete subtype.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | UUID | Unique identifier |
| `source_type` | Enum(REPOSITORY, DOCUMENT, DATASET, IMAGE, MEMORY, CUSTOM) | Type discriminator |
| `ingestion_timestamp` | DateTime | When first ingested |
| `hash` | String | Content hash for dedup |
| `status` | Enum(pending, active, error) | Current status |
| `metadata` | JSON | Type-specific metadata |

**Subtypes**:
- `Repository`: url, language, branch, last_commit, clone_path
- `Document`: file_name, file_type, page_count, parser_version
- `Dataset`: name, format, record_count, schema
- `Image`: file_name, width, height, format
- `Memory`: title, source, tags
- `CUSTOM`: arbitrary key-value pairs

### KnowledgeChunk

The atomic retrieval unit across all layers. All retrieval operates on chunks.

| Field | Type | Description |
|-------|------|-------------|
| `chunk_id` | String (UUID5) | Deterministic hash of content — enables cross-source dedup |
| `source_id` | UUID FK → KnowledgeSource | Origin source |
| `knowledge_version` | UUID FK → KnowledgeVersion | Index snapshot version |
| `chunk_type` | Enum(CODE_FILE, CODE_CLASS, CODE_FUNCTION, CODE_INTERFACE, CODE_SYMBOL, DOCUMENT, DOCUMENT_SECTION, DOCUMENT_PARAGRAPH, MEMORY, MEMORY_FACT, MEMORY_SUMMARY, DATASET, IMAGE, CUSTOM, UNKNOWN) | Type classification |
| `content` | Text | Chunk content (text, HTML, or reference) |
| `embedding` | Vector | Embedding representation (nullable — computed async) |
| `parent_chunk_id` | String (UUID5) nullable FK → KnowledgeChunk | Lineage — parent chunk for hierarchical chunking |
| `root_chunk_id` | String (UUID5) nullable FK → KnowledgeChunk | Lineage — topmost ancestor |
| `metadata` | JSON | See Provenance section below |
| `created_at` | DateTime | Creation timestamp |

**Provenance (in `metadata`)**:

| Field | Type | Description |
|-------|------|-------------|
| `source_type` | String | Origin source type (repository, document, memory, etc.) |
| `source_path` | String | Original path within source |
| `source_reference` | String | Line/offset/identifier reference |
| `ingestion_timestamp` | DateTime | When this chunk was created |
| `provider_version` | String | Version of the provider that created this chunk |
| `page_nums` | List[int] | Source page numbers (documents) |
| `summary` | String | LLM summary |
| `keywords` | List[str] | Extracted keywords |
| `tokens` | List[str] | Pre-tokenized terms |
| `connect_to` | List[Connection] | Cross-chunk references (embedding relations) |

**Validation rules**:
- `chunk_id` is deterministic: SHA-based UUID5 of `content` + source context
- `chunk_type` MUST be a valid enum value; `CUSTOM` allowed for client-defined types
- If `parent_chunk_id` is set, `root_chunk_id` MUST also be set
- `content` MUST be non-empty
- `knowledge_version` MUST reference a sealed KnowledgeVersion

### KnowledgeVersion

Sealed, verifiable snapshot of the complete index.

| Field | Type | Description |
|-------|------|-------------|
| `version_id` | UUID | Unique identifier |
| `created_at` | DateTime | Creation timestamp |
| `parent_version` | UUID nullable FK → KnowledgeVersion | Previous version (for chaining) |
| `status` | Enum(sealing, sealed, corrupted) | Lifecycle state |
| `checksum` | String | Cryptographic hash of full snapshot |
| `metadata` | JSON | Version metadata (trigger, author, description) |

**State transitions**:

```
sealing → sealed (on successful seal)
sealing → corrupted (on failure)
sealed → corrupted (on checksum mismatch)
```

**Implementation note**: Implementations MAY use incremental snapshots internally, provided that replay semantics remain equivalent to a full atomic snapshot.

### RetrievalPipeline

First-class entity defining a per-workload retrieval execution plan.

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_id` | UUID | Unique identifier |
| `name` | String | Human-readable name |
| `strategies` | List[Enum(VECTOR, GRAPH, KEYWORD)] | Ordered list of retrieval strategies |
| `fusion_method` | Enum(RRF, WEIGHTED, CONCATENATE) | How to fuse multi-strategy results |
| `ranking_strategy` | String reference | Name of ranking strategy to use |
| `compression_strategy` | String reference | Name of compression strategy to use |
| `context_builder` | String reference | Name of context builder to use |
| `config` | JSON | Strategy-specific configuration |
| `version` | Integer | Pipeline definition version (for audit) |

**Validation rules**:
- `strategies` MUST contain at least one strategy
- All strategy/ranking/compression/context references MUST resolve to registered providers
- Pipeline configuration is immutable once created; changes create a new version

### IngestionJob

Execution record for a single ingestion run.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | UUID | Unique identifier |
| `source_id` | UUID FK → KnowledgeSource | Source being ingested |
| `knowledge_version` | UUID FK → KnowledgeVersion | Target version |
| `status` | Enum(pending, running, completed, failed) | Current status |
| `progress` | Float | 0.0–1.0 progress indicator |
| `chunks_created` | Integer | Number of chunks produced |
| `errors` | JSON[] | Error log for failed items |
| `started_at` | DateTime | Job start time |
| `completed_at` | DateTime nullable | Job completion time |

### GraphNode

A node in the Knowledge Graph representing any indexed entity.

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | UUID | Unique identifier |
| `entity_type` | String | Type discriminator (chunk, source, symbol, memory, etc.) |
| `entity_id` | String | ID of the represented entity |
| `knowledge_version` | UUID FK → KnowledgeVersion | Snapshot version |
| `properties` | JSON | Entity properties |
| `embedding` | Vector nullable | Optional embedding for graph+vector hybrid |

### GraphEdge

A typed, weighted relationship between two GraphNodes.

| Field | Type | Description |
|-------|------|-------------|
| `edge_id` | UUID | Unique identifier |
| `source_node_id` | UUID FK → GraphNode | Source node |
| `target_node_id` | UUID FK → GraphNode | Target node |
| `relationship_type` | Enum(EMBEDS, REFERENCES, DEPENDS_ON, CONTAINS, RELATED, CUSTOM) | Relationship type |
| `weight` | Float | Relationship weight |
| `properties` | JSON | Edge properties |
| `knowledge_version` | UUID FK → KnowledgeVersion | Snapshot version |

### Memory Layer

| Entity | Key Fields |
|--------|------------|
| `Memory` | memory_id, source_id, title, content, embedding, tags, created_at |
| `MemoryFact` | fact_id, memory_id, statement, confidence, source_reference |
| `MemoryRelationship` | rel_id, source_memory_id, target_memory_id, relationship_type, weight |
| `MemorySummary` | summary_id, memory_id, summary_text, strategy, compressed_length |

### Code Memory Layer

| Entity | Key Fields |
|--------|------------|
| `Repository` | repo_id, source_id, url, language, branch, last_commit, status |
| `File` | file_id, repo_id, path, language, content_hash, parser_version |
| `Symbol` | symbol_id, file_id, name, kind (class, function, variable, interface, type), signature, doc, line_start, line_end |
| `Dependency` | dep_id, source_file_id, target_symbol_id, import_path, dep_type |
| `Reference` | ref_id, symbol_id, file_id, line, column, context |

## Provider Registry

All providers register via configuration with metadata:

```yaml
providers:
  embedding:
    default:
      provider_name: "openai-embedding"
      provider_version: "1.0.0"
      capabilities:
        - name: "text-embedding-3-small"
          version: "1.0.0"
          stability: "stable"
        - name: "text-embedding-3-large"
          version: "1.1.0"
          stability: "beta"
```

Provider fallback is opt-in per category:
- `EmbeddingProvider`, `VectorProvider`: SHOULD configure fallback
- `StorageProvider`, `GraphProvider`: SHOULD NOT configure fallback (fail fast)
