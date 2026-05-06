import builtins
from typing import TYPE_CHECKING, cast

import pytest

from app.services.auth.api_key_identity_cache import APIKeyIdentityCache
from app.services.rate_limit.identity_cache import IdentityCache

if TYPE_CHECKING:
    from shared.services.redis.redis_service import RedisService
else:
    RedisService = object


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> object | None:
        return self.values.get(key)

    async def set(self, key: str, value: object, ttl: int | None = None) -> bool:
        self.values[key] = value
        if ttl is not None:
            self.ttls[key] = ttl
        return True

    async def delete(self, *keys: str) -> int:
        deleted_count: int = 0
        for key in keys:
            deleted_value: object | None = self.values.pop(key, None)
            deleted_set: set[str] | None = self.sets.pop(key, None)
            self.ttls.pop(key, None)
            if deleted_value is not None or deleted_set is not None:
                deleted_count += 1
        return deleted_count

    async def sadd(self, key: str, *values: object) -> int:
        members: builtins.set[str] = self.sets.setdefault(key, set())
        previous_size: int = len(members)
        members.update(str(value) for value in values)
        return len(members) - previous_size

    async def srem(self, key: str, *values: object) -> int:
        members: builtins.set[str] = self.sets.setdefault(key, set())
        removed_count: int = 0
        for value in values:
            if str(value) in members:
                members.remove(str(value))
                removed_count += 1
        return removed_count

    async def smembers(self, key: str) -> builtins.set[str]:
        return set(self.sets.get(key, set()))

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = ttl
        return True


@pytest.mark.asyncio
async def test_api_key_identity_cache_should_store_user_id_without_tier() -> None:
    cache = APIKeyIdentityCache()
    fake_redis = FakeRedisService()
    redis = cast(RedisService, fake_redis)

    await cache.set_user_id(
        redis,
        api_key_hash="hash-one",
        user_id="user-one",
        ttl_seconds=7200,
    )

    assert await cache.get_user_id(redis, "hash-one") == "user-one"
    assert fake_redis.values[cache.get_cache_key("hash-one")] == "user-one"
    assert fake_redis.ttls[cache.get_cache_key("hash-one")] == 3600
    assert fake_redis.sets[cache.get_reverse_key("user-one")] == {"hash-one"}


@pytest.mark.asyncio
async def test_api_key_identity_cache_invalidation_should_not_touch_tier_cache() -> None:
    api_key_cache = APIKeyIdentityCache()
    tier_cache = IdentityCache()
    fake_redis = FakeRedisService()
    redis = cast(RedisService, fake_redis)

    await api_key_cache.set_user_id(redis, "hash-one", "user-one", ttl_seconds=300)
    await tier_cache.set_user_tier(redis, "user-one", "tier_5")

    await api_key_cache.invalidate_api_key(redis, "user-one", "hash-one")

    assert await api_key_cache.get_user_id(redis, "hash-one") is None
    assert await tier_cache.get_user_tier(redis, "user-one") == {
        "user_id": "user-one",
        "user_tier": "tier_5",
    }


@pytest.mark.asyncio
async def test_user_tier_cache_invalidation_should_not_touch_api_key_cache() -> None:
    api_key_cache = APIKeyIdentityCache()
    tier_cache = IdentityCache()
    fake_redis = FakeRedisService()
    redis = cast(RedisService, fake_redis)

    await api_key_cache.set_user_id(redis, "hash-one", "user-one", ttl_seconds=300)
    await tier_cache.set_user_tier(redis, "user-one", "tier_5")

    await tier_cache.invalidate_user(redis, "user-one")

    assert await api_key_cache.get_user_id(redis, "hash-one") == "user-one"
    assert await tier_cache.get_user_tier(redis, "user-one") is None
