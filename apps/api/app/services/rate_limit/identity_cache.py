"""Redis-backed rate-limit identity cache for user_id + user_tier."""

import json

from loguru import logger

from shared.services.redis.redis_service import RedisService

_JWT_TTL_SECONDS: int = 3600


class IdentityCache:
    """Cache resolved rate-limit identity by user_id."""

    @staticmethod
    def get_user_key(user_id: str) -> str:
        return f"identity:user:{user_id}"

    async def get_cached_identity(
        self,
        redis: RedisService,
        cache_key: str,
    ) -> dict[str, str] | None:
        """Return cached ``{user_id, user_tier}`` or ``None`` on miss."""
        try:
            raw_identity: object = await redis.get(cache_key)
            return self._coerce_identity(raw_identity)
        except Exception:
            logger.warning(
                "identity_cache: failed to read cache_key={}",
                cache_key,
            )
            return None

    async def set_jwt_identity(
        self,
        redis: RedisService,
        user_id: str,
        user_tier: str,
    ) -> None:
        """Cache rate-limit identity for a user."""
        key: str = self.get_user_key(user_id)
        payload: dict[str, str] = {"user_id": user_id, "user_tier": user_tier}
        try:
            await redis.set(key, payload, ttl=_JWT_TTL_SECONDS)
        except Exception:
            logger.warning(
                "identity_cache: failed to set jwt identity user_id={}",
                user_id,
            )

    async def invalidate_user(
        self,
        redis: RedisService,
        user_id: str,
    ) -> None:
        """Delete cached rate-limit identity for a user."""
        try:
            await redis.delete(self.get_user_key(user_id))
        except Exception:
            logger.warning(
                "identity_cache: failed to invalidate user_id={}",
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


identity_cache = IdentityCache()
