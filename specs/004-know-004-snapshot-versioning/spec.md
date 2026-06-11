# Feature Specification: KNOW-004 Snapshot & Versioning

**Feature Branch**: `004-know-004-snapshot-versioning`
**Created**: 2026-06-11
**Status**: Draft
**Input**: Migrate Snapshot entity and lifecycle from KNOW-002 to a dedicated Snapshot & Versioning specification.

## 1. Problem Statement

KNOW-002 Canonical Knowledge Model defines the structural representation of repositories, files, symbols, chunks, relationships, and references. However, Snapshot — a temporal state capture mechanism — was originally embedded within KNOW-002, creating a tension between the structural model (representation) and the temporal model (versioning).

Snapshot management requires concepts (checksums, manifests, lineage, restoration, rollback) that are fundamentally about state history and persistence, not about structural representation. To maintain KNOW-002's strict focus on provider-agnostic representation and navigation, Snapshot must live in its own specification.

## 2. Goals

- Define Snapshot as a first-class entity for capturing the complete canonical state of a Repository at a specific point in time
- Establish Snapshot lifecycle operations: create, verify, restore, rollback
- Enable historical recovery and audit of repository state through Snapshot-based restoration
- Support Snapshot lineage (parent-child relationships) for temporal ordering
- Ensure Snapshot integrity through order-independent aggregate checksums
- Provide a deterministic mechanism for Snapshot comparison and verification

## 3. Non-Goals

- Replacing or modifying the canonical entity definitions in KNOW-002 (Repository, File, Symbol, Chunk, Relationship, Reference)
- Defining new canonical entities or relationships beyond Snapshot
- Designing a new retrieval engine or search system
- Specifying a particular serialization format, database, or persistence technology
- Defining UI components, API endpoints, or user-facing interfaces

## 4. Architecture Overview

KNOW-004 sits as a temporal layer above KNOW-002. It operates on canonical entities produced by KNOW-002 and adds versioning/historical capabilities.

```
┌─────────────────────────────────────────┐
│          KNOW-004 Snapshot & Versioning │
│  (Snapshot entity, lifecycle, lineage,  │
│   checksum, manifest, restore, rollback)│
└────────────────┬────────────────────────┘
                 │ operates on
┌────────────────▼────────────────────────┐
│        KNOW-002 Canonical Knowledge     │
│  (Repository, File, Symbol, Chunk,      │
│   Relationship, Reference)                │
└─────────────────────────────────────────┘
```

**Key architectural properties:**

1. **KNOW-002 purity**: KNOW-002 remains strictly about structural representation and navigation. No temporal or persistence concepts leak into the canonical model.
2. **Layered responsibility**: KNOW-004 consumes canonical entities and produces Snapshot entities. It does not modify canonical entity definitions.
3. **Snapshot as derived index**: A Snapshot is a derived view of canonical entity state at a point in time, not a source of truth.
4. **Storage as authority**: As per the KNOW architecture, Storage is authoritative. Snapshots are derived indices, never reconstruct Storage from Snapshots.

## 5. Domain Model

KNOW-004 defines a single primary entity: **Snapshot**.

### Entity Dependency Graph

```
Repository ──► Snapshot ──► Snapshot (parent lineage)
```

- **Snapshot**: A sealed, timestamped capture of a Repository's complete canonical state at a specific point in time.

## 6. Entity Definitions

### 6.1 Snapshot

A Snapshot captures the complete canonical state of a Repository at a specific point in time.

| Attribute        | Description                                                  | Mutability |
|------------------|--------------------------------------------------------------|------------|
| `id`             | Unique identifier (non-deterministic — e.g., timestamp-based UUID) | Immutable |
| `repository_id`  | Reference to the parent Repository's id                      | Immutable |
| `version_label`  | Human-readable version label (e.g., "v1.0.0", "2026-06-11")  | Immutable |
| `checksum`       | Order-independent aggregate content hash over all entities in the snapshot | Immutable |
| `parent_snapshot_id`| Optional reference to a prior Snapshot id for lineage tracking | Immutable |
| `entity_count`   | Total count of all entities captured in this snapshot         | Immutable |
| `entity_counts`  | Typed entity counters (e.g., files: N, symbols: N, chunks: N, relationships: N, references: N) for lightweight integrity verification | Immutable |
| `created_at`     | Timestamp of snapshot creation                                | Immutable |
| `manifest`       | Inventory of all entity ids and their types included in the snapshot | Immutable |
| `metadata`       | Extensible key-value map (e.g., trigger reason, provider version) | Mutable |

**Invariants:**
- `checksum` must be order-independent (e.g., sorted-hash or XOR-combined): the same set of entities always produces the same checksum regardless of insertion order
- `checksum` must cover all entity content in the snapshot; any change to any entity produces a different checksum
- `id` is globally unique across all Repositories and Snapshots
- A Snapshot is immutable once created — its contents must not change
- `parent_snapshot_id` must, if set, refer to an existing Snapshot and must not create circular lineage

### 6.2 ManifestEntry

| Field   | Type | Description |
|---------|------|-------------|
| id      | str  | Entity ID   |
| type    | str  | Entity type ("file", "symbol", "chunk", "relationship", "reference") |

## 7. Relationship Definitions

### 7.1 Entity Relationship Matrix

| Relationship Type      | Source           | Target           | Cardinality | Description |
|------------------------|----------------------|--------------------|-------------|-------------|
| `precedes`             | Snapshot         | Snapshot           | Temporal ordering of snapshots |

### 7.2 Relationship Cardinality

| From         | To           | Cardinality | Notes |
|--------------|-------------|-------------|-------|
| Repository   | Snapshot     | 1:N         | A Repository may have many Snapshots |
| Snapshot     | Snapshot     | N:1         | Each Snapshot has at most one parent |

## 8. Snapshot Lifecycle

### 8.1 Create

**Operation**: `create_snapshot(repository, version_label, metadata=None)`

**Input**: A Repository with all its canonical entities (Files, Symbols, Chunks, Relationships, References).

**Output**: A Snapshot entity.

**Process**:
1. Collect all canonical entities from the Repository
2. Compute `entity_count` and `entity_counts` (per-type counters)
3. Build `manifest` (list of all entity IDs and types)
4. Compute `checksum` (order-independent aggregate hash of all entity content)
5. Generate `id` (non-deterministic UUID)
6. Set `created_at` to current timestamp
7. Set optional `parent_snapshot_id` to the most recent prior Snapshot
8. Return immutable Snapshot

### 8.2 Verify

**Operation**: `verify_snapshot(snapshot, repository)`

**Input**: A Snapshot and a Repository (or the entity collection it claims to represent).

**Output**: Verification result (pass/fail) with detailed mismatch report if failed.

**Process**:
1. Recompute `checksum` from the provided entity collection
2. Compare with `snapshot.checksum`
3. Compare `entity_count` and `entity_counts` with actual counts
4. Verify all entity IDs in `manifest` exist in the collection
5. Report any mismatches

### 8.3 Restore

**Operation**: `restore_snapshot(snapshot)`

**Input**: A Snapshot.

**Output**: The canonical entity collection as it existed at the time of the Snapshot.

**Process**:
1. Read `manifest` to identify all entities
2. Reconstruct the entity graph from the Snapshot's stored data
3. Verify reconstructed graph matches `snapshot.checksum`
4. Return the entity collection

### 8.4 Rollback

**Operation**: `rollback_to_snapshot(repository, snapshot_id)`

**Input**: A Repository and a Snapshot ID.

**Output**: The Repository restored to the state captured by the Snapshot.

**Process**:
1. Retrieve the Snapshot by `snapshot_id`
2. Verify the Snapshot
3. Restore the canonical entity collection from the Snapshot
4. Replace the Repository's current entity collection with the restored state
5. Update the Repository's metadata to reflect the rollback

## 9. Serialization Requirements

### 9.1 Principles

- Snapshot serialization MUST be lossless and include all entity content
- Snapshot serialization MUST embed the canonical model version (from KNOW-002)
- Snapshot serialization MUST include a Snapshot version marker for forward/backward compatibility

### 9.2 Format Requirements

- The Snapshot format MUST support all six canonical entity types (from KNOW-002)
- The Snapshot format MUST include the manifest and checksum for integrity verification
- The Snapshot format MUST support compression for storage and transmission efficiency

## 10. Acceptance Criteria

### 10.1 Snapshot Creation

- **AC-007**: Snapshot reproduces exact historical index state — creating a Snapshot from a Repository and restoring it produces an identical entity graph
- **AC-008**: Restored graph has same aggregate checksum — the restored entity collection produces the same `checksum` as the original Snapshot

### 10.2 Snapshot Rollback

- **AC-009**: Repository rollback to prior Snapshot — rolling back to a previous Snapshot restores the Repository to the exact state captured at that time

### 10.3 Snapshot Integrity

- **AC-SV-001**: A Snapshot with a corrupted entity produces a different checksum on verification
- **AC-SV-002**: A Snapshot's manifest accurately lists all entity IDs and types
- **AC-SV-003**: Snapshot lineage (parent-child chain) is preserved without circular references

### 10.4 Performance

- **SC-003**: Snapshot creation and verification complete in under 5 seconds for a repository of 10,000 entities

## 11. Migration from KNOW-002

### 11.1 What Moved

The following content was removed from KNOW-002 and migrated to KNOW-004:

- **Entity definition**: Snapshot (§6.7 in KNOW-002)
- **Value object**: ManifestEntry
- **Relationship**: `precedes` (Snapshot → Snapshot)
- **Relationship cardinality**: Repository → Snapshot, Snapshot → Snapshot
- **Acceptance criteria**: AC-007, AC-008, AC-009
- **Success criteria**: SC-003
- **Functional requirement**: FR-008 (Snapshot identifier rule)
- **User Story**: User Story 3 — Platform Engineer Recovering from Snapshot
- **Constraint**: Constraint 6 — Snapshot Reproducibility

### 11.2 What Remains in KNOW-002

- **Repository**: Still the sole aggregate root, but no longer carries a `snapshots` collection
- **Serialization**: KNOW-002 serialization handles the six canonical entities; Snapshot serialization is a KNOW-004 concern
- **Query interface**: `CanonicalRepository` no longer has `get_snapshot()` — Snapshot queries belong to KNOW-004

## 12. Future Compatibility

- New canonical entity types added to KNOW-002 (e.g., MemoryFact, DomainConcept) will automatically be supported by Snapshot if they follow the canonical entity pattern (deterministic id, required fields, metadata)
- Snapshot versioning is independent of canonical model versioning
- Snapshot format may evolve independently of KNOW-002 serialization format

## 13. Success Criteria

### Measurable Outcomes

- **SC-003**: Snapshot creation and verification complete in under 5 seconds for a repository of 10,000 entities
- **SC-SV-001**: A Snapshot can be created, verified, restored, and rolled back without data loss
- **SC-SV-002**: Snapshot lineage supports at least 100 sequential Snapshots without performance degradation

## 14. Functional Requirements

### 14.1 Snapshot Entity Requirements

- **FR-SV-001**: The Snapshot entity MUST capture all canonical entities (Repository, File, Symbol, Chunk, Relationship, Reference) at a point in time
- **FR-SV-002**: Snapshot identifiers MUST be non-deterministic (e.g., UUID or timestamp-based) and globally unique
- **FR-SV-003**: Snapshot checksums MUST be order-independent and cover all entity content
- **FR-SV-004**: Snapshot manifests MUST accurately inventory all entity IDs and types

### 14.2 Lifecycle Requirements

- **FR-SV-005**: Snapshot creation MUST produce an immutable Snapshot with accurate checksum and manifest
- **FR-SV-006**: Snapshot verification MUST detect any entity modification since creation
- **FR-SV-007**: Snapshot restoration MUST return the exact entity collection captured at creation time
- **FR-SV-008**: Snapshot rollback MUST restore the Repository to the exact state captured by the Snapshot

### 14.3 Lineage Requirements

- **FR-SV-009**: Snapshot lineage MUST support parent-child relationships without circular references
- **FR-SV-010**: Snapshot lineage MUST support temporal ordering via the `precedes` relationship

## 15. Constraints

### Constraint 1 — KNOW-002 Purity

KNOW-004 MUST NOT modify or extend KNOW-002 canonical entity definitions. It operates on them as a consumer.

### Constraint 2 — Storage Authority

Snapshots are derived indices. The canonical entity Storage (as defined in KNOW-002 persistence) is the authoritative source of truth. Snapshots MUST NOT be used to reconstruct Storage.

### Constraint 3 — Deterministic Checksums

Snapshot checksums MUST be deterministic: the same set of canonical entities always produces the same checksum regardless of insertion order or serialization format.

## 16. Key Entities

| Entity         | Role                                                     | Identifier Source                     |
|----------------|----------------------------------------------------------|---------------------------------------|
| Snapshot       | A sealed, timestamped capture of repository state        | Generated (non-deterministic)         |

## 17. Dependencies

- **KNOW-002**: Canonical Knowledge Model (entities, relationships, serialization)
- **KNOW-003**: Parsing & Symbol Extraction (produces canonical entities that Snapshots capture)

## 18. Notes

- This specification was created as part of ARCH-001 to maintain the Canonical Knowledge Model's strict focus on representation and navigation.
- Snapshot was originally defined in KNOW-002 §6.7 but has been migrated here to preserve KNOW-002's single responsibility.
