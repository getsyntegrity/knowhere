"""
CompressionProvider Interface
=============================

Interface for compression providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.chunk import KnowledgeChunk
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class CompressionProvider(ABC):
    """Interface for compression providers."""
    
    @abstractmethod
    def get_capability(self) -> Capability:
        """Get the capability of this provider."""
        pass
    
    @abstractmethod
    def get_metrics(self) -> MetricReport:
        """Get metrics for this provider."""
        pass
    
    @abstractmethod
    def validate_consistency(self) -> ConsistencyReport:
        """Validate the consistency of the compression provider."""
        pass
    
    @abstractmethod
    def compress_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        """Compress a knowledge chunk."""
        pass
    
    @abstractmethod
    def decompress_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        """Decompress a knowledge chunk."""
        pass
    
    @abstractmethod
    def get_compression_ratio(self, original_size: int, compressed_size: int) -> float:
        """Calculate the compression ratio."""
        pass