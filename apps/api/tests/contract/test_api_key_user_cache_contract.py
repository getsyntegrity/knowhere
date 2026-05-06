from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import TYPE_CHECKING, cast

import pytest

from tests.support.import_environment import configure_import_environment, ensure_import_paths

if TYPE_CHECKING:
    from app.services.auth.api_key_service import APIKeyService as APIKeyServiceType
    from shared.services.redis.redis_service import RedisService
else:
    APIKeyServiceType = object
    RedisService = object

configure_import_environment()
ensure_import_paths()


def get_api_key_service_class() -> type[APIKeyServiceType]:
    """Import APIKeyService after test import paths are configured."""
    module = import_module("app.services.auth.api_key_service")
    return cast(type[APIKeyServiceType], module.APIKeyService)


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
        deleted_count = 0
        for key in keys:
            cached_value = self.values.pop(key, None)
            cached_set = self.sets.pop(key, None)
            self.ttls.pop(key, None)
            if cached_value is not None or cached_set is not None:
                deleted_count += 1
        return deleted_count

    async def sadd(self, key: str, *values: object) -> int:
        members = self.sets.setdefault(key, set())
        previous_size = len(members)
        members.update(str(value) for value in values)
        return len(members) - previous_size

    async def srem(self, key: str, *values: object) -> int:
        members = self.sets.setdefault(key, set())
        removed_count = 0
        for value in values:
            string_value = str(value)
            if string_value in members:
                members.remove(string_value)
                removed_count += 1
        return removed_count

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = ttl
        return True


@pytest.mark.asyncio
async def test_api_key_cache_should_store_user_id_without_tier() -> None:
    service = get_api_key_service_class().get_instance()
    fake_redis = FakeRedisService()
    redis_service = cast(RedisService, fake_redis)

    await service._set_cached_user_id(
        redis_service,
        api_key_hash="hash-one",
        user_id="user-one",
        ttl_seconds=7200,
    )

    user_id_key = service._get_user_id_key("hash-one")
    user_api_keys_key = service._get_user_api_keys_key("user-one")

    assert await service._get_cached_user_id(redis_service, "hash-one") == "user-one"
    assert fake_redis.values[user_id_key] == "user-one"
    assert fake_redis.ttls[user_id_key] == 3600
    assert fake_redis.sets[user_api_keys_key] == {"hash-one"}
    assert fake_redis.ttls[user_api_keys_key] == 3600


@pytest.mark.asyncio
async def test_api_key_cache_invalidation_should_not_touch_tier_cache() -> None:
    service = get_api_key_service_class().get_instance()
    fake_redis = FakeRedisService()
    redis_service = cast(RedisService, fake_redis)

    await service._set_cached_user_id(redis_service, "hash-one", "user-one", 300)
    fake_redis.values["tier:user:user-one"] = "tier_5"

    await service._invalidate_cached_api_key_user_id(
        redis_service,
        user_id="user-one",
        api_key_hash="hash-one",
    )

    assert await service._get_cached_user_id(redis_service, "hash-one") is None
    assert fake_redis.values["tier:user:user-one"] == "tier_5"


def test_api_key_cache_ttl_should_not_exceed_api_key_expiration() -> None:
    service = get_api_key_service_class().get_instance()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=120)

    ttl_seconds = service._resolve_api_key_cache_ttl_seconds(expires_at)

    assert 1 <= ttl_seconds <= 120


def test_api_key_service_should_be_singleton() -> None:
    api_key_service_class = get_api_key_service_class()

    assert api_key_service_class.get_instance() is api_key_service_class()
