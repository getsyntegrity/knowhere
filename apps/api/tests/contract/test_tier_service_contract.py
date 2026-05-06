from typing import TYPE_CHECKING, cast

import pytest

from app.services.rate_limit.tier_service import TierService
from shared.core.exceptions.domain_exceptions import NotFoundException

if TYPE_CHECKING:
    from shared.services.redis.redis_service import RedisService
else:
    RedisService = object


class FakeRedisService:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> object | None:
        return self.values.get(key)

    async def set(self, key: str, value: object, ttl: int | None = None) -> bool:
        self.values[key] = value
        if ttl is not None:
            self.ttls[key] = ttl
        return True

    async def delete(self, *keys: str) -> int:
        deleted_count = 0
        for key in keys:
            cached_value = self.values.pop(key, None)
            self.ttls.pop(key, None)
            if cached_value is not None:
                deleted_count += 1
        return deleted_count


@pytest.mark.asyncio
async def test_tier_cache_should_store_user_tier_without_identity_payload() -> None:
    fake_redis = FakeRedisService()
    redis_service = cast(RedisService, fake_redis)

    await TierService._set_cached_tier(redis_service, "user-one", "tier_5")

    cache_key = TierService._get_user_tier_key("user-one")
    assert await TierService._get_cached_tier(redis_service, "user-one") == "tier_5"
    assert fake_redis.values[cache_key] == "tier_5"
    assert fake_redis.ttls[cache_key] == 3600


@pytest.mark.asyncio
async def test_tier_cache_invalidation_should_only_delete_user_tier_key() -> None:
    fake_redis = FakeRedisService()
    redis_service = cast(RedisService, fake_redis)

    await TierService._set_cached_tier(redis_service, "user-one", "tier_5")
    fake_redis.values["api-key:user-one"] = "should-stay"

    await redis_service.delete(TierService._get_user_tier_key("user-one"))

    assert await TierService._get_cached_tier(redis_service, "user-one") is None
    assert fake_redis.values["api-key:user-one"] == "should-stay"


@pytest.mark.asyncio
async def test_get_tier_from_db_should_raise_when_user_tier_is_missing() -> None:
    class EmptySession:
        async def execute(self, statement: object) -> object:
            class EmptyResult:
                def scalar_one_or_none(self) -> object | None:
                    return None

            return EmptyResult()

    with pytest.raises(NotFoundException):
        await TierService._get_tier_from_db(
            cast(object, EmptySession()),
            "missing-user",
        )
