"""
KnowledgeSource Entity
======================

Root entity for all ingested knowledge origins. Abstract base — every source is a concrete subtype.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel

from ..types.chunk_type import ChunkType


class KnowledgeSource(BaseModel, ABC):
    """Abstract base class for all knowledge sources."""
    
    source_id: UUID
    source_type: str  # Will be enum in concrete implementations
    ingestion_timestamp: datetime
    hash: str
    status: str  # Will be enum in concrete implementations
    metadata: Dict[str, Any]
    
    @abstractmethod
    def get_source_type(self) -> str:
        """Get the type of this source."""
        pass
    
    @abstractmethod
    def get_source_metadata(self) -> Dict[str, Any]:
        """Get the metadata for this source."""
        pass