# SourceProvider Contract

**Layer**: Ingestion Layer | **Spec**: [FR-008, FR-016](../spec.md) | **Date**: 2026-06-11

## Purpose

Abstract knowledge ingestion from any source type (Git, filesystem, documents, images).

## Interface

```python
class SourceProvider:
    provider_name: str          # Unique identifier
    provider_version: str       # Semver
    provider_capabilities: list[Capability]  # Structured: name, version, stability

    def ingest(self, config: SourceConfig) -> list[KnowledgeChunk]:
        """
        Ingest content from a source and return KnowledgeChunk objects.
        
        Args:
            config: Source-specific configuration (path, URL, credentials, etc.)
            
        Returns:
            List of KnowledgeChunk objects with content, metadata, and provenance.
            
        Raises:
            SourceNotFoundError: Source path/URL does not exist
            SourceAccessError: Permission or network failure
            IngestionError: Unrecoverable processing error
        """
```

## Metadata Requirements

Every provider MUST expose:
- `provider_name` (unique identifier)
- `provider_version` (semantic version)
- `provider_capabilities` — each capability: `name`, `version` (semver), `stability` (stable, beta, deprecated)

## Error Conditions

| Error | When | Behavior |
|-------|------|----------|
| `SourceNotFoundError` | Source path/URL doesn't exist | Fail job, log error, no chunks produced |
| `SourceAccessError` | Authentication/permission failure | Fail job, log error, no chunks produced |
| `IngestionError` | Processing failure mid-stream | Log error, CONTINUE with remaining content, mark partial success |

## Contract Tests

```python
class SourceProviderContract:
    def test_ingest_returns_chunks(self, provider, sample_source):
        chunks = provider.ingest(sample_source)
        assert len(chunks) > 0
        for c in chunks:
            assert c.chunk_id is not None
            assert c.source_id is not None
            assert c.content is not None

    def test_ingest_sets_provenance(self, provider, sample_source):
        chunks = provider.ingest(sample_source)
        for c in chunks:
            assert c.metadata.source_type is not None
            assert c.metadata.source_path is not None
            assert c.metadata.ingestion_timestamp is not None

    def test_provider_metadata(self, provider):
        assert provider.provider_name is not None
        assert provider.provider_version is not None
        assert len(provider.provider_capabilities) > 0
        for cap in provider.provider_capabilities:
            assert "name" in cap
            assert "version" in cap
            assert "stability" in cap
```
