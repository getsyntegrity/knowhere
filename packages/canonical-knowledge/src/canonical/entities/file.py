"""File entity — single source file or document."""

from typing import Any

from pydantic import BaseModel, Field


class File(BaseModel):
    """A File represents a single source file or document within a Repository."""
    
    model_config = {"frozen": True}
    
    id: str = Field(..., description="Deterministic identifier")
    repository_id: str = Field(..., description="Parent Repository.id")
    path: str = Field(..., description="Relative path within repository")
    language: str | None = Field(default=None, description="Language label")
    checksum: str = Field(..., description="Content hash")
    size_bytes: int = Field(..., ge=0, description="Source file size")
    symbols: list = Field(default_factory=list, description="Symbols defined in this file")
    chunks: list = Field(default_factory=list, description="Chunks extracted from this file")
    references: list = Field(default_factory=list, description="References originating in this file")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible attributes")
