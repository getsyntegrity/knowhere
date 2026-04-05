"""Guest registration routes."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.guest.guest_registration_service import GuestRegistrationService
from app.services.rate_limit.dependencies import require_ip_rate_limit
from shared.core.database import get_db
from shared.models.schemas.guest import GuestRegisterRequest, GuestRegisterResponse

router = APIRouter()


@router.post("", summary="Register guest device", response_model=GuestRegisterResponse)
async def register_guest(
    payload: GuestRegisterRequest,
    request: Request,
    _rate_limit: None = Depends(require_ip_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> GuestRegisterResponse:
    """Register a guest device and return an API key.

    If the device_id already exists, the previous key is revoked and a new
    one is issued.  The endpoint is rate-limited by client IP.
    """
    service = GuestRegistrationService()
    return await service.register_guest(
        session=db,
        device_id=payload.device_id,
        client=payload.client,
        platform=payload.platform,
        app_version=payload.app_version,
    )
