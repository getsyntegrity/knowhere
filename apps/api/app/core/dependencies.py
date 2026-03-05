import hashlib
from datetime import timedelta
from typing import Any

import jwt
from jwt import PyJWKClient

from app.services.auth.api_key_service import APIKeyService
from app.services.rate_limit.identity_cache import identity_cache
from fastapi import Depends, Header, Request
from loguru import logger
from shared.core.config import redis_pool_manager, settings
from shared.core.database import get_db
from shared.core.exceptions.domain_exceptions import (
    AuthException,
)
from sqlalchemy.ext.asyncio import AsyncSession


# Standard JWKS endpoint path (fixed, following OpenID Connect convention)
JWKS_ENDPOINT_PATH = "/api/auth/jwks"

# Cache settings: 1 hour in seconds
JWKS_CACHE_TTL_SECONDS = 60 * 60  # 3600 seconds

# Cached PyJWKClient instance
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """
    Get or create a cached PyJWKClient instance.
    
    The JWKS endpoint is constructed from INTERNAL_DASHBOARD_ENDPOINT + fixed path.
    PyJWKClient caches the JWKS response for 1 hour.
    """
    global _jwks_client
    
    if _jwks_client is None:
        jwks_url = f"{settings.INTERNAL_DASHBOARD_ENDPOINT}{JWKS_ENDPOINT_PATH}"
        _jwks_client = PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=JWKS_CACHE_TTL_SECONDS,
            timeout=30
        )
        logger.info(f"Initialized JWKS client with endpoint: {jwks_url}")
    
    return _jwks_client


def _get_verification_key(token: str) -> Any:
    """
    Get the verification key for the JWT from the JWKS endpoint.
    
    Uses PyJWKClient's built-in cache with 1 hour TTL.
    """
    try:
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return signing_key.key
    except jwt.PyJWKClientError as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise AuthException(internal_message=f"Failed to fetch verification key from JWKS endpoint: {e}")
    except jwt.PyJWKSetError as e:
        logger.error(f"Invalid JWKS format: {e}")
        raise AuthException(internal_message=f"Invalid JWKS format: {e}")


def decode_jwt_token(token: str) -> str:
    """
    Decode and validate JWT token using JWKS.
    
    Expected JWT claims:
    - id/sub: User ID
    - exp: Expiration
    """
    try:
        key = _get_verification_key(token)

        # Decode and Verify
        payload = jwt.decode(
            token,
            key,
            algorithms=["HS256", "RS256", "EdDSA"],
            leeway=timedelta(seconds=30),
            options={"verify_aud": False}
        )
        
        # Extract user_id from 'id' claim
        user_id = payload.get("id")
        
        if not user_id:
            raise AuthException(user_message="Token missing 'id' claim")
        
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise AuthException(user_message="Token has expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise AuthException(user_message="Invalid token")


async def get_current_user_id(
    request: Request,
    authorization: str | None = Header(default=None, description="Bearer <token> OR internal signature auth"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Authenticate the caller and return user_id.

    When the identity cache is hit the resolved ``user_tier`` is stashed on
    ``request.state.cached_user_tier`` so that downstream dependencies
    (``with_current_user``) can skip a second cache/DB lookup.
    """
    if not authorization:
        raise AuthException(
            user_message="Authentication required. Provide Authorization header."
        )

    # Parse Authorization header
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthException(user_message="Invalid Authorization header format")

    # Mode 1: API Key verification (for external clients)
    if token.startswith("sk_"):
        # Check identity cache first — skip DB on cache hit
        api_key_hash = hashlib.sha256(token.encode()).hexdigest()
        try:
            cached = await identity_cache.get_cached_identity(
                redis_pool_manager.get_redis_service(),
                identity_cache._apikey_key(api_key_hash),
            )
            if cached is not None:
                cached_user_id = cached.get("user_id")
                if cached_user_id:
                    # Stash tier so with_current_user can reuse it
                    request.state.cached_user_tier = cached.get("user_tier")
                    request.state.cached_identity_hit = True
                    request.state.user_id = cached_user_id
                    return cached_user_id
        except Exception:
            pass  # Fall through to DB validation

        # Cache miss — validate via DB
        api_key_service = APIKeyService()
        user_id = await api_key_service.validate_api_key(db, token)
        if user_id:
            request.state.user_id = user_id
            return user_id
        else:
            raise AuthException(user_message="Invalid API Key")

    # Mode 2: JWT verification (for Dashboard/Internal)
    user_id = decode_jwt_token(token)
    request.state.user_id = user_id
    return user_id
