from types import SimpleNamespace

import pytest

from app.services.rate_limit import dependencies as deps
from app.services.rate_limit.data_structures import SystemRpmRule
from shared.core.exceptions.domain_exceptions import RateLimitException

from .helpers import make_request


class _Window:
    def __init__(
        self,
        *,
        hit_allowed: bool = True,
        reset_time: int = 1_800_000_000,
        remaining: int = 0,
    ) -> None:
        self.hit_allowed = hit_allowed
        self.reset_time = reset_time
        self.remaining = remaining
        self.hit_calls: list[tuple[object, str, str]] = []
        self.stats_calls: list[tuple[object, str, str]] = []

    async def hit(self, rate_item, namespace: str, identifier: str) -> bool:
        self.hit_calls.append((rate_item, namespace, identifier))
        return self.hit_allowed

    async def get_window_stats(
        self,
        rate_item,
        namespace: str,
        identifier: str,
    ) -> SimpleNamespace:
        self.stats_calls.append((rate_item, namespace, identifier))
        return SimpleNamespace(reset_time=self.reset_time, remaining=self.remaining)


class _Config:
    def __init__(self, *, rule: SystemRpmRule, fixed_window: _Window, sliding_window: _Window) -> None:
        self.is_bypassed = False
        self.system_rules = [rule]
        self.fixed_window = fixed_window
        self.sliding_window = sliding_window

    @staticmethod
    def parse_rate(rate: str) -> str:
        return f"parsed:{rate}"

    @staticmethod
    def namespaced_namespace(namespace: str) -> str:
        return f"knowhere-api:rate_limit:{namespace}"


@pytest.mark.asyncio
async def test_require_ip_rate_limit_uses_fixed_window_for_daily_rule(monkeypatch) -> None:
    fixed_window = _Window()
    sliding_window = _Window()
    config = _Config(
        rule=SystemRpmRule(
            method="POST",
            api_pattern="/v1/guest",
            priority=100,
            rpm=100,
            period="day",
        ),
        fixed_window=fixed_window,
        sliding_window=sliding_window,
    )
    request = make_request()
    request.scope["path"] = "/v1/guest"

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )

    await deps.require_ip_rate_limit(request)

    assert fixed_window.hit_calls == [
        (
            "parsed:100/day",
            "knowhere-api:rate_limit:ip_rate_limit:day",
            "127.0.0.1:/v1/guest",
        )
    ]
    assert sliding_window.hit_calls == []


@pytest.mark.asyncio
async def test_require_ip_rate_limit_raises_day_period_when_daily_limit_exceeded(
    monkeypatch,
) -> None:
    fixed_window = _Window(hit_allowed=False, reset_time=1_800_000_123, remaining=0)
    config = _Config(
        rule=SystemRpmRule(
            method="POST",
            api_pattern="/v1/guest",
            priority=100,
            rpm=100,
            period="day",
        ),
        fixed_window=fixed_window,
        sliding_window=_Window(),
    )
    request = make_request()
    request.scope["path"] = "/v1/guest"

    monkeypatch.setattr(
        deps.RateLimitConfig,
        "get_instance",
        classmethod(lambda _cls: config),
    )

    with pytest.raises(RateLimitException) as exc_info:
        await deps.require_ip_rate_limit(request)

    exc = exc_info.value
    assert exc.limit == 100
    assert exc.period == "day"
