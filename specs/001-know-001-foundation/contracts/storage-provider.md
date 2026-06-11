# StorageProvider Contract

**Layer**: Storage Layer | **Spec**: [FR-022, FR-008, FR-009](../spec.md) | **Date**: 2026-06-11

## Purpose

Persistent entity storage for all entity types. Storage is the authoritative source of truth; Vector and Graph stores are derived indices.

## Interface

```python
class StorageProvider:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    # KnowledgeSource CRUD
    def create_source(self, source: KnowledgeSource) -> None
    def get_source(self, source_id: str) -> KnowledgeSource
    def list_sources(self, filters: dict) -> list[KnowledgeSource]

    # KnowledgeChunk CRUD
    def create_chunk(self, chunk: KnowledgeChunk) -> None
    def get_chunk(self, chunk_id: str) -> KnowledgeChunk
    def get_chunks_by_source(self, source_id: str) -> list[KnowledgeChunk]
    def get_chunks_by_version(self, version_id: str) -> list[KnowledgeChunk]
    def delete_chunk(self, chunk_id: str) -> None

    # KnowledgeVersion CRUD
    def create_version(self, version: KnowledgeVersion) -> None
    def get_version(self, version_id: str) -> KnowledgeVersion
    def seal_version(self, version_id: str) -> None
    def get_latest_version(self) -> KnowledgeVersion
    def list_versions(self) -> list[KnowledgeVersion]

    # RetrievalPipeline CRUD
    def create_pipeline(self, pipeline: RetrievalPipeline) -> None
    def get_pipeline(self, pipeline_id: str) -> RetrievalPipeline
    def list_pipelines(self) -> list[RetrievalPipeline]

    # Graph entity CRUD
    def create_graph_node(self, node: GraphNode) -> None
    def create_graph_edge(self, edge: GraphEdge) -> None
    def get_graph_nodes_by_version(self, version_id: str) -> list[GraphNode]
    def get_graph_edges_by_version(self, version_id: str) -> list[GraphEdge]
```

## Fallback

SHOULD NOT configure fallback (fail fast — Storage is authoritative source of truth).

## Contract Tests

- `test_create_and_retrieve_source`
- `test_create_and_retrieve_chunk`
- `test_create_and_seal_version`
- `test_create_and_retrieve_pipeline`
- `test_chunk_idempotent_create`
