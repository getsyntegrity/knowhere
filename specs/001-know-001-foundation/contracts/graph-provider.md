# GraphProvider Contract

**Layer**: Knowledge Graph Layer | **Spec**: [FR-016, FR-051](../spec.md) | **Date**: 2026-06-11

## Purpose

Abstract graph storage and traversal over GraphNode/GraphEdge entities. Derived index — rebuildable from Storage.

## Interface

```python
class GraphProvider:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    def create_node(self, node: GraphNode) -> None:
        """Create or update a graph node."""

    def create_edge(self, edge: GraphEdge) -> None:
        """Create or update a graph edge."""

    def traverse(self, start_node_id: str, relationship_types: list[str], max_depth: int) -> list[GraphPath]:
        """Traverse the graph from a starting node."""

    def query_by_type(self, entity_type: str, properties: dict = None) -> list[GraphNode]:
        """Query nodes by entity type and optional properties."""

    def rebuild(self) -> None:
        """Rebuild the entire graph index from Storage."""

    def verify_consistency(self) -> ConsistencyReport:
        """Compare graph index against Storage and report discrepancies."""
```

## Fallback

SHOULD NOT configure fallback (fail fast — Storage is the authoritative source).

## Contract Tests

- `test_create_and_query_node`
- `test_create_and_traverse_edge`
- `test_rebuild_produces_identical_results`
- `test_verify_consistency_reports_ok`
