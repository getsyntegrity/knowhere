# Data Model: KNOW-004 Snapshot & Versioning

**Phase**: 1 — Design & Contracts
**Date**: 2026-06-11
**Spec**: [spec.md](spec.md)

## Dependencies

This specification depends on KNOW-002 Canonical Knowledge Model for all canonical entity definitions (Repository, File, Symbol, Chunk, Relationship, Reference).

## Entities

### Snapshot

| Field               | Type              | Required | Immutable | Description |
|---------------------|-------------------|----------|-----------|-------------|
| id                  | str               | Y        | Y         | `uuid4()` (non-deterministic) |
| repository_id       | str               | Y        | Y         | Parent Repository.id |
| version_label       | str               | Y        | Y         | Human-readable version |
| checksum            | str               | Y        | Y         | Order-independent aggregate hash of all entities |
| parent_snapshot_id  | str\|None         | N        | Y         | Previous Snapshot ID |
| entity_count        | int               | Y        | Y         | Total entity count |
| entity_counts       | dict[str,int]     | Y        | Y         | Per-type entity counts |
| created_at          | datetime          | Y        | Y         | Creation timestamp |
| manifest            | ManifestEntry[]   | Y        | Y         | All entity IDs and their types |
| metadata            | dict[str,Any]     | N        | N         | Extensible attributes |

### ManifestEntry

| Field   | Type | Description |
|---------|------|-------------|
| id      | str  | Entity ID   |
| type    | str  | Entity type ("file", "symbol", "chunk", "relationship", "reference") |

## Relationship Type Catalog

| Type              | Source           | Target           | Cardinality | Description |
|-------------------|------------------|------------------|-------------|-------------|
| precedes          | Snapshot         | Snapshot         | 1:N         | Temporal ordering |

## Identifier Generation

| Entity       | Input Fields                                  |
|--------------|-----------------------------------------------|
| Snapshot     | `uuid4()` (non-deterministic)                 |

## Snapshot Lifecycle

### Create

1. Collect all canonical entities from Repository
2. Compute `entity_count` and `entity_counts`
3. Build `manifest`
4. Compute `checksum` (order-independent)
5. Generate `id` (UUID)
6. Set `created_at`
7. Set optional `parent_snapshot_id`
8. Return immutable Snapshot

### Verify

1. Recompute `checksum` from entity collection
2. Compare with `snapshot.checksum`
3. Compare `entity_count` and `entity_counts`
4. Verify `manifest` entries exist
5. Return pass/fail with mismatch report

### Restore

1. Read `manifest`
2. Reconstruct entity graph
3. Verify reconstructed graph matches `checksum`
4. Return entity collection

### Rollback

1. Retrieve Snapshot by ID
2. Verify Snapshot
3. Restore entity collection
4. Replace Repository's current state
5. Update Repository metadata

## Validation Rules

### Snapshot Invariants

- `checksum`: order-independent, covers all entity content
- `id`: globally unique (UUID)
- `parent_snapshot_id`: no circular lineage
- `manifest`: accurate inventory of all entities
- Snapshot is immutable after creation

## State Transitions

- **Snapshot**: Create → Immutable → Verify | Restore | Rollback
- No update or delete operations on Snapshots

## Dependencies

- **KNOW-002**: Canonical Knowledge Model (entities, relationships)
- **KNOW-003**: Parsing & Symbol Extraction (produces canonical entities)
