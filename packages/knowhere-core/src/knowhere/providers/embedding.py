"""
EmbeddingProvider Interface
===========================

Interface for embedding providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.chunk import KnowledgeChunk
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class EmbeddingProvider(ABC):
    """Interface for embedding providers."""
    
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
        """Validate the consistency of the embedding provider."""
        pass
    
    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """Generate an embedding for the given text."""
        pass
    
    @abstractmethod
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        pass
    
    @abstractmethod
    def get_embedding_dimensions(self) -> int:
        """Get the dimensionality of the embeddings."""
        pass