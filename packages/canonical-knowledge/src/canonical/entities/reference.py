"""Reference entity — occurrence-based pointer."""

from typing import Any

from pydantic import BaseModel, Field

from canonical.value_objects.code_location import CodeLocation


class Reference(BaseModel):
    """A Reference represents an occurrence-based pointer from one entity to another."""
    
    model_config = {"frozen": True}
    
    id: str = Field(..., description="Deterministic identifier")
    repository_id: str = Field(..., description="Parent Repository.id")
    source_id: str = Field(..., description="Originating entity ID")
    target_id: str = Field(..., description="Referenced entity ID")
    source_file_id: str = Field(..., description="Originating File.id")
    target_file_id: str = Field(..., description="Referenced File.id")
    location: CodeLocation = Field(..., description="Source location")
    context: str | None = Field(default=None, description="Surrounding text snippet")
    role: str = Field(..., description="Semantic role (import, call, etc.)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible attributes")
