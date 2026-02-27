import time
from types import SimpleNamespace

import pytest

from app.services.rate_limit.limiter import RateLimiter
from shared.core.exceptions.domain_exceptions import RateLimitException


class _Window:
    def __init__(
        self,
        *,
        hit_allowed: bool = True,
        remaining: int = 0,
        reset_time: int | None = None,
        stats_error: bool = False,
    ) -> None:
        self.hit_allowed = hit_allowed
        self.remaining = remaining
        self.reset_time = (
            int(time.time()) + 30 if reset_time is None else reset_time
        )
        self.stats_error = stats_error
        self.hit_calls: list[tuple] = []
        self.stats_calls: list[tuple] = []

    async def hit(self, rate_item, namespace, identifier):
        self.hit_calls.append((rate_item, namespace, identifier))
        return self.hit_allowed

    async def get_window_stats(self, rate_item, namespace, identifier):
        self.stats_calls.append((rate_item, namespace, identifier))
        if self.stats_error:
            raise RuntimeError("stats unavailable")
        return SimpleNamespace(
            reset_time=self.reset_time,
            remaining=self.remaining,
        )


def _config(
    *,
    is_bypassed: bool = False,
    sliding: _Window | None = None,
    fixed: _Window | None = None,
):
    return SimpleNamespace(
        is_bypassed=is_bypassed,
        parse_rate=lambda rate: f"parsed:{rate}",
        sliding_window=sliding or _Window(),
        fixed_window=fixed or _Window(),
        namespaced_namespace=lambda ns: f"knowhere-api:rate_limit:{ns}",
    )


@pytest.mark.asyncio
async def test_check_system_rpm_skips_when_bypassed():
    sliding = _Window(hit_allowed=False)
    limiter = RateLimiter(_config(is_bypassed=True, sliding=sliding))
    await limiter.check_system_rpm("u1", 10, "/v1/jobs")
    assert sliding.hit_calls == []


@pytest.mark.asyncio
async def test_check_system_rpm_skips_when_unlimited():
    sliding = _Window(hit_allowed=False)
    limiter = RateLimiter(_config(sliding=sliding))
    await limiter.check_system_rpm("u1", -1, "/v1/jobs")
    assert sliding.hit_calls == []


@pytest.mark.asyncio
async def test_check_system_rpm_raises_with_window_details():
    sliding = _Window(hit_allowed=False, remaining=0, reset_time=int(time.time()) + 20)
    limiter = RateLimiter(_config(sliding=sliding))

    with pytest.raises(RateLimitException) as exc_info:
        await limiter.check_system_rpm("u_sys", 12, "/v1/jobs")

    exc = exc_info.value
    assert exc.limit == 12
    assert exc.period == "minute"
    assert exc.details["remaining"] == 0
    assert isinstance(exc.details["reset"], int)
    assert exc.details["reset"] >= int(time.time())


@pytest.mark.asyncio
async def test_check_billing_rpm_uses_default_retry_after_when_stats_fail():
    sliding = _Window(hit_allowed=False, stats_error=True)
    limiter = RateLimiter(_config(sliding=sliding))

    with pytest.raises(RateLimitException) as exc_info:
        await limiter.check_billing_rpm("u_billing", 5)

    exc = exc_info.value
    assert exc.limit == 5
    assert exc.retry_after == RateLimitException.DEFAULT_RETRY_AFTER


@pytest.mark.asyncio
async def test_check_daily_quota_uses_fixed_window_and_raises_day_period():
    fixed = _Window(hit_allowed=False, remaining=0, reset_time=int(time.time()) + 40)
    limiter = RateLimiter(_config(fixed=fixed))

    with pytest.raises(RateLimitException) as exc_info:
        await limiter.check_daily_quota("u_daily", 20)

    exc = exc_info.value
    assert exc.limit == 20
    assert exc.period == "day"
    assert fixed.hit_calls[0][1] == "knowhere-api:rate_limit:daily_quota"
