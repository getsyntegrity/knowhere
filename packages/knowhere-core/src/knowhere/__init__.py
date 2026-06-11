"""
Knowhere Core - Foundation Architecture
=======================================

This package provides the core architecture for Knowhere, including:
- Abstract provider interfaces
- Core entity definitions
- Type system and enums
- Domain exceptions
"""

# Re-export core components for easy import
from .entities.source import KnowledgeSource
from .entities.chunk import KnowledgeChunk
from .entities.version import KnowledgeVersion
from .entities.pipeline import RetrievalPipeline
from .entities.graph import GraphNode, GraphEdge
from .entities.memory import Memory, MemoryFact, MemoryRelationship, MemorySummary
from .entities.code import Repository, File, Symbol, Dependency, Reference

from .providers.vector import VectorProvider
from .providers.embedding import EmbeddingProvider
from .providers.graph import GraphProvider
from .providers.storage import StorageProvider
from .providers.code_parser import CodeParserProvider
from .providers.ranking import RankingStrategy
from .providers.compression import CompressionProvider
from .providers.context_builder import ContextBuilder

from .types.chunk_type import ChunkType
from .types.version import KnowledgeVersionStatus
from .types.metrics import Capability, MetricReport, ConsistencyReport

from .exceptions.exceptions import (
    ProviderNotFoundError,
    VersionCorruptedError,
    ConfigurationError,
    ChunkValidationError,
)

__all__ = [
    # Entities
    "KnowledgeSource",
    "KnowledgeChunk",
    "KnowledgeVersion",
    "RetrievalPipeline",
    "GraphNode",
    "GraphEdge",
    "Memory",
    "MemoryFact",
    "MemoryRelationship",
    "MemorySummary",
    "Repository",
    "File",
    "Symbol",
    "Dependency",
    "Reference",
    
    # Providers
    "VectorProvider",
    "EmbeddingProvider",
    "GraphProvider",
    "StorageProvider",
    "CodeParserProvider",
    "RankingStrategy",
    "CompressionProvider",
    "ContextBuilder",
    
    # Types
    "ChunkType",
    "KnowledgeVersionStatus",
    "Capability",
    "MetricReport",
    "ConsistencyReport",
    
    # Exceptions
    "ProviderNotFoundError",
    "VersionCorruptedError",
    "ConfigurationError",
    "ChunkValidationError",
]