# VectorProvider Contract

**Layer**: Storage | **Spec**: [FR-018, FR-050](../spec.md) | **Date**: 2026-06-11

## Purpose

Abstract vector storage and similarity search over KnowledgeChunk embeddings. Derived index — rebuildable from Storage.

## Interface

```python
class VectorProvider:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    def upsert(self, chunks: list[KnowledgeChunk]) -> None:
        """Index or update chunks in the vector store."""

    def search(self, query_vector: list[float], top_k: int, filters: dict = None) -> list[ChunkResult]:
        """Search for nearest neighbors by vector similarity."""

    def delete(self, chunk_ids: list[str]) -> None:
        """Remove chunks from the index."""

    def list_collections(self) -> list[str]:
        """List available collection/index names."""

    def rebuild(self) -> None:
        """Rebuild the entire vector index from Storage (authoritative source)."""

    def verify_consistency(self) -> ConsistencyReport:
        """Compare vector index against Storage and report discrepancies."""
```

## Fallback

SHOULD configure fallback for production deployments.

## Contract Tests

- `test_upsert_and_search_roundtrip`
- `test_search_returns_top_k_results`
- `test_delete_removes_from_index`
- `test_rebuild_produces_identical_results`
- `test_provider_metadata`
