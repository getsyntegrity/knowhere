"""
ContextBuilder Interface
========================

Interface for context building providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.chunk import KnowledgeChunk
from ..entities.memory import MemoryFact
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class ContextBuilder(ABC):
    """Interface for context building providers."""
    
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
        """Validate the consistency of the context builder."""
        pass
    
    @abstractmethod
    def build_context(self, chunks: List[KnowledgeChunk], facts: List[MemoryFact], **kwargs) -> str:
        """Build a context string from chunks and facts."""
        pass
    
    @abstractmethod
    def build_context_with_metadata(self, chunks: List[KnowledgeChunk], facts: List[MemoryFact], **kwargs) -> Dict[str, Any]:
        """Build a context with metadata from chunks and facts."""
        pass