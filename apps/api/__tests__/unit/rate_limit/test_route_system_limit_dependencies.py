from types import SimpleNamespace

import pytest

from app.services.rate_limit import dependencies as deps
from app.services.rate_limit.data_structures import SystemLimitRule
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)

from .helpers import make_request


class _Config:
    def __init__(self, system_rules: list[SystemLimitRule]) -> None:
        self.is_bypassed = False
        self.system_rules = system_rules


class _PassRateLimiter:
    calls: list[tuple[str, int, str, str, bool]] = []

    def __init__(self, _config) -> None:
        pass

    async def check_system_limit(
        self,
        identifier: str,
        limit: int,
        matched_pattern: str,
        *,
        period: str = "minute",
        use_global_key: bool = False,
    ) -> None:
        self.calls.append((identifier, limit, matched_pattern, period, use_global_key))


class _CrashRateLimiter:
    def __init__(self, _config) -> None:
        pass

    async def check_system_limit(
        self,
        identifier: str,
        limit: int,
        matched_pattern: str,
        *,
        period: str = "minute",
        use_global_key: bool = False,
    ) -> None:
        raise RuntimeError("redis transient error")


@pytest.mark.asyncio
async def test_require_route_system_limit_uses_route_identifier_with_explicit_rule(
    monkeypatch,
) -> None:
    _PassRateLimiter.calls.clear()
    config = _Config(
        [
            SystemLimitRule(
                method="POST",
                api_pattern="/v1/guest",
                priority=100,
                limit=100,
                period="day",
            )
        ]
    )
    request = make_request()
    request.scope["path"] = "/v1/guest"

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    await deps.require_route_system_limit(request)

    assert _PassRateLimiter.calls == [("/v1/guest", 100, "/v1/guest", "day", True)]


@pytest.mark.asyncio
async def test_require_route_system_limit_uses_route_template_for_dynamic_paths(
    monkeypatch,
) -> None:
    _PassRateLimiter.calls.clear()
    config = _Config(
        [
            SystemLimitRule(
                method="POST",
                api_pattern="/v1/jobs/*",
                priority=100,
                limit=30,
            )
        ]
    )
    request = make_request()
    request.scope["path"] = "/v1/jobs/job-123"
    request.scope["route"] = SimpleNamespace(path="/v1/jobs/{job_id}")

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    await deps.require_route_system_limit(request)

    assert _PassRateLimiter.calls == [
        ("/v1/jobs/{job_id}", 30, "/v1/jobs/*", "minute", True)
    ]


@pytest.mark.asyncio
async def test_require_route_system_limit_uses_default_rule_when_no_specific_match(
    monkeypatch,
) -> None:
    _PassRateLimiter.calls.clear()
    config = _Config(
        [
            SystemLimitRule(
                method="*",
                api_pattern="*",
                priority=9999,
                limit=1000,
            )
        ]
    )
    request = make_request()
    request.scope["path"] = "/v1/guest"

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _PassRateLimiter)

    await deps.require_route_system_limit(request)
    assert _PassRateLimiter.calls == [("/v1/guest", 1000, "*", "minute", True)]


@pytest.mark.asyncio
async def test_require_route_system_limit_fails_closed_on_redis_error(
    monkeypatch,
) -> None:
    config = _Config(
        [
            SystemLimitRule(
                method="POST",
                api_pattern="/v1/guest",
                priority=100,
                limit=100,
                period="day",
            )
        ]
    )
    request = make_request()
    request.scope["path"] = "/v1/guest"

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _CrashRateLimiter)

    with pytest.raises(UnavailableException) as exc_info:
        await deps.require_route_system_limit(request)

    exc = exc_info.value
    assert exc.retry_after == 15
    assert exc.limit == 100
    assert exc.period == "day"


@pytest.mark.asyncio
async def test_require_route_system_limit_reraises_rate_limit_exception(
    monkeypatch,
) -> None:
    class _Raise429RateLimiter:
        def __init__(self, _config) -> None:
            pass

        async def check_system_limit(
            self,
            identifier: str,
            limit: int,
            matched_pattern: str,
            *,
            period: str = "minute",
            use_global_key: bool = False,
        ) -> None:
            raise RateLimitException(retry_after=33, limit=limit, period=period)

    config = _Config(
        [
            SystemLimitRule(
                method="POST",
                api_pattern="/v1/guest",
                priority=100,
                limit=100,
                period="day",
            )
        ]
    )
    request = make_request()
    request.scope["path"] = "/v1/guest"

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )
    monkeypatch.setattr(deps, "RateLimiter", _Raise429RateLimiter)

    with pytest.raises(RateLimitException) as exc_info:
        await deps.require_route_system_limit(request)

    assert exc_info.value.retry_after == 33
