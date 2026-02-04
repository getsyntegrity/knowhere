from shared.core.exceptions.domain_exceptions import SystemSettingMissingException
from typing import Any, Dict, Optional, Tuple
import hmac
import hashlib
import time

from shared.core.database import get_db
from shared.core.config import settings
from app.services.auth.api_key_service import APIKeyService
from fastapi import Depends, Request, status, Header
from loguru import logger
from shared.core.exceptions.domain_exceptions import AuthException
from sqlalchemy.ext.asyncio import AsyncSession

async def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db)
) -> str:
    """
    Get current user ID.
    Supports two authentication modes:
    1. Internal communication signature verification (X-User-Id, X-Timestamp, X-Signature)
    2. API Key verification (Authorization: Bearer sk_...)
    """
    # Mode 1: Signature verification (for Dashboard/Internal)
    if x_user_id and x_timestamp and x_signature:
        # 1. Validate Timestamp
        try:
            ts = int(x_timestamp)
            now = int(time.time() * 1000)
            # Allow 5 minutes time difference
            if abs(now - ts) > 5 * 60 * 1000:
                raise AuthException(user_message="Request timestamp expired")
        except ValueError:
            raise AuthException(user_message="Invalid timestamp format")

        # 2. Verify Signature
        # Payload format: {user_id}:{timestamp}
        payload = f"{x_user_id}:{x_timestamp}"
        secret = settings.INTERNAL_API_SECRET
        
        if not secret:
            raise SystemSettingMissingException("INTERNAL_API_SECRET is not set!")

        if secret:
            expected_signature = hmac.new(
                secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, x_signature):
                raise AuthException(user_message="Invalid request signature")

        return x_user_id

    # Mode 2: API Key verification (for external clients)
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.startswith("sk_"):
            api_key_service = APIKeyService()
            user_id = await api_key_service.validate_api_key(db, token)
            if user_id:
                return user_id
            else:
                raise AuthException(user_message="Invalid API Key")

    # Authentication failed
    raise AuthException(
        user_message="Authentication required. Provide X-User-Id/Signature headers or API Key."
    )
