"""Symbol entity — named code or document symbol."""

from typing import Any

from pydantic import BaseModel, Field

from canonical.value_objects.code_location import CodeLocation


class Symbol(BaseModel):
    """A Symbol represents a named code or document symbol (function, class, variable, etc.)."""
    
    model_config = {"frozen": True}
    
    id: str = Field(..., description="Deterministic identifier")
    file_id: str = Field(..., description="Parent File.id")
    repository_id: str = Field(..., description="Parent Repository.id")
    name: str = Field(..., description="Local name")
    qualified_name: str = Field(..., description="Fully qualified name (unique per repo)")
    kind: str = Field(..., description="Symbol kind (function, class, etc.)")
    scope: str | None = Field(default=None, description="Parent scope identifier")
    location: CodeLocation = Field(..., description="Source location")
    signature: str | None = Field(default=None, description="Callable signature text")
    documentation: str | None = Field(default=None, description="Docstring/comment")
    children: list[str] = Field(default_factory=list, description="Child Symbol IDs")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible attributes")
