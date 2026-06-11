# ChunkingStrategy Contract

**Layer**: Ingestion Layer | **Spec**: [FR-008, FR-014](../spec.md) | **Date**: 2026-06-11

## Purpose

Pluggable strategy for splitting KnowledgeSource content into KnowledgeChunk units.

## Interface

```python
class ChunkingStrategy:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    def chunk(self, content: str, metadata: ChunkMetadata) -> list[KnowledgeChunk]:
        """
        Split content into KnowledgeChunk objects.
        
        Args:
            content: Raw source content (text, HTML, code)
            metadata: Source provenance metadata
            
        Returns:
            List of KnowledgeChunk objects with chunk_type assigned.
        """
```

## Contract Tests

- `test_chunk_returns_at_least_one_chunk`
- `test_chunks_have_deterministic_chunk_id`
- `test_chunks_have_valid_chunk_type`
- `test_chunks_maintain_source_lineage`
- `test_provider_metadata`
