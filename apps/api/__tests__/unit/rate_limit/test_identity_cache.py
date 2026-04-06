import pytest

fakeredis = pytest.importorskip("fakeredis.aioredis")

from app.services.rate_limit.config import REDIS_KEY_PREFIX
from app.services.rate_limit.identity_cache import IdentityCache

from .helpers import FakeRedisService


def test_identity_cache_key_prefixes():
    cache = IdentityCache()
    assert cache._jwt_key("u1") == f"{REDIS_KEY_PREFIX}identity:jwt:u1"
    assert cache._apikey_key("h1") == f"{REDIS_KEY_PREFIX}identity:apikey:h1"
    assert cache._reverse_key("u1") == f"{REDIS_KEY_PREFIX}identity:apikeys:u1"


@pytest.mark.asyncio
async def test_set_jwt_identity_and_get_cached_identity():
    cache = IdentityCache()
    redis = fakeredis.FakeRedis(decode_responses=True)
    svc = FakeRedisService(redis)

    await cache.set_jwt_identity(svc, "user_a", "tier_2")
    key = cache._jwt_key("user_a")
    cached = await cache.get_cached_identity(svc, key)

    assert cached == {"user_id": "user_a", "user_tier": "tier_2"}


@pytest.mark.asyncio
async def test_set_apikey_identity_caps_ttl_and_maintains_reverse_index():
    cache = IdentityCache()
    redis = fakeredis.FakeRedis(decode_responses=True)
    svc = FakeRedisService(redis)

    await cache.set_apikey_identity(
        svc,
        api_key_hash="hash_1",
        user_id="user_b",
        user_tier="tier_3",
        ttl_seconds=7200,
        enabled_modules=["guest"],
    )

    apikey_key = cache._apikey_key("hash_1")
    reverse_key = cache._reverse_key("user_b")
    cached = await cache.get_cached_identity(svc, apikey_key)
    members = await svc.smembers(reverse_key)
    apikey_ttl = await redis.ttl(apikey_key)
    reverse_ttl = await redis.ttl(reverse_key)

    assert cached == {
        "user_id": "user_b",
        "user_tier": "tier_3",
        "enabled_modules": ["guest"],
    }
    assert members == {"hash_1"}
    assert 1 <= apikey_ttl <= 3600
    assert 1 <= reverse_ttl <= 3600


@pytest.mark.asyncio
async def test_set_apikey_identity_does_not_shorten_reverse_index_ttl():
    cache = IdentityCache()
    redis = fakeredis.FakeRedis(decode_responses=True)
    svc = FakeRedisService(redis)

    await cache.set_apikey_identity(
        svc,
        api_key_hash="hash_long",
        user_id="user_ttl",
        user_tier="tier_1",
        ttl_seconds=300,
    )
    reverse_key = cache._reverse_key("user_ttl")
    before_ttl = await svc.ttl(reverse_key)

    await cache.set_apikey_identity(
        svc,
        api_key_hash="hash_short",
        user_id="user_ttl",
        user_tier="tier_1",
        ttl_seconds=10,
    )
    after_ttl = await svc.ttl(reverse_key)

    # Second insert with shorter ttl must not reduce the reverse-set ttl.
    assert after_ttl >= before_ttl - 1


@pytest.mark.asyncio
async def test_invalidate_user_clears_jwt_apikey_and_reverse_index():
    cache = IdentityCache()
    redis = fakeredis.FakeRedis(decode_responses=True)
    svc = FakeRedisService(redis)

    await cache.set_jwt_identity(svc, "user_c", "free")
    await cache.set_apikey_identity(
        svc, api_key_hash="k1", user_id="user_c", user_tier="free", ttl_seconds=300
    )
    await cache.set_apikey_identity(
        svc, api_key_hash="k2", user_id="user_c", user_tier="free", ttl_seconds=300
    )

    await cache.invalidate_user(svc, "user_c")

    assert await cache.get_cached_identity(svc, cache._jwt_key("user_c")) is None
    assert await cache.get_cached_identity(svc, cache._apikey_key("k1")) is None
    assert await cache.get_cached_identity(svc, cache._apikey_key("k2")) is None
    assert await svc.smembers(cache._reverse_key("user_c")) == set()


@pytest.mark.asyncio
async def test_invalidate_apikey_removes_single_key_and_reverse_member():
    cache = IdentityCache()
    redis = fakeredis.FakeRedis(decode_responses=True)
    svc = FakeRedisService(redis)

    await cache.set_apikey_identity(
        svc, api_key_hash="k1", user_id="user_d", user_tier="free", ttl_seconds=300
    )
    await cache.set_apikey_identity(
        svc, api_key_hash="k2", user_id="user_d", user_tier="free", ttl_seconds=300
    )

    await cache.invalidate_apikey(svc, "user_d", "k1")

    assert await cache.get_cached_identity(svc, cache._apikey_key("k1")) is None
    assert await cache.get_cached_identity(
        svc, cache._apikey_key("k2")
    ) == {"user_id": "user_d", "user_tier": "free"}
    assert await svc.smembers(cache._reverse_key("user_d")) == {"k2"}
