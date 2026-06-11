# Feature Specification: KNOW-002 Canonical Knowledge Model

**Feature Branch**: `002-know-002-canonical`
**Created**: 2026-06-11
**Status**: Draft
**Input**: Syntegrity Canonical Knowledge Model — create an implementation-agnostic canonical abstraction layer that protects Syntegrity products from upstream Knowhere model changes while enabling multi-provider memory and retrieval.

> **Normative**: `spec.md`, `data-model.md` — define the canonical model contract independent of implementation.
> **Non-normative**: `research.md`, `plan.md`, `tasks.md` — describe the Python reference implementation and are not part of the canonical contract.

## Clarifications

### Session 2026-06-11

- Q: How should Chunk identity and semantic equivalence be distinguished? → A: `chunk_id` = repository_id + file_id + location (deterministic, unique); `semantic_hash` = content hash only (deduplication and semantic equivalence)
- Q: Should source location be a shared value object? → A: Yes, introduce CodeLocation value object shared across Symbol, Chunk, and Reference.
- Q: Should Repository origin_uri be renamed for broader compatibility? → A: Rename to `source_uri` to align with multi-provider sourcing semantics.
- Q: Should KnowledgeAsset be reserved for future non-code assets? → A: Yes, add KnowledgeAsset placeholder to §6.8 Optional Future Entities.
- Q: How should deterministic identifier generation evolve over time? → A: Identifier generation is part of the public Canonical Knowledge Model contract. Once released, identifier algorithms and input composition rules MUST NOT change. Repository.id, File.id, Symbol.id, Chunk.id, Relationship.id, and Reference.id are permanent. New entity types, optional attributes, metadata fields, serialization formats, and adapters may evolve freely.

## 1. Problem Statement

Knowhere is being extended by Syntegrity while maintaining long-term compatibility with the upstream project. The existing Knowhere internal models (KnowledgeSource, KnowledgeChunk, KnowledgeVersion, etc.) are designed for Knowhere's specific retrieval pipeline and are tightly coupled to its provider interfaces, vector store assumptions, and chunking strategies.

Syntegrity products — including Atlas, Mem0 integrations, Codebase Memory MCP, and future custom parsers — cannot safely depend directly on these Knowhere models because:

- Upstream Knowhere model changes would cascade into Syntegrity code
- Knowhere models carry assumptions (e.g., vector embeddings, retrieval-specific metadata) that are irrelevant or harmful to other consumers
- Multiple upstream providers (Knowhere, Atlas Native, Mem0, external parsers) produce structurally different data that must be unified into a single consumable representation
- Historical recovery and deterministic reconstruction require an immutable, source-agnostic representation

A canonical knowledge model is needed — an Anti-Corruption Layer (ACL) that sits between upstream providers and Syntegrity consumers, providing a stable, provider-agnostic abstraction that insulates all Syntegrity products from upstream implementation changes.

## 2. Goals

- Define a stable, extensible, provider-agnostic canonical knowledge model capable of representing repositories, files, symbols, code chunks, relationships, and references
- Establish adapter contracts that convert provider-specific data into canonical entities without modifying either side
- Enable multiple producers (Knowhere, Mem0, Atlas Native, external parsers, future sources) to generate identical canonical entities for the same underlying content
- Support deterministic reconstruction of indexed repositories from canonical entities alone
- Enable deterministic reconstruction of repository state from canonical entities alone
- Provide a factory contract that normalizes source data, validates invariants, and generates deterministic identifiers
- Ensure the canonical model is completely independent of vector databases, embedding providers, LLM providers, tree-sitter, and retrieval engines

## 3. Non-Goals

- Replacing, modifying, or duplicating existing Knowhere internal models (KnowledgeSource, KnowledgeChunk, KnowledgeVersion, etc.)
- Altering existing Knowhere parsing, indexing, or retrieval structures
- Designing a new retrieval engine or search system
- Defining how downstream consumers (Atlas, Mem0, etc.) process canonical entities — only the contract for producing them
- Specifying a particular serialization format, database, or persistence technology
- Defining UI components, API endpoints, or user-facing interfaces
- Building the adapter implementations themselves — only the contracts adapters must satisfy

## 4. Architecture Overview

The Canonical Knowledge Model acts as an **Anti-Corruption Layer (ACL)** between upstream providers and Syntegrity consumers.

```
                    ┌─────────────────────────────────────────┐
                    │          Syntegrity Consumers           │
                    │  (Atlas, Mem0, MCP, custom parsers...)  │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │        Canonical Knowledge Model        │
                     │  (Repository, File, Symbol, Chunk,      │
                     │   Relationship, Reference)                │
                    │                                         │
                    │  CanonicalFactory ──► validates         │
                    │  Adapters ────────► converts            │
                    └────────────────┬────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
┌───────▼───────┐          ┌────────▼───────┐          ┌────────▼───────┐
│   Knowhere    │          │  Atlas Native  │          │  Mem0 / Other  │
│   Adapter     │          │   Adapter      │          │   Adapters     │
└───────┬───────┘          └────────┬───────┘          └────────┬───────┘
        │                            │                            │
┌───────▼──────────────────┐ ┌──────▼──────────────────┐ ┌──────▼──────────┐
│   Knowhere Internal      │ │   Atlas Internal        │ │   Mem0 / Other  │
│   Models & Storage       │ │   Storage & Models      │ │   Storage       │
└──────────────────────────┘ └─────────────────────────┘ └─────────────────┘
```

**Key architectural properties:**

1. **Provider isolation**: No provider-specific type leaks into the canonical layer. Each provider has an adapter responsible for conversion.
2. **Stable consumer contract**: Syntegrity consumers depend only on canonical entities, never on upstream models.
3. **Minimal surface**: The canonical model contains only what consumers need. Provider-specific metadata is either mapped or excluded.
4. **Deterministic identity**: Entity identifiers are derived from content, enabling cross-provider deduplication and reconstruction.
5. **Recovery scope**: Snapshot-based state recovery is moved to KNOW-004 Snapshot & Versioning.

### Producer Isolation

Every upstream system is isolated behind its own adapter. Adapters are the only components that know about both the provider's internal model and the canonical model. Changes to an upstream system's model only require updating that system's adapter — the canonical entities and all consumers remain unchanged.

### Consumer Protection

No Syntegrity consumer ever imports or depends on a provider-internal type. All data arrives as canonical entities. This means a provider can be swapped, upgraded, or removed without changes to consumer code, as long as a working adapter exists.

## 5. Domain Model

The canonical knowledge domain consists of **six primary entities** — Repository, File, Symbol, Chunk, Relationship, and Reference — plus three **optional future entities** — MemoryFact, DomainConcept, and DeterministicArtifact.

### Entity Dependency Graph

```
Repository ──► File ──► Chunk
     │              │
     │              ├──► Symbol
     │              │
     │              └──► Reference
     │
     └──► Relationship (connects any entities)
```

- **Repository**: Sole aggregate root and ownership boundary. Owns all other entities within its scope. No other entity type serves as an aggregate root — Files, Symbols, Chunks, Relationships, and References always exist within a Repository boundary. Direct retrieval operations (e.g., `get_file(file_id)`, `get_symbol(symbol_id)`) exposed by `CanonicalRepository` are navigation and analysis conveniences; they do NOT imply independent lifecycle, ownership, or persistence outside the Repository boundary.
- **File**: Belongs to a Repository. Contains Chunks and Symbols.
- **Symbol**: Defined within a File. May reference other Symbols.
- **Chunk**: Extracted from a File at a specific location.
- **Relationship**: Links any two entities with a typed edge.
- **Reference**: A cross-entity pointer with semantic meaning.

### Identifier Philosophy

Every canonical entity receives a **deterministic, content-derived identifier** that is:
- Reproducible from content alone, independent of provider
- Unique within its entity type scope
- Stable across time — re-indexing identical content produces the same ID
- Opaque to consumers (no semantic encoding in the identifier format)
- **Permanent** — identifier generation is part of the public contract and MUST NOT change after release

The following identifiers are considered permanent: `Repository.id`, `File.id`, `Symbol.id`, `Chunk.id`, `Relationship.id`, `Reference.id`. Future evolution MAY introduce new entity types, optional attributes, metadata fields, serialization formats, and adapters, but MUST NOT alter canonical identifier generation.

### 5.1 CodeLocation Value Object

CodeLocation is a reusable value object representing a source location span in a File. It is shared across Symbol, Chunk, and Reference entities.

| Attribute       | Description                                        | Mutability |
|-----------------|----------------------------------------------------|------------|
| `start_line`    | Starting line number (1-indexed)                   | Immutable  |
| `start_column`  | Starting column number (1-indexed)                 | Immutable  |
| `end_line`      | Ending line number (1-indexed)                     | Immutable  |
| `end_column`    | Ending column number (1-indexed)                   | Immutable  |

**Invariants:**
- `start_line` ≤ `end_line`; if equal, `start_column` ≤ `end_column`
- All values are positive integers (1-indexed)
- The location must fall within the bounds of the parent File

## 6. Entity Definitions

### 6.1 Repository

A Repository represents an indexed codebase, knowledge base, or collection of files.

| Attribute       | Description                                                  | Mutability |
|-----------------|--------------------------------------------------------------|------------|
| `id`            | Deterministic identifier derived from the repository's canonical source URI | Immutable |
| `name`          | Human-readable name (e.g., repository name, project title)   | Mutable    |
| `source_uri`    | Provider-specific URI or identifier from which this repository was produced | Immutable |
| `source`        | Label identifying the provider (e.g., "knowhere", "mem0", "atlas") | Immutable |
| `files`         | Collection of File entities belonging to this repository     | Mutable    |
| `created_at`    | Timestamp of first ingestion                                 | Immutable |
| `metadata`      | Extensible key-value map for provider-specific or domain-specific attributes | Mutable |

**Invariants:**
- `id` must be reproducible from `source_uri` and `source` alone
- `name` and `source_uri` are required; all other attributes may be empty for a minimal entity
- `metadata` must not contain fields that duplicate canonical attributes

### 6.2 File

A File represents a single source file or document within a Repository.

| Attribute      | Description                                                  | Mutability |
|----------------|--------------------------------------------------------------|------------|
| `id`           | Deterministic identifier derived from the file's path and repository | Immutable |
| `repository_id`| Reference to the parent Repository's id                      | Immutable |
| `path`         | Relative path within the repository                          | Immutable |
| `language`     | Optional language label (e.g., "python", "markdown", "unknown") | Mutable |
| `checksum`     | Content hash for integrity verification                      | Immutable |
| `size_bytes`   | Size of the original source content                          | Immutable |
| `symbols`      | Collection of Symbol entities defined in this file           | Mutable |
| `chunks`       | Collection of Chunk entities extracted from this file        | Mutable |
| `references`   | Collection of Reference entities originating from this file  | Mutable |
| `metadata`     | Extensible key-value map                                     | Mutable |

**Invariants:**
- `id` must be reproducible from `path` and `repository_id`
- `path` must be unique within a Repository
- `checksum` uses a content-hash algorithm that allows deterministic reproduction
- A File may have zero symbols, zero chunks, or zero references (e.g., a binary file with only metadata)

### 6.3 Symbol

A Symbol represents a named code or document symbol (function, class, variable, method, section heading, etc.).

| Attribute      | Description                                                  | Mutability |
|----------------|--------------------------------------------------------------|------------|
| `id`           | Deterministic identifier derived from the symbol's qualified name and file | Immutable |
| `file_id`      | Reference to the parent File's id                            | Immutable |
| `repository_id`| Reference to the parent Repository's id                      | Immutable |
| `name`         | Local name of the symbol (e.g., "process_data")              | Immutable |
| `qualified_name`| Fully qualified name within the repository (e.g., "module.submodule.process_data") | Immutable |
| `kind`         | Kind of symbol (e.g., "function", "class", "variable", "method", "section") | Immutable |
| `scope`        | Optional parent scope identifier if this symbol is nested    | Mutable |
| `location`     | Source location as a CodeLocation value object                    | Immutable |
| `signature`    | Optional text signature for callables (e.g., function signature stripped of body) | Mutable |
| `documentation`| Optional docstring or comment text associated with the symbol | Mutable |
| `children`     | Collection of child Symbol ids for hierarchical symbols      | Mutable |
| `metadata`     | Extensible key-value map                                     | Mutable |

**Invariants:**
- `qualified_name` must be unique within a Repository
- `id` must be reproducible from `qualified_name` and `repository_id`
- `location` (CodeLocation) must be within the bounds of the parent File
- Circular `children` references are prohibited

### 6.4 Chunk

A Chunk represents a contiguous span of text extracted from a File.

| Attribute     | Description                                                  | Mutability |
|---------------|--------------------------------------------------------------|------------|
| `id`          | Deterministic identifier derived from (repository_id, file_id, location) | Immutable |
| `file_id`     | Reference to the parent File's id                            | Immutable |
| `repository_id`| Reference to the parent Repository's id                     | Immutable |
| `text`        | The raw text content of the chunk                            | Immutable |
| `location`    | Source location as a CodeLocation value object                    | Immutable |
| `semantic_hash`| Content hash derived from `text` only, for cross-provider deduplication and semantic equivalence detection | Immutable |
| `chunk_type`  | Semantic type label (e.g., "code", "documentation", "comment", "heading", "unknown") | Immutable |
| `checksum`    | Content hash of the text field                               | Immutable |
| `ordering`    | Ordinal position within the parent file                      | Immutable |
| `symbol_ids`  | Optional collection of Symbol ids that reference or are defined within this chunk | Mutable |
| `metadata`    | Extensible key-value map                                     | Mutable |

**Invariants:**
- `id` must be reproducible from (repository_id, file_id, location), ensuring uniqueness within a Repository
- `semantic_hash` must be reproducible from `text` only, enabling cross-provider deduplication and semantic equivalence detection
- `checksum` must be computed from `text` and must match a deterministic re-computation
- `location` (CodeLocation) must be within the bounds of the parent File
- `ordering` must be unique within a File
- Chunks from the same File must not overlap in source location

**Hash Distinction:**
Although both `semantic_hash` and `checksum` are computed from `text` using the same algorithm (SHA-256) in the default implementation, they serve distinct contracts:
- **`semantic_hash`**: Semantic equivalence contract — two chunks with identical `semantic_hash` are semantically the same text regardless of location or provider. This is a cross-provider deduplication primitive.
- **`checksum`**: Integrity contract — verifies that the chunk text has not been corrupted or altered since creation. This is a self-integrity primitive.
Future implementations may use different algorithms for each field (e.g., perceptual hash for `semantic_hash`, SHA-256 for `checksum`). The two fields MUST NOT be treated as interchangeable.

### 6.5 Relationship

A Relationship represents a typed edge connecting any two canonical entities.

| Attribute       | Description                                                  | Mutability |
|-----------------|--------------------------------------------------------------|------------|
| `id`            | Deterministic identifier derived from (source_id, target_id, type, repository_id) | Immutable |
| `repository_id` | Reference to the parent Repository's id                      | Immutable |
| `source_id`     | Canonical entity id of the relationship source               | Immutable |
| `target_id`     | Canonical entity id of the relationship target               | Immutable |
| `type`          | Semantic type label (e.g., "imports", "calls", "extends", "implements", "contains") | Immutable |
| `weight`        | Optional numeric weight or strength (0.0 to 1.0)             | Mutable |
| `attributes`    | Optional key-value map for typed relationship attributes     | Mutable |
| `metadata`      | Extensible key-value map                                     | Mutable |

**Invariants:**
- `id` must be reproducible from (source_id, target_id, type, repository_id)
- `source_id` and `target_id` must refer to existing canonical entities within the same Repository
- Self-referencing relationships (source_id == target_id) are permitted
- Duplicate (source_id, target_id, type) tuples are not permitted within a Repository

### 6.6 Reference

A Reference represents an occurrence-based pointer from one entity to another, carrying contextual information about how the reference is used.

| Attribute       | Description                                                  | Mutability |
|-----------------|--------------------------------------------------------------|------------|
| `id`            | Deterministic identifier derived from (source_id, target_id, location, repository_id) | Immutable |
| `repository_id` | Reference to the parent Repository's id                      | Immutable |
| `source_id`     | Canonical entity id of the reference's originating entity    | Immutable |
| `target_id`     | Canonical entity id of the referenced entity                 | Immutable |
| `source_file_id`| File id where the reference originates                       | Immutable |
| `target_file_id`| File id where the referenced entity resides                  | Immutable |
| `location`      | Source location as a CodeLocation value object               | Immutable |
| `context`       | Optional text snippet surrounding the reference              | Mutable |
| `role`          | Semantic role (e.g., "import", "call", "inherit", "type_annotation", "documentation_link") | Immutable |
| `metadata`      | Extensible key-value map                                     | Mutable |

**Invariants:**
- `id` must be reproducible from (source_id, target_id, location, repository_id)
- `source_id` and `target_id` must refer to existing canonical entities
- Multiple References between the same source and target at different locations are distinct entities
- A Reference is a specific occurrence; a Relationship is an aggregate typed connection

### 6.7 Optional Future Entities

The following entities are reserved for future specification:

- **MemoryFact**: A discrete piece of information derived from conversational or experiential sources (e.g., user preferences, historical decisions). Would extend the model to support Mem0 and similar memory systems.
- **DomainConcept**: A higher-level abstraction that groups related canonical entities under a domain-specific concept (e.g., "authentication flow", "data pipeline"). Would enable semantic navigation across entity boundaries.
- **DeterministicArtifact**: A binary or structured artifact (e.g., compiled output, test fixture, generated file) with a deterministic identity derived from its content. Would extend the model beyond text-based sources.
- **KnowledgeAsset**: A non-code knowledge asset (e.g., PDF, image, contract, spreadsheet, scientific document) supporting Atlas's evolution beyond source code. Would extend the model to represent binary and document-based knowledge with metadata, content references, and typed relationships.

These entities are described here to ensure the canonical model's extensibility mechanisms (metadata, relationships, references) accommodate them when they are formally specified.

## 7. Relationship Definitions

### 7.1 Entity Relationship Matrix

The following relationships are supported between canonical entities:

| Relationship Type      | Source(s)            | Target(s)          | Description |
|------------------------|----------------------|--------------------|-------------|
| `contains`             | Repository           | File               | The Repository contains this File |
| `contains`             | File                 | Chunk              | The File contains this Chunk |
| `contains`             | File                 | Symbol             | The File contains this Symbol |
| `contains`             | Symbol               | Symbol             | Parent Symbol contains a child Symbol |
| `references`           | Chunk                | Symbol             | Chunk text references a Symbol |
| `references`           | Reference            | Entity             | Reference points to any canonical entity |
| `imports`              | File / Chunk         | File / Symbol      | Source imports or depends on target |
| `calls`                | Symbol               | Symbol             | Source Symbol invokes target Symbol |
| `extends`              | Symbol               | Symbol             | Source Symbol extends or inherits from target |
| `implements`           | Symbol               | Symbol             | Source Symbol implements target interface/contract |
| `defines`              | Chunk                | Symbol             | Chunk contains the definition of a Symbol |
| `annotates`            | Entity               | Entity             | Source entity provides metadata/annotation about target |
| `derives_from`         | Chunk                | Chunk              | Derived content (e.g., minified, compiled) originates from source |
| `equivalent_to`        | Entity               | Entity             | Cross-provider equivalence (e.g., Knowhere chunk ≡ Atlas chunk) |


### 7.2 Cross-Provider Equivalence

The `equivalent_to` relationship is critical for multi-provider scenarios. When two providers generate canonical entities representing the same underlying content, they are linked via `equivalent_to` relationships. This enables:

- Deduplication across providers
- Merging retrieval results from multiple sources
- Gradual migration from one provider to another
- Verifying that different providers produce identical canonical representations

### 7.3 Relationship Cardinality

| From         | To           | Cardinality | Notes |
|--------------|-------------|-------------|-------|
| Repository   | File         | 1:N         | A Repository has many Files |
| File         | Chunk        | 1:N         | A File may have zero or more Chunks |
| File         | Symbol       | 1:N         | A File may have zero or more Symbols |
| File         | Reference    | 1:N         | A File may have zero or more References |
| Symbol       | Symbol       | N:M         | Symbol-to-Symbol relationships (calls, extends, etc.) |
| Chunk        | Symbol       | N:M         | A Chunk may reference many Symbols; a Symbol may appear in many Chunks |

## 8. Adapter Contracts

Adapters are the only components that understand both a provider's internal model and the canonical model. Each adapter contract specifies the conversion responsibility without prescribing implementation details.

### 8.1 General Adapter Contract

Every adapter MUST:
- Accept a provider-specific input and return a canonical entity (or collection of entities)
- Validate all invariants of the canonical entity before returning
- Fail explicitly with a descriptive error if conversion is not possible (without crashing the caller)
- Be stateless — given identical input, produce identical output (deterministic)
- Not modify, cache, or persist the provider's internal data

### 8.2 FileAdapter

**Responsibility**: Convert provider-specific file representations into canonical File entities.

**Input**: Provider-specific file data (e.g., Knowhere code file metadata, file system path + content, database record).

**Output**: One or more canonical `File` entities.

**Contract requirements:**
- MUST derive a deterministic `id` from the file's path and repository origin
- MUST compute a content `checksum` using the configured hash algorithm
- MUST extract or infer `language` from available provider metadata; fall back to "unknown" when unavailable
- MUST populate `path` as a relative path within the repository
- MUST populate `metadata` with any provider-specific attributes that do not map to canonical fields
- MUST NOT populate `symbols`, `chunks`, or `references` — those are populated by other adapters

### 8.3 SymbolAdapter

**Responsibility**: Convert provider-specific symbol representations into canonical Symbol entities.

**Input**: Provider-specific symbol data (e.g., tree-sitter AST node, LSP symbol, parser output).

**Output**: One or more canonical `Symbol` entities.

**Contract requirements:**
- MUST derive a deterministic `id` from the symbol's `qualified_name` and `repository_id`
- MUST construct `qualified_name` from the provider's hierarchical symbol information
- MUST map the provider's symbol kind to a canonical `kind` value; use "unknown" if no mapping exists
- MUST validate that `location` falls within the bounds of the parent File
- MUST preserve parent-child symbol hierarchy via the `children` collection
- MUST not populate `qualified_name` with path or file components that are not part of the symbol's logical name
- SHOULD extract `documentation` from provider docstrings or comments when available

### 8.4 ChunkAdapter

**Responsibility**: Convert provider-specific chunk representations into canonical Chunk entities.

**Input**: Provider-specific chunk data (e.g., Knowhere KnowledgeChunk, parser segment, embedding chunk).

**Output**: One or more canonical `Chunk` entities.

**Contract requirements:**
- MUST derive a deterministic `id` from (`repository_id`, `file_id`, `location`) to ensure uniqueness within a Repository
- MUST compute `checksum` from `text` only
- MUST compute a `semantic_hash` from `text` only for cross-provider deduplication and semantic equivalence detection
- MUST validate that `location` falls within the bounds of the parent File
- MUST assign an `ordering` that reflects the chunk's position within the file
- MUST map the provider's chunk type to a canonical `chunk_type`; use "unknown" if no mapping exists
- MUST NOT include embedding vectors, embedding metadata, or provider-specific retrieval scores
- SHOULD verify that the chunk `text` matches the source content at the specified `location`
- MAY populate `symbol_ids` if the adapter can identify which symbols are defined or referenced within the chunk

### 8.5 RelationshipAdapter

**Responsibility**: Convert provider-specific relationship or graph edge representations into canonical Relationship entities.

**Input**: Provider-specific relationship data (e.g., graph edge, dependency entry, cross-reference record).

**Output**: One or more canonical `Relationship` entities.

**Contract requirements:**
- MUST derive a deterministic `id` from (source_id, target_id, type, repository_id)
- MUST verify that `source_id` and `target_id` refer to existing canonical entities (adapter MAY resolve references lazily if entities are being created in a batch)
- MUST map the provider's relationship type to a canonical `type` from the supported relationship set; use "custom" prefixed with the provider name if no mapping exists
- MUST reject duplicate (source_id, target_id, type) tuples within the same Repository
- MAY populate `weight` or `attributes` from provider-specific relationship metadata

## 9. Factory Contracts

### 9.1 CanonicalFactory

The CanonicalFactory is responsible for creating canonical entities from raw source data. It sits above the adapters and provides:

- A unified entry point for canonical entity creation
- Invariant validation before entity construction
- Deterministic identifier generation
- Cross-entity consistency checks

**Factory responsibilities:**

| Responsibility              | Description |
|-----------------------------|-------------|
| Build canonical entities    | Accept normalized data and produce fully-validated canonical entity instances |
| Normalize source data       | Apply consistent transformations to source data (e.g., path normalization, text sanitization, language inference) before entity creation |
| Validate invariants         | Check all entity-level invariants (required fields, uniqueness constraints, location bounds, checksum integrity) before returning an entity |
| Generate identifiers        | Compute deterministic identifiers using the configured algorithm for each entity type |
| Enforce consistency         | Verify cross-entity references against the complete batch graph. Forward references inside the same batch are valid; references outside the batch must already exist |
| Reject invalid data         | Return structured error information for data that cannot be represented as canonical entities |

**Factory contract requirements:**
- MUST NOT depend on any provider-specific types, libraries, or data structures
- MUST accept source data exclusively through adapter outputs (normalized canonical data primitives)
- MUST produce only canonical entity types
- MUST validate all entity invariants before construction
- MUST use a deterministic identifier algorithm per the public contract (default SHA-256). The algorithm and identifier input composition rules are permanent and MUST NOT change after release
- MUST fail atomically — a batch of entities either all pass validation or none are returned (the caller decides whether to accept partial results)
- MUST provide a mechanism for batched creation with cross-entity reference validation: forward references inside the same batch are valid; references outside the batch must already exist

### 9.2 Factory Identifier Strategy

The identifier generation strategy MUST be:

- **Deterministic**: Same input always produces the same identifier
- **Permanent**: Identifier generation is part of the public Canonical Knowledge Model contract. The algorithm (SHA-256) and identifier input composition rules MUST NOT change after release. `Repository.id`, `File.id`, `Symbol.id`, `Chunk.id`, `Relationship.id`, and `Reference.id` are permanent identifiers.
- **Collision-resistant**: The probability of accidental collision must be negligible within the expected scale of entities
- **Provider-agnostic**: Identifier generation must not depend on provider-specific metadata

Identifier scope rules per entity type — these rules are **permanent** and MUST NOT change:

| Entity Type   | Identifier Inputs |
|---------------|-------------------|
| Repository    | `source_uri` + `source` label |
| File          | `path` + `repository_id` |
| Symbol        | `qualified_name` + `repository_id` |
| Chunk         | `repository_id` + `file_id` + `location` |
| Relationship  | `source_id` + `target_id` + `type` + `repository_id` |
| Reference     | `source_id` + `target_id` + `location` + `repository_id` |


### 9.3 Error Handling

The factory MUST return structured errors for:

- Missing required fields per entity type
- Field validation failures (e.g., location out of bounds, checksum mismatch)
- Duplicate identifier detection within a batch
- Circular or unresolvable cross-entity references
- Unknown or unmappable entity types

Error responses MUST include:
- The specific entity and field that caused the failure
- A machine-readable error code
- A human-readable description

## 10. Serialization Requirements

### 10.1 Principles

- The canonical model MUST be serializable to a portable, language-independent format
- Serialization and deserialization MUST be lossless — round-tripping an entity produces an identical entity
- The serialization format MUST NOT require any provider-specific libraries to read or write
- Versioning MUST be embedded in the serialized form to enable forward and backward compatibility

### 10.2 Format Requirements

- The canonical serialization format MUST support all six entity types plus aggregates (Repository with nested entities)
- The format MUST support streaming serialization for large collections of entities
- The format MUST include a schema identifier or version marker that readers can use to select an appropriate deserialization strategy
- The format MUST NOT carry provider-specific metadata unless it has been explicitly mapped to canonical `metadata` fields
- The format SHOULD support compression for storage and transmission efficiency
- The format SHOULD support selective deserialization (reading only a subset of entities from a serialized collection)

### 10.3 Versioning

- Every serialized entity or collection MUST carry a model version identifier
- Breaking changes to the canonical model (field removal, type changes, new required fields) MUST increment the major version
- Additive changes (new optional fields, new entity types) MUST increment the minor version
- Consumers MUST reject serialized data with an unsupported major version
- Consumers SHOULD gracefully handle unknown minor version data by ignoring unrecognized fields

## 11. Query & Navigation

### 11.1 Principles

Canonical consumers need a mechanism to navigate and query the canonical entity graph without coupling to any specific storage backend or persistence technology. This specification defines an in-memory query interface — the `CanonicalRepository` — that operates on collections of canonical entities.

- The query interface MUST be backend-agnostic and operate on in-memory entity collections
- The query interface MUST support navigation by entity identity and by relationship traversal
- The query interface MUST NOT prescribe any storage, database, or persistence technology
- The query interface MAY have multiple implementations (in-memory)

### 11.2 CanonicalRepository Interface

The `CanonicalRepository` provides entity retrieval (get) and discovery (find) operations. These operations are navigation and analysis conveniences; they do not imply that child entities (File, Symbol, Chunk, Relationship, Reference) have an independent lifecycle, ownership, or persistence boundary outside Repository.

**Retrieval by ID:**
- `get_file(file_id)` → Returns a single File entity by its canonical ID, or raises if not found
- `get_symbol(symbol_id)` → Returns a single Symbol entity by its canonical ID
- `get_chunk(chunk_id)` → Returns a single Chunk entity by its canonical ID
- `get_relationship(relationship_id)` → Returns a single Relationship entity by its canonical ID
- `get_reference(reference_id)` → Returns a single Reference entity by its canonical ID
- `get_repository(repository_id)` → Returns a single Repository by its canonical ID

**Discovery by relation:**
- `find_symbols(file_id)` → Returns all Symbols defined in the given File
- `find_chunks(file_id)` → Returns all Chunks extracted from the given File, in ordering
- `find_references(file_id)` → Returns all References originating in the given File
- `find_relationships(source_id)` → Returns all Relationships with the given source_id
- `find_relationships_by_target(target_id)` → Returns all Relationships with the given target_id
- `find_entities_by_type(entity_type)` → Returns all entities of a given type within a Repository

**Repository scope:**
- `get_file_by_path(repository_id, path)` → Returns a File by its repository-relative path
- `get_symbol_by_name(repository_id, qualified_name)` → Returns a Symbol by its qualified name

### 11.3 Implementation Guidance

The `CanonicalRepository` is an in-memory query abstraction. Implementations:
- MUST be stateless with respect to external storage — all entity data is passed at construction time
- MUST perform lookup by deterministic entity identifiers
- MUST support cross-entity navigation (e.g., File → Symbols, Symbol → Relationships)
- MUST NOT introduce any database, persistence, or storage dependency

_Persistence (durable storage, database backends, Snapshot lifecycle) is out of scope for KNOW-002 and will be addressed in a separate specification._

## 12. Extensibility Requirements

### 12.1 New Source Types

Adding a new upstream provider MUST require only:
1. Implementing the relevant adapter contracts (FileAdapter, SymbolAdapter, ChunkAdapter, RelationshipAdapter)
2. Registering the new adapter with the CanonicalFactory

No changes to canonical entities, the factory, or existing adapters are required.

### 12.2 New Entity Types

Adding a new canonical entity type (e.g., MemoryFact, DomainConcept) MUST require:
1. Defining the entity structure following the existing pattern (deterministic id, required invariants, metadata map)
2. Adding the entity to the CanonicalFactory's type registry
3. Adding an adapter contract for the new entity type

Existing entity types, relationships, and consumers remain unchanged.

### 12.3 Extended Attributes

The `metadata` key-value map on every entity provides a built-in extension mechanism:
- Providers can store provider-specific data that has no canonical equivalent
- Consumers can annotate entities with consumption-specific data without modifying the entity structure
- Future canonical fields can be introduced without breaking existing data — fields that were previously in `metadata` graduate to top-level attributes

### 12.4 Custom Relationship Types

Adapters MAY introduce provider-specific relationship types using the convention `provider_name:type_name`. The canonical model reserves the unprefixed namespace for standard relationship types. Custom relationship types are valid canonical entities and participate in all normal operations (serialization, query).

## 13. Acceptance Criteria

### 13.1 Reconstruction

- **AC-001**: Given a set of canonical entities for a Repository, the full entity graph (Files, Symbols, Chunks, Relationships, References) can be reconstructed without access to the original provider
- **AC-002**: Reconstructing from canonical entities produces an entity graph identical to the original at the time of creation

### 13.2 Navigation

- **AC-003**: A Symbol can be navigated to its parent File via `file_id`
- **AC-004**: A Chunk can be mapped to its exact source location within its parent File
- **AC-005**: All Symbols defined within a File can be enumerated from the File's `symbols` collection
- **AC-006**: All Relationships originating from or targeting an entity can be queried

### 13.3 Snapshot Recovery (Moved to KNOW-004)

Snapshot creation, verification, restoration, and historical rollback are out of scope for KNOW-002. The Snapshot entity and all Snapshot-related acceptance criteria have been moved to KNOW-004 Snapshot & Versioning.

- **AC-007**: _Moved to KNOW-004_ — Snapshot reproduces exact historical index state
- **AC-008**: _Moved to KNOW-004_ — Restored graph has same aggregate checksum
- **AC-009**: _Moved to KNOW-004_ — Repository rollback to prior Snapshot

### 13.4 Provider Equivalence

- **AC-010**: Two different providers indexing the same source content produce identical `semantic_hash` values for identical chunk text, and identical canonical identifiers for the same file at the same location
- **AC-011**: The `equivalent_to` relationship accurately links corresponding entities from different providers

### 13.5 Determinism

- **AC-012**: Indexing the same source content twice through the same adapter produces identical canonical entities (including identifiers)
- **AC-013**: Re-ordering or parallelizing entity creation does not change the resulting canonical entities

### 13.6 Isolation

- **AC-014**: No adapter implementation imports Knowhere internal types
- **AC-015**: No Syntegrity consumer imports any provider-internal type
- **AC-016**: Removing an adapter does not affect the functionality of other adapters or consumers

### 13.7 Boundary Conditions

- **AC-017**: An empty Repository (no Files, Symbols, Chunks, Relationships, or References) can be represented as a valid canonical entity
- **AC-018**: A Repository with a single File containing no symbols and one chunk is representable
- **AC-019**: A Repository with extremely large files (e.g., 1M+ lines) is representable without structural failure
- **AC-020**: Unicode content in file paths, symbol names, and chunk text is preserved accurately
- **AC-021**: Circular symbol references (e.g., mutually recursive functions) are handled without infinite loops
- **AC-022**: Binary files are representable with metadata only (no chunk text extraction required)
- **AC-023**: The model handles gracefully when a provider cannot supply all canonical fields (missing optional data)
- **AC-024**: Two chunks with identical `semantic_hash` but different `chunk_id` (i.e., semantically identical text at different locations) are both representable as distinct canonical entities, each with its own identity, location, and file context

## 14. Migration Strategy

### 14.1 Principles

- Migration MUST be incremental — not a big-bang cutover
- Existing Knowhere functionality MUST remain operational during migration
- Adapters MUST be developed and tested independently before the canonical model is enabled for any consumer
- The canonical model and existing Knowhere models MAY coexist during the transition period

### 14.2 Phased Migration

**Phase 1 — Foundation (this specification):**
- Define and ratify the canonical model specification
- Establish adapter contracts and factory contract
- Create a reference implementation of the CanonicalFactory
- Implement the first adapter (Knowhere) for a single entity type (File)

**Phase 2 — Entity Coverage:**
- Implement all adapters for the Knowhere provider (File, Symbol, Chunk, Relationship)
- Implement serialization for all entity types
- Implement the CanonicalRepository query interface
- Verify reconstruction from canonical entities matches Knowhere output

**Phase 3 — Consumer Adoption:**
- Migrate the first Syntegrity consumer (Atlas) to consume canonical entities exclusively
- Verify that Atlas functionality is preserved through the canonical layer
- Remove direct Knowhere model dependencies from Atlas

**Phase 4 — Multi-Provider:**
- Implement a second adapter (Mem0 or Atlas Native)
- Verify cross-provider entity equivalence
- Demonstrate equivalent_to relationship linking

**Phase 5 — Deprecation:**
- Document Knowhere-internal model dependencies as legacy
- Establish policy that all new Syntegrity modules consume canonical entities only
- Set target date for removing direct Knowhere model access from Syntegrity code

### 14.3 Rollback Plan

If issues are discovered during any phase:
- Phase 1 issues: Update specification and re-ratify
- Phase 2 issues: Correct adapter implementations; canonical model remains active
- Phase 3 issues: Atlas can revert to direct Knowhere dependency while adapter issues are resolved
- Phase 4 issues: Individual adapters can be disabled without affecting others

_Snapshot & Recovery lifecycle (Snapshot creation, verification, restoration, rollback) is moved to KNOW-004 Snapshot & Versioning._

## 15. Future Compatibility Considerations

### 15.1 Upstream Knowhere Changes

If Knowhere's internal models change in a future version:
- Only the Knowhere adapter needs to be updated to map new internal fields to canonical entities
- All canonical entities, consumers, and other adapters remain unaffected
- If Knowhere adds new capabilities not representable in the current canonical model, new canonical fields or entity types can be added via the extensibility mechanisms (Section 12)

### 15.2 New Provider Types

Future providers (custom parsers, indexing engines, knowledge bases) can be integrated by:
1. Implementing the relevant adapter contracts
2. Registering adapters with the CanonicalFactory
3. No changes to the canonical model unless the provider introduces fundamentally new data types

### 15.3 Atlas Native Integration

Atlas, as the first Syntegrity consumer, will:
- Consume canonical entities exclusively
- Never import Knowhere internal types
- Communicate through the canonical model exclusively
- Potentially contribute new adapter implementations for Atlas-specific sources

### 15.4 Mem0 Integration

Mem0 and similar memory systems will:
- Produce canonical MemoryFact entities (once the entity type is formally specified)
- Integrate through the Relationship mechanism to link MemoryFacts to existing canonical entities
- Consume canonical entities for context enrichment

### 15.5 Codebase Memory MCP

The Codebase Memory MCP server will:
- Expose canonical entities through MCP tool interfaces
- Provide search and retrieval over canonical entities
- Support state synchronization through canonical entity serialization

### 15.6 Semantic Versioning of the Canonical Model

The canonical model itself MUST be versioned using semantic versioning:
- **Major**: Breaking changes to entity structure (field removal, type changes, new required fields)
- **Minor**: Backward-compatible additions (new optional fields, new entity types, new relationship types)
- **Patch**: Clarifications, documentation, invariant refinements that do not change the entity schema

The model version MUST be embedded in serialized data and exposed by the factory for runtime compatibility checks.

## 16. User Scenarios & Testing

### User Story 1 — Syntegrity Developer Building a New Feature (Priority: P1)

A Syntegrity developer building a new feature in Atlas needs to access code symbol information from a previously indexed repository. They do not need to know whether the data was originally indexed by Knowhere, Mem0, or a custom parser.

**Why this priority**: This is the primary value proposition of the canonical model — insulating consumer code from provider specifics.

**Independent Test**: The developer can build and test a feature that reads Symbols from canonical entities using test data, without any provider adapter running.

**Acceptance Scenarios**:

1. **Given** a Repository with indexed code, **When** a developer queries Symbols by file, **Then** they receive canonical Symbol entities with name, kind, and location
2. **Given** canonical entities from different providers, **When** a developer processes them, **Then** they use identical code paths — no provider-specific branching

---

### User Story 2 — System Integrator Adding a New Provider (Priority: P1)

A system integrator needs to add support for a new code indexing provider (e.g., a custom parser for a proprietary language). They want to make the provider's output available to all Syntegrity consumers without modifying consumer code.

**Why this priority**: Multi-provider support is an architectural constraint (Constraint 4) and a core design goal.

**Independent Test**: The integrator can implement a FileAdapter and ChunkAdapter for the new provider and verify that existing consumers receive correct canonical entities without code changes.

**Acceptance Scenarios**:

1. **Given** an existing consumer of canonical entities, **When** a new provider adapter produces canonical entities, **Then** the consumer processes them without modification
2. **Given** a new provider with data that maps to canonical entities, **When** the adapter runs, **Then** all entity invariants are validated by the CanonicalFactory
3. **Given** provider data that cannot be fully mapped, **When** the adapter creates entities, **Then** available fields are populated and missing fields use defaults

---

### User Story 3 — Platform Engineer Verifying Cross-Provider Consistency (Priority: P2)

An engineer runs indexing on the same codebase using two different providers (Knowhere and a custom parser) and needs to verify that the canonical identifiers and entities are consistent.

**Why this priority**: Deterministic reconstruction and cross-provider equivalence are explicit design requirements (Goals, AC-010, AC-012).

**Independent Test**: The engineer can index the same file with two adapters and compare the resulting canonical entities programmatically.

**Acceptance Scenarios**:

1. **Given** the same source file, **When** indexed by two different adapters, **Then** canonical Chunk entities for identical text segments have the same `id`
2. **Given** a Symbol from one provider, **When** the equivalent Symbol from another provider is found, **Then** they are linked via `equivalent_to` relationship

---

### User Story 4 — Data Consumer Querying Entity Relationships (Priority: P3)

A data consumer (e.g., an AI-assisted code review tool) needs to follow relationships from a function symbol to all other symbols it calls, and from those called symbols to their source files.

**Why this priority**: Relationship navigation is important for downstream value but can be built incrementally after core entity support.

**Independent Test**: The consumer can query Relationships by source_id and target_id and traverse the entity graph without knowing which provider originally created the data.

**Acceptance Scenarios**:

1. **Given** a Repository with relationship data, **When** a consumer queries relationships for a specific Symbol, **Then** all Relationships where that Symbol is source or target are returned
2. **Given** a Relationship of type "calls", **When** the consumer follows it to the target Symbol, **Then** the target Symbol's File can be retrieved via `file_id`

---

### Edge Cases

- What happens when a provider indexes the same repository twice? — Deterministic identifiers ensure the second pass produces identical entities; duplicated Chunks are detected via `semantic_hash` for cross-provider deduplication
- How does the model handle a provider that cannot supply all canonical fields? — Required fields must be present; optional fields use safe defaults (empty string, zero, empty collection, "unknown")
- What happens when an adapter encounters data that violates canonical invariants? — The adapter rejects the data with a structured error; the CanonicalFactory does not produce invalid entities
- How does the model handle files that change between indexing passes? — New content produces new Chunk identifiers; the Relationship `derives_from` can link old and new chunks
- How does the model handle concurrent modifications to a Repository? — The canonical model is read-oriented for consumers; writes are batch-oriented through the factory with atomic batch semantics

## 17. Functional Requirements

### 17.1 Entity Requirements

- **FR-001**: The canonical model MUST provide entities for Repository, File, Symbol, Chunk, Relationship, and Reference
- **FR-002**: Every canonical entity MUST carry a deterministic identifier that is reproducible from its content
- **FR-003**: Every canonical entity MUST carry an extensible metadata map for provider-specific or domain-specific attributes
- **FR-004**: Every canonical entity MUST carry a reference to its parent Repository
- **FR-005**: The canonical model MUST support the future addition of MemoryFact, DomainConcept, DeterministicArtifact, and KnowledgeAsset entity types without structural changes to existing entities

### 17.2 Identifier Requirements

- **FR-006**: Entity identifiers MUST be deterministically derived from entity content, not from provider-assigned values
- **FR-007**: The identifier generation algorithm MUST be stable and permanent. Once released, the algorithm (SHA-256) and identifier input composition rules MUST NOT change


### 17.3 Adapter Requirements

- **FR-009**: The canonical model MUST define adapter contracts for FileAdapter, SymbolAdapter, ChunkAdapter, and RelationshipAdapter
- **FR-010**: Every adapter MUST be stateless and deterministic — identical input produces identical output
- **FR-011**: Every adapter MUST validate all canonical entity invariants before returning entities
- **FR-012**: Every adapter MUST fail with a structured error for data that cannot be converted

### 17.4 Factory Requirements

- **FR-013**: A CanonicalFactory MUST provide unified canonical entity creation from adapter outputs
- **FR-014**: The CanonicalFactory MUST validate all entity invariants before construction
- **FR-015**: The CanonicalFactory MUST NOT import or depend on any provider-specific types
- **FR-016**: The CanonicalFactory MUST support batched entity creation with cross-entity reference validation

### 17.5 Serialization Requirements

- **FR-017**: The canonical model MUST support lossless serialization and deserialization of all entity types
- **FR-018**: Serialized data MUST carry a model version identifier
- **FR-019**: Major version mismatches MUST cause deserialization to be rejected

### 17.6 Persistence Requirements

- **FR-020**: The canonical model MUST provide a `CanonicalRepository` query interface for entity retrieval and discovery by identity and relationship
- **FR-021**: The `CanonicalRepository` MUST be backend-agnostic and operate on in-memory entity collections without database dependencies
- **FR-022**: The query interface MUST support cross-entity navigation (File → Symbols, Symbol → Relationships, etc.)

### 17.7 Relationship Requirements

- **FR-023**: The canonical model MUST support typed relationships between any two canonical entities
- **FR-024**: The canonical model MUST support the `equivalent_to` relationship type for cross-provider equivalence
- **FR-025**: Adapters MUST be able to introduce custom relationship types using a namespaced convention

### 17.8 Isolation Requirements

- **FR-026**: No canonical entity, contract, or factory MUST import any provider-specific type
- **FR-027**: No Syntegrity consumer MUST import any provider-specific type
- **FR-028**: Adding or removing an adapter MUST NOT affect any other adapter or consumer
- **FR-029**: The canonical model MUST be completely independent of vector databases, embedding providers, LLM providers, tree-sitter, and retrieval engines

### 17.9 Validation Requirements

- **FR-030**: The CanonicalFactory MUST validate all entity invariants before returning entities
- **FR-031**: Validation MUST include required field checks, location bounds, checksum integrity, and reference existence
- **FR-032**: Entity creation MUST fail atomically — a batch either fully validates or returns no entities

## 18. Mandatory Architectural Constraints

### Constraint 1 — Provider Independence

The canonical model MUST be completely independent from:
- Vector databases
- Embedding providers
- LLM providers
- Tree-sitter (AST parsing)
- Retrieval engines

### Constraint 2 — No Knowhere Dependency

The canonical model MUST NOT depend on Knowhere internal types. Adapters perform the conversion between Knowhere types and canonical entities.

### Constraint 3 — Consumer Isolation

All future Syntegrity modules MUST consume canonical entities only. Direct dependency on Knowhere models is prohibited.

### Constraint 4 — Multi-Producer Support

The design MUST support multiple producers:
- Knowhere
- Mem0
- Atlas Native
- External parsers
- Future sources

### Constraint 5 — Deterministic Reconstruction

The design MUST support deterministic reconstruction of indexed repositories from canonical entities alone.



## 19. Key Entities

The following table summarizes the canonical entities and their roles:

| Entity         | Role                                                     | Identifier Source                     |
|----------------|----------------------------------------------------------|---------------------------------------|
| Repository     | Root aggregate for all indexed content                   | source_uri + source label             |
| File           | A single source file or document                         | path + repository_id                  |
| Symbol         | A named code or document symbol                          | qualified_name + repository_id        |
| Chunk          | A contiguous span of text                                | repository_id + file_id + location    |
| Relationship   | A typed edge connecting two entities                     | source_id + target_id + type + repository_id |
| Reference      | An occurrence-based pointer between entities             | source_id + target_id + location + repository_id |


## 20. Success Criteria

### Measurable Outcomes

- **SC-001**: A Repository can be fully reconstructed from its canonical entities without any provider-specific code, completing in under 5 seconds for a repository of 10,000 entities
- **SC-002**: Identical source content indexed through two different providers produces canonical entities with matching `semantic_hash` values for identical text, and identical canonical identifiers for the same file at the same location (verified by automated comparison)
- **SC-003**: _Moved to KNOW-004 Snapshot & Versioning_
- **SC-004**: Adding a new provider adapter requires implementing no more than four adapter contracts (FileAdapter, SymbolAdapter, ChunkAdapter, RelationshipAdapter) and zero changes to the canonical model or existing adapters
- **SC-005**: A consumer that reads canonical entities operates correctly without any knowledge of which provider produced the data — swapping the provider adapter requires no consumer code changes
- **SC-006**: The canonical model version can be independently updated without coordination with any provider's release cycle
- **SC-007**: All 21 acceptance criteria (AC-001 through AC-024, excluding AC-007 through AC-009 moved to KNOW-004) pass for at least two distinct provider adapters
