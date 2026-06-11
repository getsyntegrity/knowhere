# Implementation Plan: KNOW-004 Snapshot & Versioning

**Branch**: `004-know-004-snapshot-versioning` | **Date**: 2026-06-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/004-know-004-snapshot-versioning/spec.md`

## Summary

Build Snapshot & Versioning capabilities on top of KNOW-002 Canonical Knowledge Model. Define the Snapshot entity, its lifecycle operations (create, verify, restore, rollback), and Snapshot lineage. Snapshot operates on canonical entities as a consumer — it does not modify or extend KNOW-002 entity definitions.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Pydantic v2 (Snapshot entity), hashlib (checksums, stdlib), uuid (Snapshot IDs, stdlib)
**Testing**: pytest
**Target Platform**: Linux server (project standard)
**Project Type**: Library (`packages/snapshot-versioning/`)
**Performance Goals**: Snapshot creation and verification < 5 seconds for 10,000 entities
**Constraints**: 3 mandatory constraints (spec §15) — KNOW-002 purity, Storage authority, Deterministic checksums

## Constitution Check

**Status**: PASS — The feature introduces no architectural violations. It operates on KNOW-002 canonical entities as a consumer layer.

## Project Structure

### Documentation (this feature)

```text
specs/004-know-004-snapshot-versioning/
├── plan.md              # This file — overall implementation plan
├── data-model.md        # Detailed entity definitions and lifecycle
├── spec.md              # Full feature specification
├── checklists/          # Quality checklists
└── tasks.md             # Implementation tasks
```

### Source Code (repository root)

```text
packages/snapshot-versioning/          # New library package
├── pyproject.toml                     # Python project config
├── src/
│   └── snapshot/                      # Importable as `import snapshot`
│       ├── __init__.py
│       ├── entities/
│       │   ├── snapshot.py            # Snapshot entity
│       │   └── manifest_entry.py      # ManifestEntry value object
│       ├── lifecycle.py               # SnapshotLifecycle (create, verify, restore, rollback)
│       ├── checksum.py                # ChecksumService (order-independent aggregate hash)
│       ├── lineage.py                 # SnapshotLineage (parent-child, precedes)
│       ├── exceptions.py              # Snapshot-specific error types
│       └── serialization.py           # Snapshot serialization/deserialization
└── tests/
    ├── test_snapshot_entity.py        # Snapshot entity invariants
    ├── test_lifecycle.py              # Create, verify, restore, rollback
    ├── test_checksum.py               # Order-independent checksum verification
    ├── test_lineage.py                # Parent-child, circular reference prevention
    └── conftest.py                    # Shared test fixtures
```

**Structure Decision**: New library package at `packages/snapshot-versioning/` — separate from `packages/canonical-knowledge/` to enforce KNOW-002 purity. No direct dependency on canonical-knowledge package (operates on canonical entities via interface).

## Implementation Phases

### Phase 1: Snapshot Entity & ManifestEntry

**Goal**: Implement Snapshot and ManifestEntry as Pydantic v2 frozen models.

**Files**: `snapshot/entities/snapshot.py`, `snapshot/entities/manifest_entry.py`

**Deliverables**:
- Snapshot with all fields (id, repository_id, version_label, checksum, parent_snapshot_id, entity_count, entity_counts, created_at, manifest, metadata)
- ManifestEntry with id and type
- Immutable creation semantics

### Phase 2: ChecksumService

**Goal**: Implement order-independent aggregate checksum for canonical entity collections.

**File**: `snapshot/checksum.py`

**Deliverables**:
- `compute_checksum(entities)` → order-independent hash
- XOR-combined or sorted-hash approach
- Coverage of all entity content

### Phase 3: Snapshot Lifecycle

**Goal**: Implement create, verify, restore, and rollback operations.

**File**: `snapshot/lifecycle.py`

**Deliverables**:
- `create_snapshot(repository, version_label, metadata=None)` → Snapshot
- `verify_snapshot(snapshot, entities)` → VerificationResult
- `restore_snapshot(snapshot)` → EntityCollection
- `rollback_to_snapshot(repository, snapshot_id)` → Restored Repository

### Phase 4: Snapshot Lineage

**Goal**: Implement parent-child lineage tracking and `precedes` relationship.

**File**: `snapshot/lineage.py`

**Deliverables**:
- `get_parent(snapshot)` → Optional[Snapshot]
- `get_lineage(snapshot)` → List[Snapshot] (ancestor chain)
- Circular reference detection and prevention

### Phase 5: Serialization

**Goal**: Implement Snapshot serialization with version markers.

**File**: `snapshot/serialization.py`

**Deliverables**:
- `to_json(snapshot)` → JSON string
- `from_json(json_str)` → Snapshot
- Embedded canonical model version and Snapshot version

### Phase 6: Acceptance Criteria Validation

**Goal**: Validate AC-007, AC-008, AC-009, and AC-SV-001 through AC-SV-003.

**File**: `tests/test_acceptance.py`

**Deliverables**:
- Snapshot creation and verification tests
- Restoration and rollback tests
- Lineage and circular reference tests
- Performance benchmarks for SC-003

## Complexity Tracking

No constitutional violations. Single library package, no external dependencies beyond Pydantic.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| None | — | — |
