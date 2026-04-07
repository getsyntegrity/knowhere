from types import SimpleNamespace

import pytest

from app.services.rate_limit.data_structures import SystemLimitRule, TierLimits
from app.services.rate_limit.rule_loader import (
    _fetch_system_rules,
    _fetch_tier_map,
    load_rules,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_fetch_tier_map_builds_expected_mapping():
    db = _FakeDB(
        rows=[
            SimpleNamespace(
                tier_name="free",
                rpm_limit=2,
                max_concurrent_jobs=2,
                daily_quota=20,
            ),
            SimpleNamespace(
                tier_name="tier_1",
                rpm_limit=15,
                max_concurrent_jobs=5,
                daily_quota=-1,
            ),
        ]
    )
    tier_map = await _fetch_tier_map(db)
    assert tier_map == {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20),
        "tier_1": TierLimits(rpm_limit=15, max_concurrent_jobs=5, daily_quota=-1),
    }


@pytest.mark.asyncio
async def test_fetch_system_rules_builds_rule_list():
    db = _FakeDB(
        rows=[
            SimpleNamespace(method="POST", api_pattern="/v1/jobs", priority=100, rpm=30),
            SimpleNamespace(method="*", api_pattern="*", priority=9999, rpm=1000),
        ]
    )
    rules = await _fetch_system_rules(db)
    assert rules == [
        SystemLimitRule(method="POST", api_pattern="/v1/jobs", priority=100, limit=30),
        SystemLimitRule(method="*", api_pattern="*", priority=9999, limit=1000),
    ]


@pytest.mark.asyncio
async def test_load_rules_updates_config(monkeypatch):
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemLimitRule(method="*", api_pattern="*", priority=9999, limit=1000)]
    update_calls: list[tuple[dict, list]] = []

    class _Config:
        def update_rules(self, call_tier_map, call_rules):
            update_calls.append((call_tier_map, call_rules))

    async def _fake_fetch_tier_map(_db):
        return tier_map

    async def _fake_fetch_system_rules(_db):
        return rules

    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_tier_map",
        _fake_fetch_tier_map,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_system_rules",
        _fake_fetch_system_rules,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader.RateLimitConfig.get_instance",
        classmethod(lambda _cls: _Config()),
    )

    await load_rules(db=object())
    assert update_calls == [(tier_map, rules)]


@pytest.mark.asyncio
async def test_load_rules_raises_when_fetch_fails(monkeypatch):
    async def _boom(_db):
        raise RuntimeError("fetch failed")

    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_tier_map",
        _boom,
    )

    with pytest.raises(RuntimeError, match="fetch failed"):
        await load_rules(db=object())
