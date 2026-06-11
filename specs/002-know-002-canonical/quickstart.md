# Quickstart: KNOW-002 Canonical Knowledge Model

**Phase**: 1 — Design & Contracts  
**Date**: 2026-06-11

> **Non-normative**: This document is a quickstart guide for the Python reference implementation. The canonical contract itself is defined in `spec.md` and `data-model.md` and is implementation-agnostic.

## Overview

The Canonical Knowledge Model is an Anti-Corruption Layer (ACL) between upstream providers (Knowhere, Mem0, Atlas Native) and Syntegrity consumers (Atlas, MCP servers, custom tools). It defines 6 canonical entities, 4 adapter contracts, a factory for entity creation and validation, a query interface for navigation, and JSON serialization.

_Persistence and Snapshot lifecycle are out of scope for KNOW-002 and will be addressed in KNOW-004._

## Package Structure (Planned)

```text
packages/canonical-knowledge/
├── pyproject.toml
├── src/
│   └── canonical/
│       ├── __init__.py
│       ├── entities/
│       │   ├── repository.py
│       │   ├── file.py
│       │   ├── symbol.py
│       │   ├── chunk.py
│       │   ├── relationship.py
│       │   └── reference.py
│       ├── value_objects/
│       │   └── code_location.py
│       ├── identifiers.py
│       ├── factory.py
│       ├── query.py
│       ├── serialization.py
│       ├── adapters/
│       │   ├── file_adapter.py
│       │   ├── symbol_adapter.py
│       │   ├── chunk_adapter.py
│       │   └── relationship_adapter.py
│       └── exceptions.py
└── tests/
    ├── test_entities.py
    ├── test_identifiers.py
    ├── test_factory.py
    ├── test_code_location.py
    ├── test_query.py
    ├── test_serialization.py
    └── conftest.py
```

## Canonical Entities (Summary)

| Entity       | Identifier Source                     | Role |
|-------------|---------------------------------------|------|
| Repository  | `source_uri` + `source`               | Sole aggregate root |
| File        | `path` + `repository_id`              | Single source file |
| Symbol      | `qualified_name` + `repository_id`    | Code/document symbol |
| Chunk       | `repository_id` + `file_id` + `location` | Contiguous text span |
| Relationship| `source_id` + `target_id` + `type` + `repository_id` | Typed edge |
| Reference   | `source_id` + `target_id` + `location` + `repository_id` | Occurrence pointer |


### Key Distinction

- **chunk_id** = `sha256(repository_id + "|" + file_id + "|" + location)` → uniqueness within Repository
- **semantic_hash** = `sha256(text_bytes)` → cross-provider deduplication of identical text

## Quick Usage Flow

### Creating Entities

```python
from canonical.entities.repository import Repository

repo = Repository(
    name="my-project",
    source_uri="https://github.com/org/my-project",
    source="knowhere",
)
# Repository is the sole aggregate root; all other entities reference it.
```

### Using the Factory

```python
from canonical.factory import CanonicalFactory

factory = CanonicalFactory()
validated_repo = factory.build_repository(
    name="my-project",
    source_uri="https://github.com/org/my-project",
    source="knowhere",
)
# Factory validates invariants and generates deterministic identifiers
```

### Navigating Entities

```python
from canonical.query import CanonicalRepository

# Create a query interface from a collection of entities
repo_nav = CanonicalRepository(repository=repo, files=files, symbols=symbols)

# Retrieve by ID
file = repo_nav.get_file(file_id)

# Discover by relation
symbols_in_file = repo_nav.find_symbols(file.id)
chunks_in_file = repo_nav.find_chunks(file.id)
relationships_from = repo_nav.find_relationships(symbol.id)

# Repository-scoped lookups
file_by_path = repo_nav.get_file_by_path(repo.id, "src/main.py")
symbol_by_name = repo_nav.get_symbol_by_name(repo.id, "module.ClassName.method")
```

### Implementing an Adapter

```python
from canonical.adapters.file_adapter import FileAdapter
from canonical.entities.file import File

class MyCustomFileAdapter(FileAdapter):
    def to_canonical(self, provider_input, repository_id):
        yield File(
            repository_id=repository_id,
            path=provider_input["path"],
            checksum=hashlib.sha256(provider_input["content"].encode()).hexdigest(),
            size_bytes=len(provider_input["content"]),
            language=provider_input.get("language"),
        )
```

### Serialization

```python
from canonical.serialization import JsonSerializer

serializer = JsonSerializer()
json_str = serializer.to_json(repo)           # Entity → JSON string
restored = serializer.from_json(json_str)     # JSON string → Entity
# Version marker is embedded; major version mismatch raises SerializationError
```

## Key Files

| File | Purpose |
|------|---------|
| `spec.md` | Full feature specification |
| `data-model.md` | Detailed entity definitions, invariants, identifier generation |
| `research.md` | Technology decisions and rationale |
| `contracts/` | Abstract adapter interfaces |
| `checklists/` | Quality checklists |

## Next Steps

1. **Phase 1**: CodeLocation value object
2. **Phase 2**: All 6 entities (Repository, File, Symbol, Chunk, Relationship, Reference)
3. **Phase 3**: IdentifierService with SHA-256 (permanent contract)
4. **Phase 4**: CanonicalFactory with invariant validation
5. **Phase 5**: JsonSerializer with version markers
6. **Phase 6**: CanonicalRepository query/navigation interface
7. **Phase 7**: Adapter contract test suites

See [tasks.md](tasks.md) for the full implementation breakdown.
