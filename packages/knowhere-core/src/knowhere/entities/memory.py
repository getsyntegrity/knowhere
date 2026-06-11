"""
Memory Entities
===============

Entities for memory management in the Knowhere system.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel


class Memory(BaseModel):
    """Base memory entity."""
    
    memory_id: UUID
    source_id: UUID
    knowledge_version: UUID
    created_at: datetime
    metadata: Dict[str, Any] = {}


class MemoryFact(BaseModel):
    """A single fact within a memory."""
    
    fact_id: UUID
    memory_id: UUID
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = {}


class MemoryRelationship(BaseModel):
    """Relationship between memory facts."""
    
    relationship_id: UUID
    memory_id: UUID
    from_fact_id: UUID
    to_fact_id: UUID
    relationship_type: str
    created_at: datetime
    metadata: Dict[str, Any] = {}


class MemorySummary(BaseModel):
    """Summary of a memory."""
    
    summary_id: UUID
    memory_id: UUID
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = {}