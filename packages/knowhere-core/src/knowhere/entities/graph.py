"""
GraphNode and GraphEdge Entities
================================

Graph representation of knowledge relationships.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel


class GraphNode(BaseModel):
    """Node in the knowledge graph."""
    
    node_id: UUID
    source_id: UUID
    knowledge_version: UUID
    label: str
    properties: Dict[str, Any] = {}
    created_at: datetime


class GraphEdge(BaseModel):
    """Edge in the knowledge graph."""
    
    edge_id: UUID
    source_id: UUID
    knowledge_version: UUID
    from_node_id: UUID
    to_node_id: UUID
    relationship: str
    properties: Dict[str, Any] = {}
    created_at: datetime