# Research: KNOW-002 Canonical Knowledge Model

**Phase**: 0 — Outline & Research
**Date**: 2026-06-11
**Spec**: [spec.md](spec.md)

> **Non-normative**: This document describes the Python reference implementation for the Canonical Knowledge Model. The canonical contract itself is defined in `spec.md` and `data-model.md` and is implementation-agnostic.

## Technology Decisions

### Decision 1: Language & Runtime

**Decision**: Python 3.11+  
**Rationale**: Existing Knowhere project standard; team expertise; Pydantic v2 ecosystem for clean entity definitions.  
**Alternatives considered**: Rust (would need separate build toolchain, mismatches project stack), TypeScript (would break the Python monorepo convention).

### Decision 2: Entity Definition Framework

**Decision**: Pydantic v2 BaseModel  
**Rationale**: Native support for immutable models (frozen=True), validation (field_validator), serialization (model_dump_json), and schema generation (model_json_schema). Aligns with existing Knowhere convention (`packages/shared-python/shared/models/schemas/`).  
**Alternatives considered**: Python dataclasses (no built-in validation), attrs (less ecosystem integration).

### Decision 3: Identifier Hashing

**Decision**: SHA-256 (permanent)  
**Rationale**: Collision-resistant, well-understood, standard library (hashlib). SHA-256 is a NIST-standard hash with no known practical collision attacks. Identifier generation is part of the public Canonical Knowledge Model contract; once released, the algorithm and input composition rules MUST NOT change. SHA-256 provides a safe, future-proof default.  
**Alternatives considered**: BLAKE3 (faster but non-standard library), MD5 (too weak), SHA-1 (deprecated).  
**Implementation**: `hashlib.sha256(input_bytes).hexdigest()` — input format is a canonical byte string concatenation of the identifier components.

### Decision 4: Abstract Interfaces

**Decision**: Python abc.ABC with @abstractmethod  
**Rationale**: Python-native contract enforcement; all existing Knowhere provider interfaces use this pattern.  
**Alternatives considered**: Protocol classes (structural subtyping), typing.Protocol (useful but less explicit contract enforcement).

### Decision 5: Testing Framework

**Decision**: pytest with contract test pattern  
**Rationale**: Existing project standard. Contract tests validate adapter interfaces against the canonical model invariants. Entity unit tests validate each entity definition.  
**Key test areas**:  
- Entity invariant tests (all 6 entities, all field constraints)  
- Identifier determinism tests (same input → same ID)  
- CodeLocation value object tests  
- CanonicalFactory batch validation tests  
- Adapter contract tests (one suite per adapter)

### Decision 7: Package Location

**Decision**: New package at `packages/canonical-knowledge/`  
**Rationale**: The spec mandates the canonical model MUST NOT depend on Knowhere internal types. A separate package enforces this boundary at the dependency level.  
**Package name**: `knowhere-canonical` (PyPI) / `canonical` (Python import)  
**Path**: `packages/canonical-knowledge/`  
**Alternatives considered**: Adding to `packages/shared-python/shared/models/` (would violate Constraint 2 — no Knowhere dependency), standalone repo (premature for this scope).

### Decision 8: Serialization Format

**Decision**: Pydantic v2 JSON serialization  
**Rationale**: Zero additional dependencies; Pydantic provides `model_dump_json()` and `model_validate_json()` natively. Version marker embedded via a `model_version` attribute.  
**Note**: The spec requires portable, language-independent serialization. JSON is the baseline; future formats (Protobuf, MessagePack) can be added via the serialization interface.

### Decision 9: Versioning Strategy

**Decision**: Embedded model version in serialized entities, aligned with spec §15.6  
**Rationale**: Each entity or collection carries `canonical_model_version` (e.g., "1.0.0"). Major version mismatches cause deserialization rejection. Minor version differences preserve forward compatibility via unknown field ignore.

## Dependency Analysis

| Dependency | Version | Purpose | Internal/External |
|------------|---------|---------|-------------------|
| Python     | 3.11+   | Runtime | External |
| Pydantic   | v2      | Entity definitions, validation, serialization | External |
| hashlib    | stdlib  | Deterministic identifiers | Internal (stdlib) |
| abc        | stdlib  | Abstract adapter and factory contracts | Internal (stdlib) |
| uuid       | stdlib  | General utility identifiers | Internal (stdlib) |
| pytest     | 7+      | Testing | Dev external |
_Persistence (SQLAlchemy, PostgreSQL) is out of scope for KNOW-002 and will be addressed in KNOW-004._

## Integration Patterns

### Provider Adapter Pattern

Each upstream system (Knowhere, Mem0, Atlas Native) implements adapter interfaces that convert provider-internal types to canonical entities. The adapter never leaks provider types into the canonical layer — it is the sole bridge.

```python
# Pattern (conceptual, not code — implementation in KNOW-003)
class KnowhereFileAdapter(FileAdapter):
    def to_canonical(self, provider_input) -> File:
        # Convert Knowhere internal file metadata → canonical File
        ...
```

### Factory Pattern

CanonicalFactory is a stateless orchestrator: it receives normalized data from adapters, validates invariants, generates identifiers, and returns fully-validated canonical entities. It has no provider-specific imports.

### Query Pattern

`CanonicalRepository` is an in-memory query/navigation abstraction. It operates on entity collections passed at construction time and provides retrieval by ID and discovery by relation. It is backend-agnostic and has no database, storage, or persistence dependencies.

## Unresolved Items

All spec-level NEEDS CLARIFICATION markers were resolved during the clarify session (2026-06-11). The following implementation-level decisions are deferred:

1. **Mem0 adapter** — Requires Mem0 API surface knowledge; deferred to KNOW-004 or later
2. **Atlas Native adapter** — Requires Atlas internal model definition; deferred to Atlas specification
3. **Tree-sitter symbol extraction** — Belongs to KNOW-003 Parsing & Symbol Extraction
4. **Serialization streaming protocol** — Implementation detail for large collections; deferred to implementation
