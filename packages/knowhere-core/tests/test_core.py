"""
Test file for the Knowhere Core package.
"""

import pytest
from uuid import UUID, uuid4
from datetime import datetime

from knowhere import (
    KnowledgeSource,
    KnowledgeChunk,
    KnowledgeVersion,
    RetrievalPipeline,
    GraphNode,
    GraphEdge,
    Memory,
    MemoryFact,
    MemoryRelationship,
    MemorySummary,
    Repository,
    File,
    Symbol,
    Dependency,
    Reference,
    ChunkType,
    KnowledgeVersionStatus,
    StorageProvider,
    VectorProvider,
    EmbeddingProvider,
    GraphProvider,
    CodeParserProvider,
    RankingStrategy,
    CompressionProvider,
    ContextBuilder,
    ProviderNotFoundError,
    VersionCorruptedError,
    ConfigurationError,
    ChunkValidationError
)


def test_chunk_type_enum():
    """Test that ChunkType enum works correctly."""
    assert ChunkType.CODE_FILE.value == "CODE_FILE"
    assert ChunkType.DOCUMENT.value == "DOCUMENT"
    assert len(ChunkType) == 15  # All defined types


def test_version_status_enum():
    """Test that KnowledgeVersionStatus enum works correctly."""
    assert KnowledgeVersionStatus.SEALING.value == "sealing"
    assert KnowledgeVersionStatus.SEALED.value == "sealed"
    assert KnowledgeVersionStatus.CORRUPTED.value == "corrupted"
    assert len(KnowledgeVersionStatus) == 3


def test_core_entities():
    """Test that core entities can be instantiated."""
    # Test KnowledgeSource (abstract, so we test the base class)
    assert KnowledgeSource is not None
    
    # Test KnowledgeChunk
    chunk = KnowledgeChunk(
        chunk_id="test_chunk_123",
        source_id=uuid4(),
        knowledge_version=uuid4(),
        chunk_type=ChunkType.CODE_FILE,
        content="test content",
        created_at=datetime.now()
    )
    assert chunk.chunk_id == "test_chunk_123"
    assert chunk.content == "test content"
    
    # Test KnowledgeVersion
    version = KnowledgeVersion(
        version_id=uuid4(),
        source_id=uuid4(),
        version_number="1.0.0",
        status=KnowledgeVersionStatus.SEALING,
        created_at=datetime.now()
    )
    assert version.version_number == "1.0.0"
    assert version.status == KnowledgeVersionStatus.SEALING
    
    # Test RetrievalPipeline
    pipeline = RetrievalPipeline(
        pipeline_id=uuid4(),
        source_id=uuid4(),
        name="test_pipeline",
        chunk_types=[ChunkType.CODE_FILE],
        created_at=datetime.now()
    )
    assert pipeline.name == "test_pipeline"
    assert len(pipeline.chunk_types) == 1


def test_provider_interfaces():
    """Test that provider interfaces exist."""
    assert StorageProvider is not None
    assert VectorProvider is not None
    assert EmbeddingProvider is not None
    assert GraphProvider is not None
    assert CodeParserProvider is not None
    assert RankingStrategy is not None
    assert CompressionProvider is not None
    assert ContextBuilder is not None


def test_exceptions():
    """Test that exceptions can be imported and instantiated."""
    assert ProviderNotFoundError is not None
    assert VersionCorruptedError is not None
    assert ConfigurationError is not None
    assert ChunkValidationError is not None
    
    # Test exception instantiation
    with pytest.raises(ProviderNotFoundError):
        raise ProviderNotFoundError("test_provider")
    
    with pytest.raises(VersionCorruptedError):
        raise VersionCorruptedError("test_version")
    
    with pytest.raises(ConfigurationError):
        raise ConfigurationError("test config error")
    
    with pytest.raises(ChunkValidationError):
        raise ChunkValidationError("test_chunk", "test error")


if __name__ == "__main__":
    test_chunk_type_enum()
    test_version_status_enum()
    test_core_entities()
    test_provider_interfaces()
    test_exceptions()
    print("All tests passed!")