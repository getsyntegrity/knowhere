"""
End-to-end integration test for the full rate-limit dependency chain.

Exercises:  with_current_user (L0)  ->  require_billing_limits (L1)
            ->  enforce_job_creation_capacity (L2 + L3)

Uses fakeredis for all Redis-backed layers and monkeypatch stubs for
DB-only paths (identity lookup, concurrency lock, active-job count).
"""

from typing import cast
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

fakeredis = pytest.importorskip("fakeredis.aioredis")

from app.services.rate_limit import dependencies as deps
from app.services.rate_limit.data_structures import CurrentUser, SystemRpmRule, TierLimits
from app.services.rate_limit.limiter import RateLimiter as _RealRateLimiter
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)
from fastapi import Request

# The _db / db parameters are never used at runtime in these tests because
# concurrency lock and job count are monkeypatched. We cast a sentinel
# object to AsyncSession to satisfy the type checker.
_MOCK_DB: AsyncSession = cast(AsyncSession, object())


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FREE_LIMITS = TierLimits(rpm_limit=5, max_concurrent_jobs=2, daily_quota=10)
_TIER1_LIMITS = TierLimits(rpm_limit=15, max_concurrent_jobs=5, daily_quota=-1)

_TIER_MAP: dict[str, TierLimits] = {
    "free": _FREE_LIMITS,
    "tier_1": _TIER1_LIMITS,
}

_SYSTEM_RULES: list[SystemRpmRule] = [
    SystemRpmRule(method="POST", api_pattern="/v1/jobs", priority=100, rpm=30),
    SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000),
]


class _FakeRedisService:
    def __init__(self, client) -> None:
        self._client = client

    async def _get_client(self):
        return self._client


def _make_request() -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/jobs",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def _build_real_config(monkeypatch, tier_map: dict[str, TierLimits]):
    """Create a real RateLimitConfig backed by fakeredis."""
    limits = pytest.importorskip("limits")
    limits_storage = pytest.importorskip("limits.aio.storage")
    limits_strategies = pytest.importorskip("limits.aio.strategies")
    redis_asyncio = pytest.importorskip("redis.asyncio")
    fake_server = fakeredis.FakeServer()

    def _fake_from_url(*_args, **_kwargs):
        return fakeredis.FakeRedis(server=fake_server, decode_responses=False)

    monkeypatch.setattr(redis_asyncio, "from_url", _fake_from_url, raising=False)
    if hasattr(redis_asyncio, "Redis"):
        monkeypatch.setattr(
            redis_asyncio.Redis,
            "from_url",
            classmethod(lambda _cls, *a, **k: _fake_from_url(*a, **k)),
            raising=False,
        )

    storage = limits_storage.RedisStorage(
        "async+redis://unused:6379/0",
        implementation="redispy",
    )
    config = SimpleNamespace(
        is_bypassed=False,
        tier_map=tier_map,
        system_rules=_SYSTEM_RULES,
        parse_rate=limits.parse,
        sliding_window=limits_strategies.MovingWindowRateLimiter(storage),
        fixed_window=limits_strategies.FixedWindowRateLimiter(storage),
        namespaced_namespace=lambda ns: f"knowhere-api:rate_limit:{ns}",
    )
    redis_client = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    return config, redis_client


# ---------------------------------------------------------------------------
# Monkeypatch wiring
# ---------------------------------------------------------------------------


def _wire_common(monkeypatch, config, redis_client, user_tier: str = "free"):
    """Patch all external dependencies so the full chain runs in-process."""
    redis_service = _FakeRedisService(redis_client)

    async def _cached_identity(_redis, _cache_key):
        return None  # force DB fallback

    async def _db_tier(_user_id: str):
        return user_tier

    async def _apikey_ttl(_hash: str):
        return 3600

    async def _set_jwt(_redis, _uid, _tier):
        pass

    monkeypatch.setattr(deps.redis_pool_manager, "get_redis_service", lambda: redis_service)
    monkeypatch.setattr(deps.identity_cache, "get_cached_identity", _cached_identity)
    monkeypatch.setattr(deps.identity_cache, "set_jwt_identity", _set_jwt)
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)
    monkeypatch.setattr(deps, "_resolve_apikey_cache_ttl_seconds", _apikey_ttl)
    monkeypatch.setattr(deps.RateLimitConfig, "get_instance", classmethod(lambda _cls: config))
    monkeypatch.setattr(deps, "RateLimiter", _RealRateLimiter)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_chain_allows_first_request(monkeypatch):
    """A single request through L0 -> L1 -> L2 -> L3 must succeed."""
    config, redis_client = _build_real_config(monkeypatch, _TIER_MAP)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    monkeypatch.setattr(
        deps, "_acquire_user_concurrency_lock", _async_none
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", _async_value(0)
    )

    # L0 + identity
    request = _make_request()
    current_user = await deps.with_current_user(request=request, user_id="u_e2e")
    assert current_user == CurrentUser(user_id="u_e2e", user_tier="free")

    # L1
    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        job_id="job_e2e_001",
        _db=_MOCK_DB,
    )
    yielded = await agen.__anext__()
    assert yielded == current_user
    assert request.state.job_id == "job_e2e_001"
    assert request.state.rate_limit_tier_limits == _FREE_LIMITS
    await agen.aclose()

    # L2 + L3
    await deps.enforce_job_creation_capacity(request, _MOCK_DB, current_user)


@pytest.mark.asyncio
async def test_full_chain_l1_rejects_after_rpm_exceeded(monkeypatch):
    """After exhausting the billing RPM, the next request must get 429."""
    tier_map = {
        "free": TierLimits(rpm_limit=1, max_concurrent_jobs=2, daily_quota=10),
    }
    config, redis_client = _build_real_config(monkeypatch, tier_map)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    request = _make_request()
    current_user = await deps.with_current_user(request=request, user_id="u_l1_rpm")

    # First request passes L1
    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        job_id="job_pass",
        _db=_MOCK_DB,
    )
    await agen.__anext__()
    await agen.aclose()

    # Second request hits L1 RPM limit
    with pytest.raises(RateLimitException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            job_id="job_blocked",
            _db=_MOCK_DB,
        )
        await agen.__anext__()

    assert exc_info.value.limit == 1
    assert exc_info.value.period == "minute"


@pytest.mark.asyncio
async def test_full_chain_l2_rejects_when_concurrency_full(monkeypatch):
    """When active jobs >= max, L2 must reject before burning L3 quota."""
    config, redis_client = _build_real_config(monkeypatch, _TIER_MAP)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", _async_none)
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", _async_value(2)  # == max_concurrent_jobs
    )

    request = _make_request()
    current_user = await deps.with_current_user(request=request, user_id="u_l2")

    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        job_id="job_l2",
        _db=_MOCK_DB,
    )
    await agen.__anext__()
    await agen.aclose()

    with pytest.raises(RateLimitException) as exc_info:
        await deps.enforce_job_creation_capacity(request, _MOCK_DB, current_user)

    assert exc_info.value.details.get("period") == "concurrent"
    assert exc_info.value.details.get("limit") == 2


@pytest.mark.asyncio
async def test_full_chain_l3_rejects_when_daily_quota_exhausted(monkeypatch):
    """Exhaust the daily quota and verify L3 blocks."""
    tier_map = {
        "free": TierLimits(rpm_limit=100, max_concurrent_jobs=10, daily_quota=2),
    }
    config, redis_client = _build_real_config(monkeypatch, tier_map)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", _async_none)
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", _async_value(0)
    )

    request = _make_request()
    current_user = await deps.with_current_user(request=request, user_id="u_l3")

    # Burn quota with 2 requests
    for i in range(2):
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            job_id=f"job_l3_{i}",
            _db=_MOCK_DB,
        )
        await agen.__anext__()
        await agen.aclose()
        await deps.enforce_job_creation_capacity(request, _MOCK_DB, current_user)

    # Third request should be blocked by daily quota
    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        job_id="job_l3_blocked",
        _db=_MOCK_DB,
    )
    await agen.__anext__()
    await agen.aclose()

    with pytest.raises(RateLimitException) as exc_info:
        await deps.enforce_job_creation_capacity(request, _MOCK_DB, current_user)

    assert exc_info.value.limit == 2
    assert exc_info.value.period == "day"


@pytest.mark.asyncio
async def test_full_chain_paid_tier_skips_daily_quota(monkeypatch):
    """Paid tiers (daily_quota=-1) must skip L3 entirely."""
    config, redis_client = _build_real_config(monkeypatch, _TIER_MAP)
    _wire_common(monkeypatch, config, redis_client, user_tier="tier_1")

    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", _async_none)
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", _async_value(0)
    )

    request = _make_request()
    current_user = await deps.with_current_user(request=request, user_id="u_paid")
    assert current_user.user_tier == "tier_1"

    # Run through more requests than free daily_quota (10) — L3 should never block
    for i in range(15):
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            job_id=f"job_paid_{i}",
            _db=_MOCK_DB,
        )
        await agen.__anext__()
        await agen.aclose()
        await deps.enforce_job_creation_capacity(request, _MOCK_DB, current_user)


@pytest.mark.asyncio
async def test_full_chain_l0_fails_open_l1_fails_close(monkeypatch):
    """L0 Redis error → passes through; L1 Redis error → 503."""
    class _BrokenRedisService:
        async def _get_client(self):
            raise RuntimeError("redis down")

    async def _cache_error(_redis, _cache_key):
        raise RuntimeError("redis down")

    async def _db_tier(_user_id: str):
        return "free"

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: _BrokenRedisService()
    )
    monkeypatch.setattr(deps.identity_cache, "get_cached_identity", _cache_error)
    monkeypatch.setattr(deps, "_resolve_user_tier_from_db", _db_tier)

    config = SimpleNamespace(
        is_bypassed=False,
        tier_map=_TIER_MAP,
        system_rules=_SYSTEM_RULES,
    )
    monkeypatch.setattr(
        deps.RateLimitConfig, "get_instance", classmethod(lambda _cls: config)
    )

    # L0 fail-open: should still return current_user
    request = _make_request()
    current_user = await deps.with_current_user(request=request, user_id="u_failover")
    assert current_user == CurrentUser(user_id="u_failover", user_tier="free")

    # L1 fail-close: Redis client acquisition fails → 503
    with pytest.raises(UnavailableException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            job_id="job_fail",
            _db=_MOCK_DB,
        )
        await agen.__anext__()

    assert "Redis error" in exc_info.value.internal_message


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def _async_none(*_args, **_kwargs):
    return None


def _async_value(value):
    async def _inner(*_args, **_kwargs):
        return value
    return _inner
