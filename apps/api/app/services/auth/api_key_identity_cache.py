"""Redis-backed API-key authentication identity cache."""

import json

from loguru import logger

from shared.services.redis.redis_service import RedisService

_API_KEY_MAX_TTL_SECONDS: int = 3600


class APIKeyIdentityCache:
    """Cache validated API-key identities by API-key lookup hash."""

    @staticmethod
    def get_cache_key(api_key_hash: str) -> str:
        """Return the Redis key for an API-key hash."""
        return f"identity:apikey:{api_key_hash}"

    @staticmethod
    def get_reverse_key(user_id: str) -> str:
        """Return the reverse-index Redis key for a user."""
        return f"identity:apikeys:{user_id}"

    async def get_identity(
        self,
        redis: RedisService,
        api_key_hash: str,
    ) -> dict[str, str] | None:
        """Return cached ``{user_id, user_tier}`` for an API key."""
        try:
            raw_identity: object = await redis.get(self.get_cache_key(api_key_hash))
            return self._coerce_identity(raw_identity)
        except Exception:
            logger.warning(
                "api_key_identity_cache: failed to read identity",
            )
            return None

    async def set_identity(
        self,
        redis: RedisService,
        api_key_hash: str,
        user_id: str,
        user_tier: str,
        ttl_seconds: int,
    ) -> None:
        """Cache a validated API-key identity."""
        effective_ttl_seconds: int = min(_API_KEY_MAX_TTL_SECONDS, ttl_seconds)
        cache_key: str = self.get_cache_key(api_key_hash)
        reverse_key: str = self.get_reverse_key(user_id)
        payload: dict[str, str] = {"user_id": user_id, "user_tier": user_tier}

        try:
            await redis.set(cache_key, payload, ttl=effective_ttl_seconds)
            await redis.sadd(reverse_key, api_key_hash)
            current_ttl_seconds = await redis.ttl(reverse_key)
            if (
                current_ttl_seconds in (-2, -1)
                or current_ttl_seconds < effective_ttl_seconds
            ):
                await redis.expire(reverse_key, effective_ttl_seconds)
        except Exception:
            logger.warning(
                "api_key_identity_cache: failed to set identity for user_id={}",
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

    async def invalidate_user(
        self,
        redis: RedisService,
        user_id: str,
    ) -> None:
        """Delete all API-key identity cache entries for a user."""
        try:
            reverse_key: str = self.get_reverse_key(user_id)
            api_key_hashes: set[object] = await redis.smembers(reverse_key)
            for api_key_hash in api_key_hashes:
                await redis.delete(self.get_cache_key(str(api_key_hash)))
            await redis.delete(reverse_key)
        except Exception:
            logger.warning(
                "api_key_identity_cache: failed to invalidate user_id={}",
                user_id,
            )

    def _coerce_identity(self, raw_identity: object) -> dict[str, str] | None:
        """Return a typed identity payload from a Redis value."""
        parsed_identity = raw_identity
        if isinstance(raw_identity, str):
            parsed_identity = json.loads(raw_identity)

        if not isinstance(parsed_identity, dict):
            return None

        user_id = parsed_identity.get("user_id")
        user_tier = parsed_identity.get("user_tier")
        if not isinstance(user_id, str) or not isinstance(user_tier, str):
            return None

        return {"user_id": user_id, "user_tier": user_tier}


api_key_identity_cache = APIKeyIdentityCache()
