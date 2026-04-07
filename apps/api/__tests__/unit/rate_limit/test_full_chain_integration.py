"""
End-to-end integration test for the full rate-limit dependency chain.

Exercises:  with_current_user (L0)  ->  require_billing_limits (L1)
            ->  enforce_job_creation_capacity (L2 + L3)

Uses fakeredis for all Redis-backed layers and monkeypatch stubs for
DB-only paths (identity lookup, concurrency lock, active-job count).
"""

from types import SimpleNamespace

import pytest

fakeredis = pytest.importorskip("fakeredis.aioredis")

from app.services.rate_limit import dependencies as deps
from app.services.rate_limit.data_structures import CurrentUser, TierLimits
from app.services.rate_limit.limiter import RateLimiter as _RealRateLimiter
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)

from .helpers import (
    DEFAULT_SYSTEM_RULES,
    FAKE_DB,
    FakeRedisService,
    async_none,
    async_value,
    build_real_config,
    make_request,
    resolve_dep,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FREE_LIMITS = TierLimits(rpm_limit=5, max_concurrent_jobs=2, daily_quota=10)
_TIER1_LIMITS = TierLimits(rpm_limit=15, max_concurrent_jobs=5, daily_quota=-1)

_TIER_MAP: dict[str, TierLimits] = {
    "free": _FREE_LIMITS,
    "tier_1": _TIER1_LIMITS,
}


# ---------------------------------------------------------------------------
# Monkeypatch wiring
# ---------------------------------------------------------------------------


def _wire_common(monkeypatch, config, redis_client, user_tier: str = "free"):
    """Patch all external dependencies so the full chain runs in-process."""
    redis_service = FakeRedisService(redis_client)

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
    config, redis_client = build_real_config(monkeypatch, _TIER_MAP)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    monkeypatch.setattr(
        deps, "_acquire_user_concurrency_lock", async_none
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(0)
    )

    # L0 + identity
    request = make_request()
    current_user = await resolve_dep(deps.with_current_user(request=request, user_id="u_e2e"))
    assert current_user == CurrentUser(user_id="u_e2e", user_tier="free")

    # L1
    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        _db=FAKE_DB,
    )
    yielded = await agen.__anext__()
    assert yielded == current_user
    await agen.aclose()

    # L2 + L3
    await deps.enforce_job_creation_capacity(request, FAKE_DB, current_user)


@pytest.mark.asyncio
async def test_full_chain_l1_rejects_after_rpm_exceeded(monkeypatch):
    """After exhausting the billing RPM, the next request must get 429."""
    tier_map = {
        "free": TierLimits(rpm_limit=1, max_concurrent_jobs=2, daily_quota=10),
    }
    config, redis_client = build_real_config(monkeypatch, tier_map)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    request = make_request()
    current_user = await resolve_dep(deps.with_current_user(request=request, user_id="u_l1_rpm"))

    # First request passes L1
    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        _db=FAKE_DB,
    )
    await agen.__anext__()
    await agen.aclose()

    # Second request hits L1 RPM limit
    with pytest.raises(RateLimitException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            _db=FAKE_DB,
        )
        await agen.__anext__()

    assert exc_info.value.limit == 1
    assert exc_info.value.period == "minute"


@pytest.mark.asyncio
async def test_full_chain_l2_rejects_when_concurrency_full(monkeypatch):
    """When active jobs >= max, L2 must reject before burning L3 quota."""
    config, redis_client = build_real_config(monkeypatch, _TIER_MAP)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", async_none)
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(2)  # == max_concurrent_jobs
    )

    request = make_request()
    current_user = await resolve_dep(deps.with_current_user(request=request, user_id="u_l2"))

    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        _db=FAKE_DB,
    )
    await agen.__anext__()
    await agen.aclose()

    with pytest.raises(RateLimitException) as exc_info:
        await deps.enforce_job_creation_capacity(request, FAKE_DB, current_user)

    assert exc_info.value.details.get("period") == "concurrent"
    assert exc_info.value.details.get("limit") == 2


@pytest.mark.asyncio
async def test_full_chain_l3_rejects_when_daily_quota_exhausted(monkeypatch):
    """Exhaust the daily quota and verify L3 blocks."""
    tier_map = {
        "free": TierLimits(rpm_limit=100, max_concurrent_jobs=10, daily_quota=2),
    }
    config, redis_client = build_real_config(monkeypatch, tier_map)
    _wire_common(monkeypatch, config, redis_client, user_tier="free")

    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", async_none)
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(0)
    )

    request = make_request()
    current_user = await resolve_dep(deps.with_current_user(request=request, user_id="u_l3"))

    # Burn quota with 2 requests
    for i in range(2):
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            _db=FAKE_DB,
        )
        await agen.__anext__()
        await agen.aclose()
        await deps.enforce_job_creation_capacity(request, FAKE_DB, current_user)

    # Third request should be blocked by daily quota
    agen = deps.require_billing_limits(
        request=request,
        current_user=current_user,
        _db=FAKE_DB,
    )
    await agen.__anext__()
    await agen.aclose()

    with pytest.raises(RateLimitException) as exc_info:
        await deps.enforce_job_creation_capacity(request, FAKE_DB, current_user)

    assert exc_info.value.limit == 2
    assert exc_info.value.period == "day"


@pytest.mark.asyncio
async def test_full_chain_paid_tier_skips_daily_quota(monkeypatch):
    """Paid tiers (daily_quota=-1) must skip L3 entirely."""
    config, redis_client = build_real_config(monkeypatch, _TIER_MAP)
    _wire_common(monkeypatch, config, redis_client, user_tier="tier_1")

    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", async_none)
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(0)
    )

    request = make_request()
    current_user = await resolve_dep(deps.with_current_user(request=request, user_id="u_paid"))
    assert current_user.user_tier == "tier_1"

    # Run through more requests than free daily_quota (10) — L3 should never block
    for i in range(15):
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            _db=FAKE_DB,
        )
        await agen.__anext__()
        await agen.aclose()
        await deps.enforce_job_creation_capacity(request, FAKE_DB, current_user)


@pytest.mark.asyncio
async def test_full_chain_l0_fails_open_l1_fails_close(monkeypatch):
    """L0 Redis error → passes through; L1 Redis error → 503."""
    class _BrokenRedisService:
        async def _get_client(self):
            raise RuntimeError("redis down")

        async def ping(self) -> bool:
            return False

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
        system_rules=DEFAULT_SYSTEM_RULES,
    )
    monkeypatch.setattr(
        deps.RateLimitConfig, "get_instance", classmethod(lambda _cls: config)
    )

    # L0 fail-open: should still return current_user
    request = make_request()
    current_user = await resolve_dep(deps.with_current_user(request=request, user_id="u_failover"))
    assert current_user == CurrentUser(user_id="u_failover", user_tier="free")

    # L1 fail-close: Redis client acquisition fails → 503
    with pytest.raises(UnavailableException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=current_user,
            _db=FAKE_DB,
        )
        await agen.__anext__()

    assert "Redis error in billing RPM check" in exc_info.value.internal_message
