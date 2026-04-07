"""Guest registration schemas."""
from datetime import datetime

from pydantic import BaseModel, Field


class GuestRegisterRequest(BaseModel):
    """Register a guest device."""
    device_id: str = Field(..., min_length=1, max_length=255, description="Stable client device identifier")
    client: str = Field(..., min_length=1, max_length=64, description="Client application name, e.g. knowhere-hub")
    platform: str = Field(..., min_length=1, max_length=64, description="Operating system, e.g. macos")
    app_version: str | None = Field(default=None, max_length=32, description="Client application version")


class GuestRateLimitInfo(BaseModel):
    """Rate limit metadata returned with guest registration."""
    rpm: int = Field(description="Requests per minute (-1 = unlimited)")
    daily_quota: int = Field(description="Requests per day (-1 = unlimited)")
    max_concurrent_jobs: int = Field(description="Maximum concurrent jobs")


class GuestRegisterResponse(BaseModel):
    """Response for guest device registration."""
    guest_user_id: str
    device_id: str
    api_key: str = Field(description="Plaintext API key (sk_...), issued on first registration")
    rate_limit: GuestRateLimitInfo
    expires_at: datetime | None = Field(description="API key expiry timestamp, or null for non-expiring guest keys")
