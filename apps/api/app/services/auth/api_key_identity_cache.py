"""Redis-backed API-key authentication user cache."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from shared.services.redis.redis_service import RedisService

_API_KEY_MAX_TTL_SECONDS: int = 3600


class APIKeyIdentityCache:
    """Cache validated API-key user IDs by API-key lookup hash."""

    @staticmethod
    def get_cache_key(api_key_hash: str) -> str:
        """Return the Redis key for an API-key hash."""
        return f"identity:apikey:{api_key_hash}"

    @staticmethod
    def get_reverse_key(user_id: str) -> str:
        """Return the reverse-index Redis key for a user."""
        return f"identity:apikeys:{user_id}"

    async def get_user_id(
        self,
        redis: RedisService,
        api_key_hash: str,
    ) -> str | None:
        """Return cached user_id for an API key."""
        try:
            raw_user_id: object = await redis.get(self.get_cache_key(api_key_hash))
            return self._coerce_user_id(raw_user_id)
        except Exception:
            logger.warning("api_key_identity_cache: failed to read user")
            return None

    async def set_user_id(
        self,
        redis: RedisService,
        api_key_hash: str,
        user_id: str,
        ttl_seconds: int,
    ) -> None:
        """Cache a validated API-key user ID."""
        effective_ttl_seconds: int = min(_API_KEY_MAX_TTL_SECONDS, ttl_seconds)
        cache_key: str = self.get_cache_key(api_key_hash)
        reverse_key: str = self.get_reverse_key(user_id)

        try:
            await redis.set(cache_key, user_id, ttl=effective_ttl_seconds)
            await redis.sadd(reverse_key, api_key_hash)
            current_ttl_seconds: int = await redis.ttl(reverse_key)
            if (
                current_ttl_seconds in (-2, -1)
                or current_ttl_seconds < effective_ttl_seconds
            ):
                await redis.expire(reverse_key, effective_ttl_seconds)
        except Exception:
            logger.warning(
                "api_key_identity_cache: failed to set user for user_id={}",
                user_id,
            )

    async def invalidate_api_key(
        self,
        redis: RedisService,
        user_id: str,
        api_key_hash: str,
    ) -> None:
        """Delete one API-key identity cache entry."""
        try:
            await redis.delete(self.get_cache_key(api_key_hash))
            await redis.srem(self.get_reverse_key(user_id), api_key_hash)
        except Exception:
            logger.warning(
                "api_key_identity_cache: failed to invalidate identity for user_id={}",
                user_id,
            )

    def _coerce_user_id(self, raw_user_id: object) -> str | None:
        """Return a typed user ID from current or legacy Redis values."""
        if isinstance(raw_user_id, str):
            try:
                parsed_user_id: object = json.loads(raw_user_id)
            except json.JSONDecodeError:
                return raw_user_id
        else:
            parsed_user_id = raw_user_id

        if isinstance(parsed_user_id, str):
            return parsed_user_id

        if isinstance(parsed_user_id, dict):
            legacy_user_id: object = parsed_user_id.get("user_id")
            if isinstance(legacy_user_id, str):
                return legacy_user_id

        return None


api_key_identity_cache = APIKeyIdentityCache()
