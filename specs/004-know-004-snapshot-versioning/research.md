# Research: KNOW-004 Snapshot & Versioning

**Phase**: 0 — Outline & Research
**Date**: 2026-06-11
**Spec**: [spec.md](spec.md)

## Technology Decisions

### Decision 1: Language & Runtime

**Decision**: Python 3.11+
**Rationale**: Existing Knowhere project standard; team expertise; Pydantic v2 ecosystem.

### Decision 2: Entity Definition Framework

**Decision**: Pydantic v2 BaseModel
**Rationale**: Same as KNOW-002 — frozen models, validation, serialization.

### Decision 3: Checksum Algorithm

**Decision**: Order-independent aggregate hash using XOR-combined SHA-256
**Rationale**: Order-independence is critical for Snapshot integrity. Two approaches considered:
- **Sorted-hash**: Sort entities by ID, hash concatenated bytes. Simple but requires sorting.
- **XOR-combined**: Hash each entity individually, XOR all hashes. Order-independent, parallelizable.
**Selected**: XOR-combined SHA-256 for its simplicity and parallelization potential.

### Decision 4: Identifier Strategy

**Decision**: UUID4 for Snapshot IDs
**Rationale**: Snapshots are temporal state captures, not structural entities. UUID4 provides global uniqueness without coordination. Non-determinism is intentional — the same Repository state captured twice at different times should produce different Snapshot IDs.

### Decision 5: Package Location

**Decision**: New package at `packages/snapshot-versioning/`
**Rationale**: Enforces KNOW-002 purity constraint. Snapshot operates on canonical entities as a consumer layer. Separate package prevents tight coupling.

## Dependency Analysis

| Dependency | Version | Purpose | Internal/External |
|------------|---------|---------|-------------------|
| Python     | 3.11+   | Runtime | External |
| Pydantic   | v2      | Snapshot entity definition | External |
| hashlib    | stdlib  | Checksum computation | Internal (stdlib) |
| uuid       | stdlib  | Snapshot identifiers | Internal (stdlib) |
| KNOW-002   | —       | Canonical entities (Repository, File, Symbol, Chunk, Relationship, Reference) | Internal (project) |
| pytest     | 7+      | Testing | Dev external |

## Integration Patterns

### Snapshot as Consumer Layer

KNOW-004 consumes canonical entities from KNOW-002 and produces Snapshot entities. It does not modify or extend canonical entity definitions.

```python
# Conceptual pattern
from canonical.entities.repository import Repository
from snapshot.lifecycle import SnapshotLifecycle

lifecycle = SnapshotLifecycle()
snapshot = lifecycle.create_snapshot(
    repository=repo,
    version_label="v1.0.0",
)
```

### Checksum Verification

Checksums are computed over the canonical entity content, not the Snapshot metadata. This ensures that a Snapshot accurately represents the canonical state at a point in time.

## Unresolved Items

All spec-level decisions are resolved. Implementation-level decisions deferred:

1. **Streaming serialization for large Snapshots** — Implementation detail for repositories with >100k entities
2. **Differential Snapshots** — Future enhancement: store only changed entities between Snapshots
3. **Snapshot compression** — Implementation detail for storage efficiency

## Migration Notes

This specification was created as part of ARCH-001 to migrate Snapshot from KNOW-002 to a dedicated specification. The following content was migrated:

- Snapshot entity definition (§6.7)
- ManifestEntry value object
- `precedes` relationship type
- Snapshot lifecycle (create, verify, restore, rollback)
- Acceptance criteria: AC-007, AC-008, AC-009
- Success criteria: SC-003
- Functional requirement: FR-008
- User Story: Platform Engineer Recovering from Snapshot
- Constraint: Snapshot Reproducibility
