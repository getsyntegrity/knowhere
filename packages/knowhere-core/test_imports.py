#!/usr/bin/env python3
"""
Simple test script to verify the knowhere-core package implementation.
"""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
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
    
    print("✓ All imports successful")
    
    # Test enums
    print(f"✓ ChunkType has {len(ChunkType)} values")
    print(f"✓ KnowledgeVersionStatus has {len(KnowledgeVersionStatus)} values")
    
    # Test basic instantiation
    from uuid import uuid4
    from datetime import datetime
    
    # Test KnowledgeChunk
    chunk = KnowledgeChunk(
        chunk_id="test_chunk_123",
        source_id=uuid4(),
        knowledge_version=uuid4(),
        chunk_type=ChunkType.CODE_FILE,
        content="test content",
        created_at=datetime.now()
    )
    print("✓ KnowledgeChunk instantiation successful")
    
    # Test KnowledgeVersion
    version = KnowledgeVersion(
        version_id=uuid4(),
        source_id=uuid4(),
        version_number="1.0.0",
        status=KnowledgeVersionStatus.SEALING,
        created_at=datetime.now()
    )
    print("✓ KnowledgeVersion instantiation successful")
    
    # Test RetrievalPipeline
    pipeline = RetrievalPipeline(
        pipeline_id=uuid4(),
        source_id=uuid4(),
        name="test_pipeline",
        chunk_types=[ChunkType.CODE_FILE],
        created_at=datetime.now()
    )
    print("✓ RetrievalPipeline instantiation successful")
    
    print("\n🎉 All tests passed! The knowhere-core package is working correctly.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)