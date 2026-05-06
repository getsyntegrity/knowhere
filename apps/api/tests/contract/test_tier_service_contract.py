from importlib import import_module
from typing import cast

import pytest

from tests.support.import_environment import configure_import_environment, ensure_import_paths

from app.services.rate_limit.tier_service import TierService as TierServiceType
from shared.core.exceptions.domain_exceptions import NotFoundException
from shared.services.redis.redis_service import RedisService

configure_import_environment()
ensure_import_paths()


def get_tier_service_class() -> type[TierServiceType]:
    """Import TierService after test import paths are configured."""
    module = import_module("app.services.rate_limit.tier_service")
    return cast(type[TierServiceType], module.TierService)


def get_not_found_exception_class() -> type[NotFoundException]:
    """Import NotFoundException after test import paths are configured."""
    module = import_module("shared.core.exceptions.domain_exceptions")
    return cast(type[NotFoundException], module.NotFoundException)


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
    tier_service_class = get_tier_service_class()
    fake_redis = FakeRedisService()
    redis_service = cast(RedisService, fake_redis)

    await tier_service_class._set_cached_tier(redis_service, "user-one", "tier_5")

    cache_key = tier_service_class._get_user_tier_key("user-one")
    assert await tier_service_class._get_cached_tier(redis_service, "user-one") == "tier_5"
    assert fake_redis.values[cache_key] == "tier_5"
    assert fake_redis.ttls[cache_key] == 3600


@pytest.mark.asyncio
async def test_tier_cache_invalidation_should_only_delete_user_tier_key() -> None:
    tier_service_class = get_tier_service_class()
    fake_redis = FakeRedisService()
    redis_service = cast(RedisService, fake_redis)

    await tier_service_class._set_cached_tier(redis_service, "user-one", "tier_5")
    fake_redis.values["api-key:user-one"] = "should-stay"

    await redis_service.delete(tier_service_class._get_user_tier_key("user-one"))

    assert await tier_service_class._get_cached_tier(redis_service, "user-one") is None
    assert fake_redis.values["api-key:user-one"] == "should-stay"


@pytest.mark.asyncio
async def test_get_tier_from_db_should_raise_when_user_tier_is_missing() -> None:
    tier_service_class = get_tier_service_class()
    not_found_exception_class = get_not_found_exception_class()

    class EmptySession:
        async def execute(self, statement: object) -> object:
            class EmptyResult:
                def scalar_one_or_none(self) -> object | None:
                    return None

            return EmptyResult()

    with pytest.raises(not_found_exception_class):
        await tier_service_class._get_tier_from_db(
            cast(object, EmptySession()),
            "missing-user",
        )
