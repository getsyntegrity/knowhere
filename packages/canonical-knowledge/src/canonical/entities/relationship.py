"""Relationship entity — typed edge connecting two entities."""

from typing import Any

from pydantic import BaseModel, Field


class Relationship(BaseModel):
    """A Relationship represents a typed edge connecting any two canonical entities."""
    
    model_config = {"frozen": True}
    
    id: str = Field(..., description="Deterministic identifier")
    repository_id: str = Field(..., description="Parent Repository.id")
    source_id: str = Field(..., description="Source entity ID")
    target_id: str = Field(..., description="Target entity ID")
    type: str = Field(..., description="Relationship type label")
    weight: float | None = Field(default=None, ge=0.0, le=1.0, description="Optional strength")
    attributes: dict[str, Any] | None = Field(default=None, description="Typed attribute map")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible attributes")
