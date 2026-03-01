"""Shared test helpers for rate_limit unit tests."""

import json
from typing import cast

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

fakeredis = pytest.importorskip("fakeredis.aioredis")

from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits

# Sentinel AsyncSession — never actually used at runtime because DB calls
# are monkeypatched, but satisfies the type checker.
FAKE_DB: AsyncSession = cast(AsyncSession, object())

DEFAULT_SYSTEM_RULES: list[SystemRpmRule] = [
    SystemRpmRule(method="POST", api_pattern="/v1/jobs", priority=100, rpm=30),
    SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000),
]


class FakeRedisService:
    """Superset fake that covers both _get_client (deps) and high-level
    set/get/delete/sadd/smembers/srem/expire/ttl (identity_cache) usage."""

    def __init__(self, client) -> None:
        self._client = client

    async def _get_client(self):
        return self._client

    async def ping(self) -> bool:
        return True

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


def make_request(authorization: str | None = None) -> Request:
    """Build a minimal ASGI Request for POST /v1/jobs."""
    headers: list[tuple[bytes, bytes]] = []
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


def build_real_config(
    monkeypatch,
    tier_map: dict[str, TierLimits],
    system_rules: list[SystemRpmRule] | None = None,
):
    """Create a real RateLimitConfig backed by fakeredis."""
    from types import SimpleNamespace

    limits = pytest.importorskip("limits")
    limits_storage = pytest.importorskip("limits.aio.storage")
    limits_strategies = pytest.importorskip("limits.aio.strategies")
    redis_asyncio = pytest.importorskip("redis.asyncio")
    fake_server = fakeredis.FakeServer()

    def _fake_from_url(*_args, **_kwargs):
        return fakeredis.FakeRedis(
            server=fake_server, decode_responses=False
        )

    monkeypatch.setattr(
        redis_asyncio, "from_url", _fake_from_url, raising=False
    )
    if hasattr(redis_asyncio, "Redis"):
        monkeypatch.setattr(
            redis_asyncio.Redis,
            "from_url",
            classmethod(
                lambda _cls, *a, **k: _fake_from_url(*a, **k)
            ),
            raising=False,
        )

    storage = limits_storage.RedisStorage(
        "async+redis://unused:6379/0",
        implementation="redispy",
    )
    rules = system_rules if system_rules is not None else DEFAULT_SYSTEM_RULES
    config = SimpleNamespace(
        is_bypassed=False,
        tier_map=tier_map,
        system_rules=rules,
        parse_rate=limits.parse,
        sliding_window=limits_strategies.MovingWindowRateLimiter(storage),
        fixed_window=limits_strategies.FixedWindowRateLimiter(storage),
        namespaced_namespace=lambda ns: f"knowhere-api:rate_limit:{ns}",
    )
    redis_client = fakeredis.FakeRedis(
        server=fake_server, decode_responses=True
    )
    return config, redis_client


async def async_none(*_args, **_kwargs):
    """Async callable that returns None."""
    return None


def async_value(value):
    """Factory: returns an async callable that returns *value*."""
    async def _inner(*_args, **_kwargs):
        return value
    return _inner
