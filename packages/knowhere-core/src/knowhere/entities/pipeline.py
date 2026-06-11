"""
RetrievalPipeline Entity
========================

Defines the retrieval strategy for a KnowledgeSource.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel

from ..types.chunk_type import ChunkType


class RetrievalPipeline(BaseModel):
    """Defines the retrieval strategy for a KnowledgeSource."""
    
    pipeline_id: UUID
    source_id: UUID
    name: str
    description: Optional[str] = None
    chunk_types: List[ChunkType]
    created_at: datetime
    metadata: Dict[str, Any] = {}