"""Redis-backed user-tier cache for rate-limit identity resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from shared.services.redis.redis_service import RedisService

_USER_TIER_TTL_SECONDS: int = 3600


class IdentityCache:
    """Cache resolved rate-limit user tier by user_id."""

    @staticmethod
    def get_user_tier_key(user_id: str) -> str:
        """Return the Redis key for a user's rate-limit tier."""
        return f"identity:user-tier:{user_id}"

    async def get_user_tier(
        self,
        redis: RedisService,
        user_id: str,
    ) -> dict[str, str] | None:
        """Return cached ``{user_id, user_tier}`` or ``None`` on miss."""
        cache_key: str = self.get_user_tier_key(user_id)
        try:
            raw_identity: object = await redis.get(cache_key)
            return self._coerce_identity(raw_identity)
        except Exception:
            logger.warning(
                "identity_cache: failed to read cache_key={}",
                cache_key,
            )
            return None

    async def set_user_tier(
        self,
        redis: RedisService,
        user_id: str,
        user_tier: str,
    ) -> None:
        """Cache rate-limit tier for a user."""
        key: str = self.get_user_tier_key(user_id)
        payload: dict[str, str] = {"user_id": user_id, "user_tier": user_tier}
        try:
            await redis.set(key, payload, ttl=_USER_TIER_TTL_SECONDS)
        except Exception:
            logger.warning(
                "identity_cache: failed to set user tier for user_id={}",
                user_id,
            )

    async def invalidate_user(
        self,
        redis: RedisService,
        user_id: str,
    ) -> None:
        """Delete cached rate-limit tier for a user."""
        try:
            await redis.delete(self.get_user_tier_key(user_id))
        except Exception:
            logger.warning(
                "identity_cache: failed to invalidate user_id={}",
                user_id,
            )

    def _coerce_identity(self, raw_identity: object) -> dict[str, str] | None:
        """Return a typed identity from current or legacy Redis values."""
        if not isinstance(raw_identity, dict):
            return None

        raw_user_id: object = raw_identity.get("user_id")
        raw_user_tier: object = raw_identity.get("user_tier")
        if not isinstance(raw_user_id, str) or not isinstance(raw_user_tier, str):
            return None

        return {"user_id": raw_user_id, "user_tier": raw_user_tier}


identity_cache = IdentityCache()
