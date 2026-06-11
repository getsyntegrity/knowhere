"""
KnowledgeVersion Entity
=======================

Versioned snapshot of a KnowledgeSource. All chunks belong to a version.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel

from ..types.version import KnowledgeVersionStatus


class KnowledgeVersion(BaseModel):
    """Versioned snapshot of a KnowledgeSource."""
    
    version_id: UUID
    source_id: UUID
    version_number: str
    status: KnowledgeVersionStatus
    created_at: datetime
    metadata: Dict[str, Any] = {}
    parent_version_id: Optional[UUID] = None