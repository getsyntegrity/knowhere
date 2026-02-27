"""
Redis-backed identity cache for user_id + user_tier resolution.

Caches the mapping from authentication credentials (JWT user_id or API key hash)
to the resolved identity (user_id, user_tier) so that tier lookups do not hit
the database on every request.

Key patterns (all prefixed with REDIS_KEY_PREFIX from config):
    JWT:     {PREFIX}:identity:jwt:{user_id}
    API key: {PREFIX}:identity:apikey:{api_key_hash}
    Reverse: {PREFIX}:identity:apikeys:{user_id}
"""

import json
from typing import Optional

from loguru import logger
from shared.core.config import settings
from shared.services.redis.redis_service import RedisService

# Resolved from the shared config so every service uses the same namespace.
_PREFIX: str = settings.REDIS_KEY_PREFIX

# Default TTL for JWT identity cache entries (1 hour).
_JWT_TTL_SECONDS: int = 3600

# Upper bound TTL for API-key identity cache entries (1 hour).
_APIKEY_MAX_TTL_SECONDS: int = 3600


class IdentityCache:
    """Redis-backed identity cache for user_id + user_tier resolution."""

    # ------------------------------------------------------------------
    # Key builders
    # ------------------------------------------------------------------

    @staticmethod
    def _jwt_key(user_id: str) -> str:
        return f"identity:jwt:{user_id}"

    @staticmethod
    def _apikey_key(api_key_hash: str) -> str:
        return f"identity:apikey:{api_key_hash}"

    @staticmethod
    def _reverse_key(user_id: str) -> str:
        return f"identity:apikeys:{user_id}"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_cached_identity(
        self,
        redis: RedisService,
        cache_key: str,
    ) -> Optional[dict]:
        """Return cached ``{user_id, user_tier}`` or ``None`` on miss."""
        try:
            raw: Optional[str] = await redis.get(cache_key)
            if raw is None:
                return None
            # RedisService.get already attempts JSON parse, but the
            # value may come back as a dict directly.
            if isinstance(raw, dict):
                return raw
            return json.loads(raw)
        except Exception:
            logger.warning(
                "identity_cache: failed to read cache_key={}",
                cache_key,
            )
            return None

    # ------------------------------------------------------------------
    # Write -- JWT
    # ------------------------------------------------------------------

    async def set_jwt_identity(
        self,
        redis: RedisService,
        user_id: str,
        user_tier: str,
    ) -> None:
        """Cache identity for a JWT-authenticated user (1 hr TTL)."""
        key: str = self._jwt_key(user_id)
        payload: dict = {"user_id": user_id, "user_tier": user_tier}
        try:
            await redis.set(key, payload, ttl=_JWT_TTL_SECONDS)
        except Exception:
            logger.warning(
                "identity_cache: failed to set jwt identity user_id={}",
                user_id,
            )

    # ------------------------------------------------------------------
    # Write -- API key
    # ------------------------------------------------------------------

    async def set_apikey_identity(
        self,
        redis: RedisService,
        api_key_hash: str,
        user_id: str,
        user_tier: str,
        ttl_seconds: int,
    ) -> None:
        """Cache identity for an API-key-authenticated user.

        TTL is ``min(APIKEY_MAX_TTL, api_key_remaining_ttl)`` so the
        cache never outlives the key itself.  Also maintains a reverse
        index (SET) of all cached API-key hashes per user for bulk
        invalidation.
        """
        effective_ttl: int = min(_APIKEY_MAX_TTL_SECONDS, ttl_seconds)
        key: str = self._apikey_key(api_key_hash)
        payload: dict = {"user_id": user_id, "user_tier": user_tier}
        try:
            await redis.set(key, payload, ttl=effective_ttl)
            # Maintain reverse index so invalidate_user can find all
            # API-key cache entries belonging to this user.
            reverse_key: str = self._reverse_key(user_id)
            await redis.sadd(reverse_key, api_key_hash)
            # Keep reverse index TTL aligned with the API-key cache TTL.
            await redis.expire(reverse_key, effective_ttl)
        except Exception:
            logger.warning(
                "identity_cache: failed to set apikey identity "
                "api_key_hash={}, user_id={}",
                api_key_hash,
                user_id,
            )

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    async def invalidate_user(
        self,
        redis: RedisService,
        user_id: str,
    ) -> None:
        """Full invalidation: JWT cache + all API-key caches + reverse index."""
        try:
            # 1. Delete JWT cache
            jwt_key: str = self._jwt_key(user_id)
            await redis.delete(jwt_key)

            # 2. Collect all cached API-key hashes from reverse index
            reverse_key: str = self._reverse_key(user_id)
            api_key_hashes: set = await redis.smembers(reverse_key)

            # 3. Delete each API-key cache entry
            for api_key_hash in api_key_hashes:
                apikey_key: str = self._apikey_key(str(api_key_hash))
                await redis.delete(apikey_key)

            # 4. Delete the reverse index itself
            await redis.delete(reverse_key)
        except Exception:
            logger.warning(
                "identity_cache: failed to invalidate user_id={}",
                user_id,
            )

    async def invalidate_apikey(
        self,
        redis: RedisService,
        user_id: str,
        api_key_hash: str,
    ) -> None:
        """Delete a single API-key cache entry and remove from reverse index."""
        try:
            apikey_key: str = self._apikey_key(api_key_hash)
            await redis.delete(apikey_key)

            reverse_key: str = self._reverse_key(user_id)
            await redis.srem(reverse_key, api_key_hash)
        except Exception:
            logger.warning(
                "identity_cache: failed to invalidate apikey "
                "api_key_hash={}, user_id={}",
                api_key_hash,
                user_id,
            )


# Module-level singleton so callers can import directly.
identity_cache = IdentityCache()
