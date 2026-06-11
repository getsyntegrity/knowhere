"""Chunk entity — contiguous text span."""

from typing import Any

from pydantic import BaseModel, Field

from canonical.value_objects.code_location import CodeLocation


class Chunk(BaseModel):
    """A Chunk represents a contiguous span of text extracted from a File."""
    
    model_config = {"frozen": True}
    
    id: str = Field(..., description="Deterministic identifier")
    file_id: str = Field(..., description="Parent File.id")
    repository_id: str = Field(..., description="Parent Repository.id")
    text: str = Field(..., description="Raw chunk text")
    location: CodeLocation = Field(..., description="Source location")
    semantic_hash: str = Field(..., description="Semantic equivalence hash (cross-provider dedup)")
    chunk_type: str = Field(..., description="Semantic type label")
    checksum: str = Field(..., description="Integrity hash (self-verification)")
    ordering: int = Field(..., ge=0, description="Ordinal position in file")
    symbol_ids: list[str] = Field(default_factory=list, description="Referenced Symbol IDs")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible attributes")
