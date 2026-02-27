import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request

fakeredis = pytest.importorskip("fakeredis.aioredis")

from app.services.rate_limit import dependencies as deps
from app.services.rate_limit.data_structures import CurrentUser, SystemRpmRule
from shared.core.exceptions.domain_exceptions import RateLimitException


class _FakeRedisService:
    def __init__(self, client) -> None:
        self._client = client

    async def _get_client(self):
        return self._client

    async def set(self, key, value, ttl=None, ex=None):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        expire = ex or ttl
        return await self._client.set(key, value, ex=expire)

    async def get(self, key):
        value = await self._client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def delete(self, *keys):
        return await self._client.delete(*keys)

    async def sadd(self, key, *values):
        return await self._client.sadd(key, *values)

    async def smembers(self, key):
        return await self._client.smembers(key)

    async def srem(self, key, *values):
        return await self._client.srem(key, *values)

    async def expire(self, key, ttl):
        return await self._client.expire(key, ttl)

    async def ttl(self, key):
        return await self._client.ttl(key)


class _SystemConfig:
    def __init__(self) -> None:
        self.system_rules = [
            SystemRpmRule(
                method="POST",
                api_pattern="/v1/jobs",
                priority=100,
                rpm=30,
            )
        ]


class _PassSystemRateLimiter:
    calls: list[tuple[str, int, str]] = []

    def __init__(self, _config) -> None:
        pass

    async def check_system_rpm(
        self,
        user_id: str,
        rpm: int,
        matched_pattern: str,
    ) -> None:
        self.calls.append((user_id, rpm, matched_pattern))


class _Raise429SystemRateLimiter:
    def __init__(self, _config) -> None:
        pass

    async def check_system_rpm(
        self,
        _user_id: str,
        _rpm: int,
        _matched_pattern: str,
    ) -> None:
        raise RateLimitException(retry_after=7, limit=30, period="minute")


class _RaiseSystemErrorRateLimiter:
    def __init__(self, _config) -> None:
        pass

    async def check_system_rpm(
        self,
        _user_id: str,
        _rpm: int,
        _matched_pattern: str,
    ) -> None:
        raise RuntimeError("redis transient error")


def _make_request(authorization: str | None = None) -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/jobs",
        "headers": headers,
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_with_current_user_enforces_system_rpm(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)

    async def _cached_identity(_redis, _cache_key):
        return {"user_id": "u_sys_ok", "user_tier": "tier_1"}

    _PassSystemRateLimiter.calls.clear()
    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.identity_cache, "get_cached_identity", _cached_identity
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    request = _make_request()
    user = await deps.with_current_user(request=request, user_id="u_sys_ok")

    assert user == CurrentUser(user_id="u_sys_ok", user_tier="tier_1")
    assert _PassSystemRateLimiter.calls == [("u_sys_ok", 30, "/v1/jobs")]


@pytest.mark.asyncio
async def test_with_current_user_raises_on_system_rpm_exceeded(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)

    async def _cached_identity(_redis, _cache_key):
        return {"user_id": "u_sys_429", "user_tier": "free"}

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.identity_cache, "get_cached_identity", _cached_identity
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _Raise429SystemRateLimiter)

    request = _make_request()
    with pytest.raises(RateLimitException) as exc_info:
        await deps.with_current_user(request=request, user_id="u_sys_429")

    assert exc_info.value.retry_after == 7
    assert exc_info.value.limit == 30


@pytest.mark.asyncio
async def test_with_current_user_fail_open_on_system_rpm_error(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)

    async def _cached_identity(_redis, _cache_key):
        return {"user_id": "u_sys_open", "user_tier": "free"}

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.identity_cache, "get_cached_identity", _cached_identity
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _RaiseSystemErrorRateLimiter)

    request = _make_request()
    user = await deps.with_current_user(request=request, user_id="u_sys_open")
    assert user == CurrentUser(user_id="u_sys_open", user_tier="free")


@pytest.mark.asyncio
async def test_with_current_user_identity_jwt_cache_hit_skips_db_lookup(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)
    db_lookup_calls = 0

    async def _cache_hit(_redis, _cache_key):
        return {"user_id": "u_cache_hit", "user_tier": "tier_5"}

    async def _db_tier(_user_id: str):
        nonlocal db_lookup_calls
        db_lookup_calls += 1
        return "free"

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(deps.identity_cache, "get_cached_identity", _cache_hit)
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    request = _make_request()
    user = await deps.with_current_user(request=request, user_id="u_cache_hit")

    assert user == CurrentUser(user_id="u_cache_hit", user_tier="tier_5")
    assert db_lookup_calls == 0


@pytest.mark.asyncio
async def test_with_current_user_identity_jwt_cache_miss_reads_db_and_sets_cache(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)
    jwt_set_calls: list[tuple[str, str]] = []

    async def _cache_miss(_redis, _cache_key):
        return None

    async def _db_tier(_user_id: str):
        return "tier_2"

    async def _set_jwt_identity(_redis, user_id: str, user_tier: str):
        jwt_set_calls.append((user_id, user_tier))

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(deps.identity_cache, "get_cached_identity", _cache_miss)
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(deps.identity_cache, "set_jwt_identity", _set_jwt_identity)
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    request = _make_request()
    user = await deps.with_current_user(request=request, user_id="u_jwt_miss")

    assert user == CurrentUser(user_id="u_jwt_miss", user_tier="tier_2")
    assert jwt_set_calls == [("u_jwt_miss", "tier_2")]


@pytest.mark.asyncio
async def test_with_current_user_identity_apikey_cache_miss_sets_apikey_cache(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)
    api_key_token = "sk_test_123"
    api_key_hash = hashlib.sha256(api_key_token.encode()).hexdigest()

    observed_cache_keys: list[str] = []
    apikey_set_calls: list[tuple[str, str, str, int]] = []

    async def _cache_miss(_redis, cache_key: str):
        observed_cache_keys.append(cache_key)
        return None

    async def _db_tier(_user_id: str):
        return "tier_3"

    async def _apikey_ttl(_api_key_hash: str):
        return 123

    async def _set_apikey_identity(
        _redis,
        call_api_key_hash: str,
        call_user_id: str,
        call_user_tier: str,
        ttl_seconds: int,
    ):
        apikey_set_calls.append(
            (call_api_key_hash, call_user_id, call_user_tier, ttl_seconds)
        )

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(deps.identity_cache, "get_cached_identity", _cache_miss)
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(deps, "_resolve_apikey_cache_ttl_seconds", _apikey_ttl)
    monkeypatch.setattr(
        deps.identity_cache, "set_apikey_identity", _set_apikey_identity
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    request = _make_request(authorization=f"Bearer {api_key_token}")
    user = await deps.with_current_user(request=request, user_id="u_apikey")

    assert user == CurrentUser(user_id="u_apikey", user_tier="tier_3")
    assert observed_cache_keys == [deps.identity_cache._apikey_key(api_key_hash)]
    assert apikey_set_calls == [(api_key_hash, "u_apikey", "tier_3", 123)]


@pytest.mark.asyncio
async def test_with_current_user_identity_redis_error_falls_back_to_db(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)

    async def _cache_error(_redis, _cache_key):
        raise RuntimeError("redis unavailable")

    async def _db_tier(_user_id: str):
        return "tier_1"

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(deps.identity_cache, "get_cached_identity", _cache_error)
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    request = _make_request()
    user = await deps.with_current_user(request=request, user_id="u_redis_err")

    assert user == CurrentUser(user_id="u_redis_err", user_tier="tier_1")


@pytest.mark.asyncio
async def test_with_current_user_identity_revalidates_after_invalidate_user_jwt(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)
    db_tiers = iter(["free", "tier_2"])

    async def _db_tier(_user_id: str):
        return next(db_tiers)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    user_id = "u_revalidate_jwt"
    request = _make_request()
    user1 = await deps.with_current_user(request=request, user_id=user_id)
    assert user1 == CurrentUser(user_id=user_id, user_tier="free")

    jwt_key = deps.identity_cache._jwt_key(user_id)
    cached1 = await deps.identity_cache.get_cached_identity(redis_service, jwt_key)
    assert cached1 == {"user_id": user_id, "user_tier": "free"}

    await deps.identity_cache.invalidate_user(redis_service, user_id)
    cached_after_invalidate = await deps.identity_cache.get_cached_identity(
        redis_service, jwt_key
    )
    assert cached_after_invalidate is None

    user2 = await deps.with_current_user(request=request, user_id=user_id)
    assert user2 == CurrentUser(user_id=user_id, user_tier="tier_2")

    cached2 = await deps.identity_cache.get_cached_identity(redis_service, jwt_key)
    assert cached2 == {"user_id": user_id, "user_tier": "tier_2"}


@pytest.mark.asyncio
async def test_with_current_user_identity_revalidates_after_invalidate_user_apikey(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)
    db_tiers = iter(["free", "tier_4"])
    api_key_token = "sk_revalidate_token"
    api_key_hash = hashlib.sha256(api_key_token.encode()).hexdigest()
    user_id = "u_revalidate_apikey"

    async def _db_tier(_user_id: str):
        return next(db_tiers)

    async def _apikey_ttl(_api_key_hash: str):
        return 300

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(deps, "_resolve_apikey_cache_ttl_seconds", _apikey_ttl)
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _SystemConfig()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassSystemRateLimiter)

    request = _make_request(authorization=f"Bearer {api_key_token}")
    user1 = await deps.with_current_user(request=request, user_id=user_id)
    assert user1 == CurrentUser(user_id=user_id, user_tier="free")

    apikey_key = deps.identity_cache._apikey_key(api_key_hash)
    reverse_key = deps.identity_cache._reverse_key(user_id)
    cached1 = await deps.identity_cache.get_cached_identity(redis_service, apikey_key)
    assert cached1 == {"user_id": user_id, "user_tier": "free"}
    assert api_key_hash in (await redis_service.smembers(reverse_key))

    await deps.identity_cache.invalidate_user(redis_service, user_id)
    cached_after_invalidate = await deps.identity_cache.get_cached_identity(
        redis_service, apikey_key
    )
    assert cached_after_invalidate is None
    assert await redis_service.smembers(reverse_key) == set()

    user2 = await deps.with_current_user(request=request, user_id=user_id)
    assert user2 == CurrentUser(user_id=user_id, user_tier="tier_4")

    cached2 = await deps.identity_cache.get_cached_identity(redis_service, apikey_key)
    assert cached2 == {"user_id": user_id, "user_tier": "tier_4"}


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, value=None, should_raise: bool = False):
        self._value = value
        self._should_raise = should_raise

    async def execute(self, _stmt):
        if self._should_raise:
            raise RuntimeError("db failure")
        return _ScalarResult(self._value)


class _DBContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_extract_bearer_token_variants():
    assert deps._extract_bearer_token(None) is None
    assert deps._extract_bearer_token("Basic x") is None
    assert deps._extract_bearer_token("Bearer") is None
    assert deps._extract_bearer_token("Bearer ") is None
    assert deps._extract_bearer_token("Bearer abc.def") == "abc.def"
    assert deps._extract_bearer_token("bearer sk_x") == "sk_x"


def test_generate_job_id_format():
    job_id = deps.generate_job_id()
    assert job_id.startswith("job_")
    assert len(job_id) == len("job_") + 12


@pytest.mark.asyncio
async def test_resolve_user_tier_from_db_found(monkeypatch):
    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(value="tier_2")),
    )
    tier = await deps._resolve_user_tier_from_db("u_tier")
    assert tier == "tier_2"


@pytest.mark.asyncio
async def test_resolve_user_tier_from_db_missing_row_defaults_to_free(monkeypatch):
    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(value=None)),
    )
    tier = await deps._resolve_user_tier_from_db("u_missing")
    assert tier == "free"


@pytest.mark.asyncio
async def test_resolve_user_tier_from_db_error_defaults_to_free(monkeypatch):
    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(should_raise=True)),
    )
    tier = await deps._resolve_user_tier_from_db("u_error")
    assert tier == "free"


@pytest.mark.asyncio
async def test_resolve_apikey_cache_ttl_seconds_none_uses_max(monkeypatch):
    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(value=None)),
    )
    ttl = await deps._resolve_apikey_cache_ttl_seconds("hash_x")
    assert ttl == 3600


@pytest.mark.asyncio
async def test_resolve_apikey_cache_ttl_seconds_clamps_to_remaining_and_min(monkeypatch):
    near_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=120
    )
    expired = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=10
    )

    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(value=near_future)),
    )
    ttl_future = await deps._resolve_apikey_cache_ttl_seconds("hash_future")
    assert 1 <= ttl_future <= 120

    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(value=expired)),
    )
    ttl_expired = await deps._resolve_apikey_cache_ttl_seconds("hash_expired")
    assert ttl_expired == 1


@pytest.mark.asyncio
async def test_resolve_apikey_cache_ttl_seconds_error_uses_max(monkeypatch):
    monkeypatch.setattr(
        deps,
        "get_db_context",
        lambda: _DBContext(_FakeDB(should_raise=True)),
    )
    ttl = await deps._resolve_apikey_cache_ttl_seconds("hash_error")
    assert ttl == 3600
