# Tasks: KNOW-004 Snapshot & Versioning

**Input**: Design documents from `specs/004-know-004-snapshot-versioning/`
**Prerequisites**: KNOW-002 Canonical Knowledge Model (entities defined)
**Approach**: Test-first — write and see each test fail before implementing.

**Format**: `- [ ] [TaskID] [P?] Description (effort: S/M/L) — [file path]`
`[P]` = parallelizable with other tasks in the same phase.

## Phase 1: Snapshot Entity & ManifestEntry

- [ ] T001 [P] **TEST**: Snapshot entity in `tests/test_snapshot_entity.py` — `id` is UUID (non-deterministic); `entity_counts` typed counters; `created_at` required; immutable on creation; metadata defaults (effort: S)
- [ ] T002 [P] **TEST**: ManifestEntry in `tests/test_snapshot_entity.py` — id and type fields; serialization roundtrip (effort: S)
- [ ] T003 [P] Implement Snapshot in `src/snapshot/entities/snapshot.py` — `entity_counts` dict; `manifest` list; UUID default id; frozen Pydantic model (effort: S)
- [ ] T004 [P] Implement ManifestEntry in `src/snapshot/entities/manifest_entry.py` — id and type fields (effort: S)

## Phase 2: ChecksumService

- [ ] T005 [P] **TEST**: ChecksumService in `tests/test_checksum.py` — same entities → same checksum; different order → same checksum; modified entity → different checksum; empty collection → valid checksum (effort: M)
- [ ] T006 [P] Implement `ChecksumService` in `src/snapshot/checksum.py` — order-independent aggregate hash (sorted-hash or XOR-combined); coverage of all entity content (effort: M)

## Phase 3: Snapshot Lifecycle

- [ ] T007 **TEST**: SnapshotLifecycle.create in `tests/test_lifecycle.py` — creates Snapshot with accurate checksum, manifest, entity_counts; sets created_at; assigns parent_snapshot_id (effort: M)
- [ ] T008 **TEST**: SnapshotLifecycle.verify in `tests/test_lifecycle.py` — valid Snapshot → pass; modified entity → fail with mismatch report; missing manifest entry → fail (effort: M)
- [ ] T009 **TEST**: SnapshotLifecycle.restore in `tests/test_lifecycle.py` — restored collection matches original; checksum matches; manifest accurate (effort: M)
- [ ] T010 **TEST**: SnapshotLifecycle.rollback in `tests/test_lifecycle.py` — Repository restored to Snapshot state; metadata updated; rollback to non-existent Snapshot → error (effort: M)
- [ ] T011 Implement `SnapshotLifecycle` in `src/snapshot/lifecycle.py` — create, verify, restore, rollback; integration with ChecksumService (effort: M)

## Phase 4: Snapshot Lineage

- [ ] T012 [P] **TEST**: SnapshotLineage in `tests/test_lineage.py` — parent lookup; ancestor chain; circular reference detection → error; temporal ordering via precedes (effort: M)
- [ ] T013 [P] Implement `SnapshotLineage` in `src/snapshot/lineage.py` — parent-child tracking; ancestor chain; circular reference prevention (effort: M)

## Phase 5: Serialization

- [ ] T014 [P] **TEST**: Snapshot serialization in `tests/test_serialization.py` — lossless roundtrip; version marker; canonical model version embedded; major version mismatch rejection (effort: M)
- [ ] T015 [P] Implement `SnapshotSerializer` in `src/snapshot/serialization.py` — `to_json(snapshot)` and `from_json(json_str)`; version markers; forward compat (effort: M)

## Phase 6: Acceptance Criteria

- [ ] T016 Validate **AC-007** (Snapshot reproduces exact historical index state) — create → modify → restore → compare (effort: M)
- [ ] T017 Validate **AC-008** (Restored graph has same aggregate checksum) — checksum before and after restore match (effort: M)
- [ ] T018 Validate **AC-009** (Repository rollback to prior Snapshot) — rollback → verify state matches Snapshot (effort: M)
- [ ] T019 Validate **AC-SV-001** (Corrupted entity → different checksum) — modify entity → verify fails (effort: S)
- [ ] T020 Validate **AC-SV-002** (Manifest accurate) — manifest entries match actual entities (effort: S)
- [ ] T021 Validate **AC-SV-003** (Lineage preserved) — 100 sequential Snapshots; no circular references; parent chain valid (effort: M)
- [ ] T022 Validate **SC-003** (performance) — create + verify < 5s for 10k entities (effort: M)

---

## Summary

| Metric | Count |
|--------|-------|
| **Total tasks** | **22** |
| Test tasks (TDD) | 12 |
| Implementation tasks | 10 |
| Parallelizable tasks | 10 |
| Phases | 6 |
| Acceptance criteria tested | 6 (AC-007, AC-008, AC-009, AC-SV-001, AC-SV-002, AC-SV-003) |
| Success criteria validated | 1 (SC-003) |

### Dependencies

```
Phase 1 (Entity) ──→ Phase 2 (Checksum) ──→ Phase 3 (Lifecycle) ──→ Phase 6 (ACs)
                                           │
Phase 4 (Lineage) ──────────────────────────┘
Phase 5 (Serialization) ───────────────────┘
```

### Key Inclusions from KNOW-002 Migration

- Snapshot entity definition (formerly KNOW-002 §6.7)
- ManifestEntry value object
- `precedes` relationship type
- Snapshot lifecycle (create, verify, restore, rollback)
- AC-007, AC-008, AC-009 (formerly deferred in KNOW-002)
- SC-003 (formerly deferred in KNOW-002)
- FR-008 (formerly in KNOW-002 §17.2)
- User Story 3 — Platform Engineer Recovering from Snapshot
- Constraint 6 — Snapshot Reproducibility
