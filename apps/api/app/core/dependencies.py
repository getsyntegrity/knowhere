import hashlib
import threading
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
    PermissionDeniedException,
)
from sqlalchemy.ext.asyncio import AsyncSession


# Standard JWKS endpoint path (fixed, following OpenID Connect convention)
JWKS_ENDPOINT_PATH = "/api/auth/jwks"

# Cache settings: 1 hour in seconds
JWKS_CACHE_TTL_SECONDS = 60 * 60  # 3600 seconds

# Cached PyJWKClient instance
_jwks_client: PyJWKClient | None = None
_jwks_client_lock = threading.Lock()


def _get_jwks_client() -> PyJWKClient:
    """
    Get or create a cached PyJWKClient instance.

    The JWKS endpoint is constructed from INTERNAL_DASHBOARD_ENDPOINT + fixed path.
    PyJWKClient caches the JWKS response for 1 hour.
    """
    global _jwks_client

    if _jwks_client is None:
        with _jwks_client_lock:
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


def _get_route_path(request: Request) -> str:
    """Return the request path without the application's root_path prefix."""
    scope_path = request.scope.get("path", request.url.path)
    root_path = request.scope.get("root_path", "")
    if root_path and scope_path.startswith(root_path):
        return scope_path[len(root_path):]
    return scope_path


def _enforce_guest_api_key_scope(route_path: str, user_tier: str) -> None:
    """Reject guest API keys outside the job API surface."""
    if user_tier != "guest":
        return

    if route_path.startswith("/v1/jobs"):
        return

    raise PermissionDeniedException(
        user_message="Guest API keys can only access job APIs",
        required_permission="jobs",
    )


async def get_current_user_id(
    request: Request,
    authorization: str | None = Header(default=None, description="Bearer <token> OR internal signature auth"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Authenticate the caller and return user_id."""
    if not authorization:
        raise AuthException(
            user_message="Authentication required. Provide Authorization header."
        )

    # Parse Authorization header
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthException(user_message="Invalid Authorization header format")

    route_path = _get_route_path(request)

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
                cached_user_tier = cached.get("user_tier")
                if cached_user_id and isinstance(cached_user_tier, str):
                    request.state.cached_user_tier = cached_user_tier
                    request.state.cached_identity_hit = True
                    request.state.user_id = cached_user_id
                    _enforce_guest_api_key_scope(route_path, cached_user_tier)
                    return cached_user_id
        except PermissionDeniedException:
            raise
        except Exception:
            pass  # Fall through to DB validation

        # Cache miss — validate via DB
        api_key_service = APIKeyService()
        identity = await api_key_service.validate_api_key_identity(db, token)
        if identity:
            request.state.cached_user_tier = identity.user_tier
            request.state.cached_identity_hit = False
            request.state.user_id = identity.user_id
            _enforce_guest_api_key_scope(route_path, identity.user_tier)
            return identity.user_id
        else:
            raise AuthException(user_message="Invalid API Key")

    # Mode 2: JWT verification (for Dashboard/Internal)
    return decode_jwt_token(token)
