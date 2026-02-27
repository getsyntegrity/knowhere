import json
from types import SimpleNamespace

import pytest

from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits
from app.services.rate_limit.rule_loader import (
    ACTIVE_RULES_KEY,
    RATE_LIMIT_UPDATES_CHANNEL,
    _fetch_system_rules,
    _fetch_tier_map,
    _publish_snapshot_to_redis,
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


class _RawClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str):
        self.published.append((channel, message))


class _RedisService:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, dict, int]] = []
        self.raw_client = _RawClient()
        self.current_snapshot = None

    async def set(self, key: str, value: dict, ttl: int):
        self.current_snapshot = value
        self.set_calls.append((key, value, ttl))

    async def get(self, _key: str):
        return self.current_snapshot

    async def _get_client(self):
        return self.raw_client


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
        SystemRpmRule(method="POST", api_pattern="/v1/jobs", priority=100, rpm=30),
        SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000),
    ]


@pytest.mark.asyncio
async def test_publish_snapshot_to_redis_sets_snapshot_and_publishes():
    redis_service = _RedisService()
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000)]

    published = await _publish_snapshot_to_redis(redis_service, tier_map, rules)

    assert published is True
    assert len(redis_service.set_calls) == 1
    key, value, ttl = redis_service.set_calls[0]
    assert key == ACTIVE_RULES_KEY
    assert ttl == 86400
    assert value["tier_map"]["free"]["rpm_limit"] == 2
    assert value["system_rules"][0]["api_pattern"] == "*"
    assert redis_service.raw_client.published == [
        (RATE_LIMIT_UPDATES_CHANNEL, '{"event":"rules_updated"}')
    ]


@pytest.mark.asyncio
async def test_publish_snapshot_to_redis_skips_when_unchanged():
    redis_service = _RedisService()
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000)]

    first = await _publish_snapshot_to_redis(redis_service, tier_map, rules)
    second = await _publish_snapshot_to_redis(redis_service, tier_map, rules)

    assert first is True
    assert second is False
    assert len(redis_service.set_calls) == 1
    assert len(redis_service.raw_client.published) == 1


@pytest.mark.asyncio
async def test_publish_snapshot_to_redis_skips_when_existing_snapshot_is_json_string():
    redis_service = _RedisService()
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000)]
    snapshot = {
        "tier_map": {"free": {"rpm_limit": 2, "max_concurrent_jobs": 2, "daily_quota": 20}},
        "system_rules": [{"method": "*", "api_pattern": "*", "priority": 9999, "rpm": 1000}],
    }
    redis_service.current_snapshot = json.dumps(snapshot)

    published = await _publish_snapshot_to_redis(redis_service, tier_map, rules)

    assert published is False
    assert redis_service.set_calls == []
    assert redis_service.raw_client.published == []


@pytest.mark.asyncio
async def test_publish_snapshot_to_redis_publishes_when_existing_snapshot_is_malformed():
    redis_service = _RedisService()
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000)]
    redis_service.current_snapshot = "{not-json"

    published = await _publish_snapshot_to_redis(redis_service, tier_map, rules)

    assert published is True
    assert len(redis_service.set_calls) == 1
    assert len(redis_service.raw_client.published) == 1


@pytest.mark.asyncio
async def test_load_rules_updates_config_and_publishes(monkeypatch):
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000)]
    redis_service = _RedisService()
    update_calls: list[tuple[dict, list]] = []
    publish_calls: list[tuple[dict, list]] = []

    class _Config:
        def update_rules(self, call_tier_map, call_rules):
            update_calls.append((call_tier_map, call_rules))

    async def _fake_fetch_tier_map(_db):
        return tier_map

    async def _fake_fetch_system_rules(_db):
        return rules

    async def _fake_publish(_redis, call_tier_map, call_rules):
        publish_calls.append((call_tier_map, call_rules))
        return True

    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_tier_map",
        _fake_fetch_tier_map,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_system_rules",
        _fake_fetch_system_rules,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._publish_snapshot_to_redis",
        _fake_publish,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader.RateLimitConfig.get_instance",
        classmethod(lambda _cls: _Config()),
    )

    published = await load_rules(db=object(), redis_service=redis_service)

    assert published is True
    assert update_calls == [(tier_map, rules)]
    assert publish_calls == [(tier_map, rules)]


@pytest.mark.asyncio
async def test_load_rules_skips_publish_when_disabled(monkeypatch):
    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    rules = [SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000)]
    update_calls: list[tuple[dict, list]] = []
    publish_calls: list[tuple[dict, list]] = []

    class _Config:
        def update_rules(self, call_tier_map, call_rules):
            update_calls.append((call_tier_map, call_rules))

    async def _fake_fetch_tier_map(_db):
        return tier_map

    async def _fake_fetch_system_rules(_db):
        return rules

    async def _fake_publish(_redis, call_tier_map, call_rules):
        publish_calls.append((call_tier_map, call_rules))
        return True

    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_tier_map",
        _fake_fetch_tier_map,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_system_rules",
        _fake_fetch_system_rules,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._publish_snapshot_to_redis",
        _fake_publish,
    )
    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader.RateLimitConfig.get_instance",
        classmethod(lambda _cls: _Config()),
    )

    published = await load_rules(
        db=object(),
        redis_service=_RedisService(),
        publish_updates=False,
    )

    assert published is False
    assert update_calls == [(tier_map, rules)]
    assert publish_calls == []


@pytest.mark.asyncio
async def test_load_rules_raises_when_fetch_fails(monkeypatch):
    async def _boom(_db):
        raise RuntimeError("fetch failed")

    monkeypatch.setattr(
        "app.services.rate_limit.rule_loader._fetch_tier_map",
        _boom,
    )

    with pytest.raises(RuntimeError, match="fetch failed"):
        await load_rules(db=object(), redis_service=_RedisService())
