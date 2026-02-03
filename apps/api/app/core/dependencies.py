from typing import Optional
import hmac
import hashlib
import time

from shared.core.config import settings
from fastapi import Header, Request
from loguru import logger
from shared.core.exceptions.domain_exceptions import AuthException

async def get_current_user_id(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
) -> str:
    """
    Get current user ID.
    Supports two authentication modes:
    Internal communication signature verification (X-User-Id, X-Timestamp, X-Signature)
    """
    # Signature verification (for Dashboard/Internal)
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
            logger.warning("INTERNAL_API_SECRET is not set! Signature verification might fail or be insecure.")
            # In production, this should probably raise an error

        if secret:
            expected_signature = hmac.new(
                secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, x_signature):
                raise AuthException(user_message="Invalid request signature")

        return x_user_id

    # Authentication failed
    raise AuthException(
        user_message="Authentication required. Provide X-User-Id/Signature headers or API Key."
    )
