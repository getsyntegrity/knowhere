# Data Model: KNOW-002 Canonical Knowledge Model

**Phase**: 1 — Design & Contracts  
**Date**: 2026-06-11  
**Spec**: [spec.md](spec.md)  

## Aggregate Root

**Repository** is the sole aggregate root. All other entities (File, Symbol, Chunk, Relationship, Reference) exist within a Repository boundary and are never persisted or retrieved independently. Operations on entities always scope to a Repository.

## Value Objects

### CodeLocation

Represents a source location span within a File.

| Field          | Type    | Constraints                           |
|----------------|---------|---------------------------------------|
| start_line     | int     | ≥ 1, ≤ end_line                       |
| start_column   | int     | ≥ 1, ≤ end_column if start_line==end_line |
| end_line       | int     | ≥ 1, ≥ start_line                     |
| end_column     | int     | ≥ 1                                   |

**Invariants**: `start_line ≤ end_line`; if equal, `start_column ≤ end_column`. All positive. Must be within parent File bounds.

## Entities

### Repository

| Field       | Type         | Required | Immutable | Description |
|-------------|--------------|----------|-----------|-------------|
| id          | str          | Y        | Y         | `sha256(source_uri + "|" + source)` |
| name        | str          | Y        | N         | Human-readable name |
| source_uri  | str          | Y        | Y         | Provider-specific origin URI |
| source      | str          | Y        | Y         | Provider label (e.g., "knowhere") |
| files       | list[File]   | N        | N         | Child file collection |
| created_at  | datetime     | Y        | Y         | First ingestion timestamp |
| metadata    | dict[str,Any]| N        | N         | Extensible attributes |

### File

| Field         | Type              | Required | Immutable | Description |
|---------------|-------------------|----------|-----------|-------------|
| id            | str               | Y        | Y         | `sha256(path + "|" + repository_id)` |
| repository_id | str               | Y        | Y         | Parent Repository.id |
| path          | str               | Y        | Y         | Relative path within repository |
| language      | str\|None         | N        | N         | Language label ("python", or None) |
| checksum      | str               | Y        | Y         | `sha256(file_content_bytes)` |
| size_bytes    | int               | Y        | Y         | Source file size |
| symbols       | list[Symbol]      | N        | N         | Symbols defined in this file |
| chunks        | list[Chunk]       | N        | N         | Chunks extracted from this file |
| references    | list[Reference]   | N        | N         | References originating in this file |
| metadata      | dict[str,Any]     | N        | N         | Extensible attributes |

### Symbol

| Field          | Type              | Required | Immutable | Description |
|----------------|-------------------|----------|-----------|-------------|
| id             | str               | Y        | Y         | `sha256(qualified_name + "|" + repository_id)` |
| file_id        | str               | Y        | Y         | Parent File.id |
| repository_id  | str               | Y        | Y         | Parent Repository.id |
| name           | str               | Y        | Y         | Local name |
| qualified_name | str               | Y        | Y         | Fully qualified name (unique per repo) |
| kind           | str               | Y        | Y         | Symbol kind ("function", "class", etc.) |
| scope          | str\|None         | N        | N         | Parent scope identifier |
| location       | CodeLocation      | Y        | Y         | Source location |
| signature      | str\|None         | N        | N         | Callable signature text |
| documentation  | str\|None         | N        | N         | Docstring/comment |
| children       | list[str]         | N        | N         | Child Symbol IDs |
| metadata       | dict[str,Any]     | N        | N         | Extensible attributes |

### Chunk

| Field          | Type              | Required | Immutable | Description |
|----------------|-------------------|----------|-----------|-------------|
| id             | str               | Y        | Y         | `sha256(repository_id + "|" + file_id + "|" + location)` |
| file_id        | str               | Y        | Y         | Parent File.id |
| repository_id  | str               | Y        | Y         | Parent Repository.id |
| text           | str               | Y        | Y         | Raw chunk text |
| location       | CodeLocation      | Y        | Y         | Source location |
| semantic_hash  | str               | Y        | Y         | `sha256(text_bytes)` — semantic equivalence contract (cross-provider dedup) |
| chunk_type     | str               | Y        | Y         | Semantic type label |
| checksum       | str               | Y        | Y         | `sha256(text_bytes)` — integrity contract (self-verification; same algorithm as semantic_hash in default impl) |
| ordering       | int               | Y        | Y         | Ordinal position in file |
| symbol_ids     | list[str]         | N        | N         | Referenced Symbol IDs |
| metadata       | dict[str,Any]     | N        | N         | Extensible attributes |

**Identity vs Semantics**: `id` is derived from (repository_id, file_id, location) for uniqueness within a Repository. `semantic_hash` is derived from `text` only for cross-provider deduplication. Two chunks with identical `semantic_hash` but different `id` represent semantically identical text at different locations.

**Hash Distinction**: `semantic_hash` and `checksum` serve distinct contracts even though both use SHA-256 in the default implementation. `semantic_hash` is a semantic equivalence primitive (cross-provider deduplication); `checksum` is an integrity primitive (self-verification). Future implementations may use different algorithms for each. They MUST NOT be treated as interchangeable.

### Relationship

| Field         | Type              | Required | Immutable | Description |
|---------------|-------------------|----------|-----------|-------------|
| id            | str               | Y        | Y         | `sha256(source_id + "|" + target_id + "|" + type + "|" + repository_id)` |
| repository_id | str               | Y        | Y         | Parent Repository.id |
| source_id     | str               | Y        | Y         | Source entity ID |
| target_id     | str               | Y        | Y         | Target entity ID |
| type          | str               | Y        | Y         | Relationship type label |
| weight        | float\|None       | N        | N         | Optional strength (0.0–1.0) |
| attributes    | dict[str,Any]\|None| N       | N         | Typed attribute map |
| metadata      | dict[str,Any]     | N        | N         | Extensible attributes |

**Cardinality**: Duplicate (source_id, target_id, type) tuples are not permitted within a Repository.

### Reference

| Field          | Type              | Required | Immutable | Description |
|----------------|-------------------|----------|-----------|-------------|
| id             | str               | Y        | Y         | `sha256(source_id + "|" + target_id + "|" + location + "|" + repository_id)` |
| repository_id  | str               | Y        | Y         | Parent Repository.id |
| source_id      | str               | Y        | Y         | Originating entity ID |
| target_id      | str               | Y        | Y         | Referenced entity ID |
| source_file_id | str               | Y        | Y         | Originating File.id |
| target_file_id | str               | Y        | Y         | Referenced File.id |
| location       | CodeLocation      | Y        | Y         | Source location |
| context        | str\|None         | N        | N         | Surrounding text snippet |
| role           | str               | Y        | Y         | Semantic role ("import", "call", etc.) |
| metadata       | dict[str,Any]     | N        | N         | Extensible attributes |

## Relationship Type Catalog

| Type              | Source           | Target           | Cardinality | Description |
|-------------------|------------------|------------------|-------------|-------------|
| contains          | Repository       | File             | 1:N         | Repository-to-file containment |
| contains          | File             | Chunk            | 1:N         | File-to-chunk containment |
| contains          | File             | Symbol           | 1:N         | File-to-symbol containment |
| contains          | Symbol           | Symbol           | 1:N         | Parent-child symbol nesting |
| references        | Chunk            | Symbol           | N:M         | Chunk text references a symbol |
| references        | Reference        | Entity           | N:M         | Reference points to any entity |
| imports           | File/Chunk       | File/Symbol      | N:M         | Dependency/import relationship |
| calls             | Symbol           | Symbol           | N:M         | Function/method call |
| extends           | Symbol           | Symbol           | N:M         | Inheritance |
| implements        | Symbol           | Symbol           | N:M         | Implementation |
| defines           | Chunk            | Symbol           | N:M         | Definition location |
| annotates         | Entity           | Entity           | N:M         | Metadata annotation |
| derives_from      | Chunk            | Chunk            | N:M         | Content derivation |
| equivalent_to     | Entity           | Entity           | N:M         | Cross-provider equivalence |


## Identifier Generation

All deterministic identifiers use `sha256(canonical_string)` where `canonical_string` is a UTF-8 encoded concatenation of input fields separated by `|`. The separator `|` is chosen as a character that cannot appear in hashes and is unlikely in most field values.

| Entity       | Input Fields                                  |
|--------------|-----------------------------------------------|
| Repository   | `source_uri` + `\|` + `source`                |
| File         | `path` + `\|` + `repository_id`               |
| Symbol       | `qualified_name` + `\|` + `repository_id`     |
| Chunk        | `repository_id` + `\|` + `file_id` + `\|` + `location.start_line + ":" + location.start_column + "-" + location.end_line + ":" + location.end_column` |
| Relationship | `source_id` + `\|` + `target_id` + `\|` + `type` + `\|` + `repository_id` |
| Reference    | `source_id` + `\|` + `target_id` + `\|` + location.to_string() + `\|` + `repository_id` |


The hashing algorithm and identifier input composition rules are part of the public Canonical Knowledge Model contract. They are permanent and MUST NOT change after release. SHA-256 is the sole identifier algorithm.

_Snapshot checksum, manifest, and lifecycle (create/verify/restore/rollback) are moved to KNOW-004 Snapshot & Versioning._

## Query & Navigation

The `CanonicalRepository` provides an in-memory query interface for navigating canonical entities. It is backend-agnostic and operates on entity collections passed at construction time. Direct retrieval of child entities (e.g., `get_file(file_id)`, `get_symbol(symbol_id)`) is a navigation and analysis convenience; it does not imply independent lifecycle, ownership, or persistence outside the Repository boundary.

### Retrieval by ID

- `get_file(file_id)` → File or raises
- `get_symbol(symbol_id)` → Symbol or raises
- `get_chunk(chunk_id)` → Chunk or raises
- `get_relationship(relationship_id)` → Relationship or raises
- `get_reference(reference_id)` → Reference or raises
- `get_repository(repository_id)` → Repository or raises

### Discovery by Relation

- `find_symbols(file_id)` → list[Symbol]
- `find_chunks(file_id)` → list[Chunk] (in ordering)
- `find_references(file_id)` → list[Reference]
- `find_relationships(source_id)` → list[Relationship]
- `find_relationships_by_target(target_id)` → list[Relationship]
- `find_entities_by_type(entity_type)` → list[Entity]

### Repository Scope

- `get_file_by_path(repository_id, path)` → File or raises
- `get_symbol_by_name(repository_id, qualified_name)` → Symbol or raises

## Validation Rules

### Entity Invariants

Each entity's validation rules (from spec §6):

- **Repository**: id reproducible from source_uri + source; name and source_uri required
- **File**: id reproducible from path + repository_id; path unique per Repository; checksum reproducible
- **Symbol**: qualified_name unique per Repository; location within File bounds; no circular children
- **Chunk**: id reproducible from (repository_id, file_id, location); semantic_hash from text only; no overlapping locations within File; unique ordering
- **Relationship**: id from (source_id, target_id, type, repository_id); no duplicate tuples; self-references OK
- **Reference**: id from (source_id, target_id, location, repository_id); multiple refs between same entities at different locations are distinct


### Factory Validation

The CanonicalFactory performs, in order:

1. Required field presence
2. Field type and format validation
3. Invariant validation per entity type
4. Cross-entity reference existence against the **complete batch graph**
   - Forward references inside the same batch are **valid** (e.g., Relationship.source_id points to a Symbol that is also created in the same batch)
   - References outside the batch must **already exist** (e.g., a Relationship referencing a Repository that is not in the batch must have been previously created)
5. Duplicate identifier detection
6. Atomic batch validation (all-or-nothing)

## State Transitions

- **Entities**: All entity fields are immutable except metadata, symbol_ids, children, weight, context, documentation, signature, scope, and language. Create → (Read | Update metadata) → (Read forever, scope is within Repository).
- **Repository**: Created when first ingested. Updated (add files).

_Snapshot lifecycle (creation, verification, restoration, rollback) is moved to KNOW-004._
