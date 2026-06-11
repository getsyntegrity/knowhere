# Implementation Plan: KNOW-002 Canonical Knowledge Model

**Branch**: `002-know-002-canonical` | **Date**: 2026-06-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-know-002-canonical/spec.md`

> **Non-normative**: This document describes the Python reference implementation. The canonical contract itself is defined in `spec.md` and `data-model.md` and is implementation-agnostic.

## Summary

Build a provider-agnostic Canonical Knowledge Model that acts as an Anti-Corruption Layer between upstream providers (Knowhere, Mem0, Atlas Native) and Syntegrity consumers (Atlas, MCP). The model defines 6 canonical entities (Repository, File, Symbol, Chunk, Relationship, Reference), a CodeLocation value object, 4 adapter contracts, a CanonicalFactory, a CanonicalRepository query interface, and JSON serialization — implemented in Python 3.11+ with Pydantic v2 and tested with pytest.

Persistence and database backends are out of scope for KNOW-002 and will be addressed in KNOW-004.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Pydantic v2 (entities, validation, serialization), hashlib (identifiers, stdlib), uuid (stdlib)  
**Storage**: None — persistence is out of scope for KNOW-002  
**Testing**: pytest with contract tests  
**Target Platform**: Linux server (project standard)  
**Project Type**: Library (`packages/canonical-knowledge/`)  
**Performance Goals**: Entity creation and query operations within sub-millisecond range for typical entity collections (<10k entities)  
**Constraints**: 6 mandatory architectural constraints (spec §18) — no Knowhere dependency, no vector/embedding/LLM coupling, no persistence dependency  
**Scale/Scope**: 5 entity types, 21 acceptance criteria, 31 functional requirements, single new package in existing monorepo

## Constitution Check

_GATE: Must pass before Phase 0 research. Re-check after Phase 1 design._

**Status**: PASS — The constitution is a template with no active gates defined. The feature plan follows existing project conventions (Python 3.11+, Pydantic v2, pytest) and introduces no violations.

_Re-check after Phase 1_: PASS — All design artifacts align with project structure conventions. No persistence dependencies imposed. No architectural violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-know-002-canonical/
├── plan.md              # This file — overall implementation plan
├── research.md          # Phase 0 — technology decisions and rationale
├── data-model.md        # Detailed entity definitions and query interface
├── quickstart.md        # Quick usage guide
├── spec.md              # Full feature specification (20 sections)
├── contracts/           # Abstract adapter interfaces
│   ├── FileAdapter.py
│   ├── SymbolAdapter.py
│   ├── ChunkAdapter.py
│   └── RelationshipAdapter.py
├── checklists/          # Quality checklists
│   └── requirements.md
└── tasks.md             # Implementation tasks
```

### Source Code (repository root)

```text
packages/canonical-knowledge/          # New library package
├── pyproject.toml                     # Python project config (hatchling/uv)
├── src/
│   └── canonical/                     # Importable as `import canonical`
│       ├── __init__.py
│       ├── entities/                  # All 6 canonical entities
│       │   ├── repository.py
│       │   ├── file.py
│       │   ├── symbol.py
│       │   ├── chunk.py
│       │   ├── relationship.py
│       │   ├── reference.py

│       ├── value_objects/             # Shared value objects
│       │   ├── __init__.py
│       │   └── code_location.py
│       ├── identifiers.py             # IdentifierService (SHA-256, permanent)
│       ├── factory.py                 # CanonicalFactory
│       ├── query.py                   # CanonicalRepository query interface
│       ├── serialization.py           # JsonSerializer
│       ├── adapters/                  # Abstract adapter contracts + stubs
│       │   ├── file_adapter.py
│       │   ├── symbol_adapter.py
│       │   ├── chunk_adapter.py
│       │   ├── relationship_adapter.py
│       │   └── base.py
│       └── exceptions.py              # Canonical model error types
└── tests/
    ├── test_code_location.py          # CodeLocation invariants
    ├── test_entities.py               # All 6 entity invariants
    ├── test_identifiers.py            # Deterministic ID generation
    ├── test_factory.py                # CanonicalFactory validation
    ├── test_serialization.py          # JSON roundtrip and versioning
    ├── test_query.py                  # CanonicalRepository navigation
    ├── contract/                      # Reusable adapter test suites
    │   ├── test_file_adapter.py
    │   ├── test_symbol_adapter.py
    │   ├── test_chunk_adapter.py
    │   └── test_relationship_adapter.py
    └── conftest.py                    # Shared test fixtures
```

**Structure Decision**: New library package at `packages/canonical-knowledge/` — separate from `packages/shared-python/` to enforce Constraint 2 (no Knowhere dependency). Flat file structure (no subdirs for factory/serialization) keeps imports simple. Tests mirror source layout. No persistence directory — out of scope for KNOW-002.

## Implementation Phases

### Phase 1: CodeLocation Value Object

**Goal**: Implement the CodeLocation value object with full invariant validation.

**File**: `canonical/value_objects/code_location.py`

**Deliverables**:
- Pydantic frozen model with `start_line`, `start_column`, `end_line`, `end_column`
- Validation: `start_line ≤ end_line`, column consistency
- `__str__` method for location serialization (e.g., "10:3-25:8")
- Equality semantics, immutability

### Phase 2: Entities (All 6)

**Goal**: Implement all 6 canonical entities as Pydantic v2 frozen models.

**Files**: `canonical/entities/*.py`, `canonical/exceptions.py`

**Deliverables**:
- Repository (sole aggregate root), File, Symbol, Chunk, Relationship, Reference
- Required fields, optional fields, `metadata: dict[str, Any]` on every entity
- Entity-specific invariant validation (unique qualified_name, non-overlapping Chunk locations, etc.)
- deterministic identifier fields (`id: str`) — IDs are computed by IdentifierService (Phase 3)
- Canonical error types: `CanonicalError`, `InvariantViolation`

### Phase 3: IdentifierService

**Goal**: Implement deterministic SHA-256 identifier generation per the permanent public contract.

**File**: `canonical/identifiers.py`

**Deliverables**:
- `IdentifierService` with `generate_repository_id()`, `generate_file_id()`, `generate_symbol_id()`, `generate_chunk_id()`, `generate_relationship_id()`, `generate_reference_id()`
- Input composition per spec §9.2: SHA-256 of UTF-8 concatenation with `|` separator
- Permanent contract — algorithm and input rules MUST NOT change

### Phase 4: CanonicalFactory

**Goal**: Implement entity creation with invariant validation, identifier generation, and batch operations.

**File**: `canonical/factory.py`

**Deliverables**:
- `build_repository()`, `build_file()`, `build_symbol()`, `build_chunk()` — per entity type
- Invariant validation before construction
- Identifier generation via IdentifierService
- `build_batch()` — atomic multi-entity creation with cross-reference validation
- Structured error reporting on validation failure

### Phase 5: Serialization

**Goal**: Implement lossless JSON serialization/deserialization with version markers.

**File**: `canonical/serialization.py`

**Deliverables**:
- `to_json(entity)` and `from_json(json_str)` for all entity types
- Embedded `canonical_model_version` (e.g., "1.0.0")
- Major version mismatch → error
- Minor version → forward-compat (unknown fields ignored)
- Uses Pydantic `model_dump_json()` / `model_validate_json()`

### Phase 6: CanonicalRepository (Query & Navigation)

**Goal**: Implement an in-memory query/navigation interface for consuming canonical entities.

**File**: `canonical/query.py`

**Deliverables**:
- `CanonicalRepository` class operating on in-memory entity collections
- Retrieval by ID: `get_file(id)`, `get_symbol(id)`, `get_chunk(id)`, etc.
- Discovery by relation: `find_symbols(file_id)`, `find_chunks(file_id)`, `find_relationships(source_id)`, etc.
- Repository scope: `get_file_by_path(repo_id, path)`, `get_symbol_by_name(repo_id, qualified_name)`
- Backend-agnostic — no database or storage dependencies
- Stateless — entity collection passed at construction time

### Phase 7: Adapter Contract Tests

**Goal**: Generate reusable contract test suites for all 4 adapter interfaces.

**Files**: `tests/contract/test_*_adapter.py`

**Deliverables**:
- `FileAdapter` contract test suite: validates ID generation, checksum, language fallback
- `SymbolAdapter` contract test suite: validates qualified_name, kind mapping, location bounds
- `ChunkAdapter` contract test suite: validates composite ID, semantic_hash, ordering
- `RelationshipAdapter` contract test suite: validates duplicate rejection, custom types, cross-reference
- In-memory stub adapters for test validation

### Phase 8: Acceptance Criteria Validation

**Goal**: Validate AC-001 through AC-024 (excluding AC-007 through AC-009 moved to KNOW-004).

**File**: `tests/test_acceptance.py`

**Deliverables**:
- Automated tests for all 21 in-scope ACs
- Navigation, determinism, provider equivalence, boundary conditions
- Performance benchmarks for SC-001, SC-002

## Complexity Tracking

No constitutional violations. Single library package, no external dependencies beyond Pydantic.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| None | — | — |
