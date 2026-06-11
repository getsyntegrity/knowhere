"""
VectorProvider Interface
========================

Interface for vector storage providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from uuid import UUID

from ..entities.chunk import KnowledgeChunk
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class VectorProvider(ABC):
    """Interface for vector storage providers."""
    
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
        """Validate the consistency of the vector storage."""
        pass
    
    @abstractmethod
    def create_vector_index(self, index_name: str, dimensions: int, **kwargs) -> str:
        """Create a new vector index."""
        pass
    
    @abstractmethod
    def delete_vector_index(self, index_name: str) -> bool:
        """Delete a vector index."""
        pass
    
    @abstractmethod
    def add_vectors(self, index_name: str, vectors: List[List[float]], ids: List[str]) -> bool:
        """Add vectors to an index."""
        pass
    
    @abstractmethod
    def search_vectors(self, index_name: str, query_vector: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        pass
    
    @abstractmethod
    def get_vector(self, index_name: str, id: str) -> Optional[List[float]]:
        """Get a specific vector by ID."""
        pass
    
    @abstractmethod
    def update_vector(self, index_name: str, id: str, vector: List[float]) -> bool:
        """Update a specific vector by ID."""
        pass
    
    @abstractmethod
    def delete_vector(self, index_name: str, id: str) -> bool:
        """Delete a specific vector by ID."""
        pass
    
    @abstractmethod
    def get_vector_count(self, index_name: str) -> int:
        """Get the number of vectors in an index."""
        pass
    
    @abstractmethod
    def list_indexes(self) -> List[str]:
        """List all available indexes."""
        pass