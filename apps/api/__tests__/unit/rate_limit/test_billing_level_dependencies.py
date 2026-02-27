from types import SimpleNamespace

import pytest
from fastapi import Request

fakeredis = pytest.importorskip("fakeredis.aioredis")

from app.services.rate_limit import dependencies as deps
from app.services.rate_limit.data_structures import CurrentUser, TierLimits
from app.services.rate_limit.limiter import RateLimiter as _RealRateLimiter
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
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


def _make_limits_config_with_fakeredis(
    monkeypatch, tier_map: dict[str, TierLimits]
):
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
                lambda _cls, *args, **kwargs: _fake_from_url(*args, **kwargs)
            ),
            raising=False,
        )

    storage = limits_storage.RedisStorage(
        "async+redis://unused:6379/0",
        implementation="redispy",
    )
    config = SimpleNamespace(
        is_bypassed=False,
        tier_map=tier_map,
        parse_rate=limits.parse,
        sliding_window=limits_strategies.MovingWindowRateLimiter(storage),
        fixed_window=limits_strategies.FixedWindowRateLimiter(storage),
        namespaced_namespace=lambda ns: f"knowhere-api:rate_limit:{ns}",
    )
    redis_client = fakeredis.FakeRedis(
        server=fake_server, decode_responses=True
    )
    return config, redis_client


class _FakeRedisService:
    def __init__(self, client) -> None:
        self._client = client

    async def _get_client(self):
        return self._client


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


@pytest.mark.asyncio
async def test_require_billing_limits_sets_job_state_and_tier_limits(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=2)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    request = _make_request()
    user = CurrentUser(user_id="u_ok", user_tier="free")
    job_id = "job_ok"

    agen = deps.require_billing_limits(
        request=request, current_user=user, job_id=job_id, _db=object()
    )
    yielded_user = await agen.__anext__()
    assert yielded_user == user
    assert request.state.job_id == job_id
    assert request.state.rate_limit_tier_limits == TierLimits(
        rpm_limit=60, max_concurrent_jobs=2, daily_quota=10
    )
    await agen.aclose()


@pytest.mark.asyncio
async def test_require_billing_limits_enforces_tier_rpm_with_real_rate_limiter(
    monkeypatch,
):
    config, redis_client = _make_limits_config_with_fakeredis(
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
    redis_service = _FakeRedisService(redis_client)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _RealRateLimiter)

    request = _make_request()
    user = CurrentUser(user_id="u_tier_2", user_tier="tier_2")

    agen = deps.require_billing_limits(
        request=request, current_user=user, job_id="job_tier_2", _db=object()
    )
    yielded_user = await agen.__anext__()
    assert yielded_user == user
    await agen.aclose()

    with pytest.raises(RateLimitException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=user,
            job_id="job_tier_2_2",
            _db=object(),
        )
        await agen.__anext__()
    assert exc_info.value.limit == 1


@pytest.mark.asyncio
async def test_require_billing_limits_applies_different_tier_rpm_limits(monkeypatch):
    config, redis_client = _make_limits_config_with_fakeredis(
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
    redis_service = _FakeRedisService(redis_client)

    monkeypatch.setattr(
        deps.redis_pool_manager, "get_redis_service", lambda: redis_service
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _RealRateLimiter)

    request = _make_request()
    free_user = CurrentUser(user_id="u_free", user_tier="free")
    tier1_user = CurrentUser(user_id="u_tier_1", user_tier="tier_1")

    agen = deps.require_billing_limits(
        request=request, current_user=free_user, job_id="job_free_1", _db=object()
    )
    await agen.__anext__()
    await agen.aclose()

    with pytest.raises(RateLimitException):
        agen = deps.require_billing_limits(
            request=request,
            current_user=free_user,
            job_id="job_free_2",
            _db=object(),
        )
        await agen.__anext__()

    for i in range(3):
        agen = deps.require_billing_limits(
            request=request,
            current_user=tier1_user,
            job_id=f"job_tier1_{i}",
            _db=object(),
        )
        yielded_user = await agen.__anext__()
        assert yielded_user == tier1_user
        await agen.aclose()


@pytest.mark.asyncio
async def test_require_billing_limits_raises_unavailable_when_redis_unreachable(
    monkeypatch,
):
    class _BrokenRedisService:
        async def _get_client(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(
        deps.redis_pool_manager,
        "get_redis_service",
        lambda: _BrokenRedisService(),
    )
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=2)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    request = _make_request()
    user = CurrentUser(user_id="u_down", user_tier="free")

    with pytest.raises(UnavailableException) as exc_info:
        agen = deps.require_billing_limits(
            request=request, current_user=user, job_id="job_down", _db=object()
        )
        await agen.__anext__()

    assert "Redis error acquiring client" in exc_info.value.internal_message


@pytest.mark.asyncio
async def test_require_billing_limits_raises_unavailable_when_tier_config_missing(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis_service = _FakeRedisService(redis)

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

    request = _make_request()
    user = CurrentUser(user_id="u_missing_tier", user_tier="tier_9")

    with pytest.raises(UnavailableException) as exc_info:
        agen = deps.require_billing_limits(
            request=request,
            current_user=user,
            job_id="job_missing_tier",
            _db=object(),
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
        deps, "_acquire_user_concurrency_lock", lambda *_args, **_kwargs: _async_none()
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", lambda *_args, **_kwargs: _async_value(0)
    )

    request = _make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=1,
        daily_quota=10,
    )
    user = CurrentUser(user_id="u_ok", user_tier="free")

    await deps.enforce_job_creation_capacity(request, object(), user)


@pytest.mark.asyncio
async def test_enforce_job_creation_capacity_raises_when_concurrency_full(monkeypatch):
    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: _FakeConfig(max_concurrent_jobs=1)),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)
    monkeypatch.setattr(
        deps, "_acquire_user_concurrency_lock", lambda *_args, **_kwargs: _async_none()
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", lambda *_args, **_kwargs: _async_value(1)
    )

    request = _make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=1,
        daily_quota=10,
    )
    user = CurrentUser(user_id="u_full", user_tier="free")

    with pytest.raises(RateLimitException) as exc_info:
        await deps.enforce_job_creation_capacity(request, object(), user)

    exc = exc_info.value
    assert exc.details.get("period") == "concurrent"
    assert exc.details.get("limit") == 1


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

    request = _make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=2,
        daily_quota=10,
    )
    user = CurrentUser(user_id="u_db_err", user_tier="free")

    with pytest.raises(UnavailableException) as exc_info:
        await deps.enforce_job_creation_capacity(request, object(), user)

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
        deps, "_acquire_user_concurrency_lock", lambda *_args, **_kwargs: _async_none()
    )
    monkeypatch.setattr(
        deps, "_count_non_terminal_jobs", lambda *_args, **_kwargs: _async_value(0)
    )

    request = _make_request()
    request.state.rate_limit_tier_limits = TierLimits(
        rpm_limit=60,
        max_concurrent_jobs=2,
        daily_quota=20,
    )
    user = CurrentUser(user_id="u_daily_err", user_tier="free")

    with pytest.raises(UnavailableException) as exc_info:
        await deps.enforce_job_creation_capacity(request, object(), user)

    assert "Redis error in daily quota check" in exc_info.value.internal_message


async def _async_none():
    return None


async def _async_value(value):
    return value
