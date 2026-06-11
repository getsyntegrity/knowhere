"""Repository entity — sole aggregate root."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Repository(BaseModel):
    """A Repository represents an indexed codebase, knowledge base, or collection of files.
    
    Sole aggregate root. Owns all other entities within its scope.
    """
    
    model_config = {"frozen": True}
    
    id: str = Field(..., description="Deterministic identifier")
    name: str = Field(..., description="Human-readable name")
    source_uri: str = Field(..., description="Provider-specific origin URI")
    source: str = Field(..., description="Provider label (e.g., 'knowhere')")
    files: list = Field(default_factory=list, description="Child file collection")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="First ingestion timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible attributes")
