"""
RankingStrategy Interface
=========================

Interface for ranking strategies in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.chunk import KnowledgeChunk
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class RankingStrategy(ABC):
    """Interface for ranking strategies."""
    
    @abstractmethod
    def get_capability(self) -> Capability:
        """Get the capability of this strategy."""
        pass
    
    @abstractmethod
    def get_metrics(self) -> MetricReport:
        """Get metrics for this strategy."""
        pass
    
    @abstractmethod
    def validate_consistency(self) -> ConsistencyReport:
        """Validate the consistency of the ranking strategy."""
        pass
    
    @abstractmethod
    def rank_chunks(self, chunks: List[KnowledgeChunk], query: str, **kwargs) -> List[KnowledgeChunk]:
        """Rank a list of chunks based on a query."""
        pass
    
    @abstractmethod
    def get_ranking_score(self, chunk: KnowledgeChunk, query: str) -> float:
        """Get the ranking score for a chunk and query."""
        pass