"""API key schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateAPIKeyRequest(BaseModel):
    """Request payload for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255, description="API key name")
    enabled_modules: Optional[List[str]] = Field(
        default=None, description="Enabled feature modules"
    )
    expires_at: Optional[datetime] = Field(default=None, description="Expiration time")


class APIKeyResponse(BaseModel):
    """Serialized API key response."""

    id: str
    name: str
    api_key: str  # Masked API key value.
    enabled_modules: Optional[List[str]]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CreateAPIKeyResponse(BaseModel):
    """Response payload returned when an API key is created."""

    api_key: str = Field(
        ..., description="Generated API key; returned only during creation"
    )
    name: str
    enabled_modules: Optional[List[str]]
    expires_at: Optional[datetime]


class RegenerateAPIKeyRequest(BaseModel):
    """Request payload for regenerating an API key."""

    api_key_id: str = Field(..., description="API key ID to regenerate")


class RevokeAPIKeyRequest(BaseModel):
    """Request payload for revoking an API key."""

    api_key_id: str = Field(..., description="API key ID to revoke")


class APIKeyListResponse(BaseModel):
    """List response for API keys."""

    api_keys: List[APIKeyResponse]
    total: int
