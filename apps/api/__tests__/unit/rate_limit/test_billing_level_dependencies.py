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
    FAKE_DB,
    FakeRedisService,
    async_none,
    async_value,
    build_real_config,
    make_request,
)


class _FakeConfig:
    def __init__(self, max_concurrent_jobs: int, daily_quota: int = 10) -> None:
        self.is_bypassed = False
        self.tier_map = {
            "free": TierLimits(
                rpm_limit=60,
                max_concurrent_jobs=max_concurrent_jobs,
                daily_quota=daily_quota,
            )
        }

    def namespaced_namespace(self, namespace: str) -> str:
        return f"knowhere-api:rate_limit:{namespace}"


class _PassRateLimiter:
    def __init__(self, _config) -> None:
        pass

    async def check_billing_rpm(self, _user_id: str, _rpm: int) -> None:
        return None

    async def check_daily_quota(self, _user_id: str, _quota: int) -> None:
        return None


class _DailyQuotaErrorRateLimiter:
    def __init__(self, _config) -> None:
        pass

    async def check_billing_rpm(self, _user_id: str, _rpm: int) -> None:
        return None

    async def check_daily_quota(self, _user_id: str, _quota: int) -> None:
        raise RuntimeError("daily quota redis failure")


@pytest.mark.asyncio
async def test_require_billing_limits_sets_job_state_and_tier_limits(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = FakeRedisService(redis)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=2)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    request = make_request()
    user = CurrentUser(user_id="u_ok", user_tier="free")

    agen = deps.require_billing_limits(
        request=request, current_user=user, _db=FAKE_DB
    )
    yielded_user = await agen.__anext__()
    assert yielded_user == user
    assert request.state.rate_limit_tier_limits == TierLimits(
        rpm_limit=60, max_concurrent_jobs=2, daily_quota=10
    )
    await agen.aclose()


@pytest.mark.asyncio
async def test_require_billing_limits_enforces_tier_rpm_with_real_rate_limiter(
    monkeypatch,
):
    config, redis_client = build_real_config(
        monkeypatch,
        {
            "free": TierLimits(
                rpm_limit=10,
                max_concurrent_jobs=2,
                daily_quota=20,
            ),
            "tier_2": TierLimits(
                rpm_limit=1,
                max_concurrent_jobs=10,
                daily_quota=-1,
            ),
        },
    )
    redis_service = FakeRedisService(redis_client)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _RealRateLimiter)

    request = make_request()
    user = CurrentUser(user_id="u_tier_2", user_tier="tier_2")

    agen = deps.require_billing_limits(
        request=request, current_user=user, _db=FAKE_DB
    )
    yielded_user = await agen.__anext__()
    assert yielded_user == user
    await agen.aclose()

    with pytest.raises(RateLimitException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=user,
            _db=FAKE_DB,
        )
        await agen.__anext__()
    assert exc_info.value.limit == 1


@pytest.mark.asyncio
async def test_require_billing_limits_applies_different_tier_rpm_limits(monkeypatch):
    config, redis_client = build_real_config(
        monkeypatch,
        {
            "free": TierLimits(
                rpm_limit=1,
                max_concurrent_jobs=2,
                daily_quota=20,
            ),
            "tier_1": TierLimits(
                rpm_limit=3,
                max_concurrent_jobs=5,
                daily_quota=-1,
            ),
        },
    )
    redis_service = FakeRedisService(redis_client)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _RealRateLimiter)

    request = make_request()
    free_user = CurrentUser(user_id="u_free", user_tier="free")
    tier1_user = CurrentUser(user_id="u_tier_1", user_tier="tier_1")

    agen = deps.require_billing_limits(
        request=request, current_user=free_user, _db=FAKE_DB
    )
    await agen.__anext__()
    await agen.aclose()

    with pytest.raises(RateLimitException):
        agen = deps.require_billing_limits(
            request=request,
            current_user=free_user,
            _db=FAKE_DB,
        )
        await agen.__anext__()

    for i in range(3):
        agen = deps.require_billing_limits(
            request=request,
            current_user=tier1_user,
            _db=FAKE_DB,
        )
        yielded_user = await agen.__anext__()
        assert yielded_user == tier1_user
        await agen.aclose()


@pytest.mark.asyncio
async def test_require_billing_limits_raises_unavailable_when_redis_unreachable(
    monkeypatch,
):
    """When the rate limiter cannot reach Redis, billing RPM (L1) must fail-close with 503."""

    class _BrokenRateLimiter:
        def __init__(self, _config) -> None:
            pass

        async def check_billing_rpm(self, _user_id: str, _rpm: int) -> None:
            raise RuntimeError("redis down")

    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = FakeRedisService(redis)

    monkeypatch.setattr(
        deps.redis_pool_manager,
        "get_redis_service",
        lambda: redis_service,
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=2)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _BrokenRateLimiter)

    request = make_request()
    user = CurrentUser(user_id="u_down", user_tier="free")

    with pytest.raises(UnavailableException) as exc_info:
        agen = deps.require_billing_limits(
            request=request, current_user=user, _db=FAKE_DB
        )
        await agen.__anext__()

    assert "Redis error in billing RPM check" in exc_info.value.internal_message


@pytest.mark.asyncio
async def test_require_billing_limits_raises_unavailable_when_tier_config_missing(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = FakeRedisService(redis)

    class _ConfigMissingTier:
        def __init__(self) -> None:
            self.is_bypassed = False
            self.tier_map = {
                "free": TierLimits(
                    rpm_limit=60,
                    max_concurrent_jobs=2,
                    daily_quota=10,
                )
            }

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _ConfigMissingTier()),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    request = make_request()
    user = CurrentUser(user_id="u_missing_tier", user_tier="tier_9")

    with pytest.raises(UnavailableException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=user,
            _db=FAKE_DB,
        )
        await agen.__anext__()

    assert "Missing tier config for tier=tier_9" in exc_info.value.internal_message


@pytest.mark.asyncio
async def test_enforce_job_creation_capacity_allows_when_active_jobs_below_limit(
    monkeypatch,
):
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=1)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)
    monkeypatch.setattr(
        deps, "_acquire_user_concurrency_lock", async_none
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(0)
    )

    request = make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=1,
        daily_quota=10,
    )
    user = CurrentUser(user_id="u_ok", user_tier="free")

    await deps.enforce_job_creation_capacity(request, FAKE_DB, user)

@pytest.mark.asyncio
async def test_enforce_job_creation_capacity_raises_when_concurrency_full(monkeypatch):
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=1)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)
    monkeypatch.setattr(
        deps, "_acquire_user_concurrency_lock", async_none
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(1)
    )

    request = make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=2,
        max_concurrent_jobs=1,
        daily_quota=10,
    )
    user = CurrentUser(user_id="u_full", user_tier="free")

    with pytest.raises(RateLimitException) as exc_info:
        await deps.enforce_job_creation_capacity(request, FAKE_DB, user)
    exc = exc_info.value
    assert exc.retry_after == 30
    assert exc.details.get("period") == "concurrent"
    assert exc.details.get("limit") == 1
    assert exc.details.get("active_jobs") == 1
    assert exc.details.get("available_slots") == 0


@pytest.mark.asyncio
async def test_enforce_job_creation_capacity_raises_unavailable_when_db_lock_fails(
    monkeypatch,
):
    async def _broken_lock(*_args, **_kwargs):
        raise RuntimeError("db lock failed")

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=2)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)
    monkeypatch.setattr(deps, "_acquire_user_concurrency_lock", _broken_lock)

    request = make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=2,
        daily_quota=10,
    )
    user = CurrentUser(user_id="u_db_err", user_tier="free")

    with pytest.raises(UnavailableException) as exc_info:
        await deps.enforce_job_creation_capacity(request, FAKE_DB, user)
    assert "DB error in concurrency check" in exc_info.value.internal_message


@pytest.mark.asyncio
async def test_enforce_job_creation_capacity_raises_unavailable_when_daily_quota_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=2, daily_quota=20)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _DailyQuotaErrorRateLimiter)
    monkeypatch.setattr(
        deps, "_acquire_user_concurrency_lock", async_none
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", async_value(0)
    )

    request = make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=2,
        daily_quota=20,
    )
    user = CurrentUser(user_id="u_daily_err", user_tier="free")

    with pytest.raises(UnavailableException) as exc_info:
        await deps.enforce_job_creation_capacity(request, FAKE_DB, user)
    assert "Redis error in daily quota check" in exc_info.value.internal_message
