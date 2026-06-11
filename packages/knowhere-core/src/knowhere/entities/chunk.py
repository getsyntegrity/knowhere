"""
KnowledgeChunk Entity
=====================

The atomic retrieval unit across all layers. All retrieval operates on chunks.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, validator

from ..types.chunk_type import ChunkType


class KnowledgeChunk(BaseModel):
    """The atomic retrieval unit across all layers."""
    
    chunk_id: str  # Deterministic hash of content
    source_id: UUID
    knowledge_version: UUID
    chunk_type: ChunkType
    content: str
    embedding: Optional[List[float]] = None
    parent_chunk_id: Optional[str] = None
    root_chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    
    @validator('content')
    def content_must_not_be_empty(cls, v):
        """Validate that content is not empty."""
        if not v or not v.strip():
            raise ValueError('Content must not be empty')
        return v
    
    @validator('parent_chunk_id', 'root_chunk_id')
    def lineage_must_have_both_ids(cls, v, values):
        """Validate that if parent_chunk_id is set, root_chunk_id must also be set."""
        if v is not None and values.get('parent_chunk_id') is not None:
            if values.get('root_chunk_id') is None:
                raise ValueError('If parent_chunk_id is set, root_chunk_id must also be set')
        return v