"""Tests for AliQuotaManager — token pool for Aliyun DashScope API keys."""

from typing import cast

import pytest

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import UnavailableException
from shared.services.redis.redis_sync_service import SyncRedisService
from shared.utils.ali_quota_manager import AliQuotaManager
from shared.utils.quota_manager import TokenConfig

fakeredis = pytest.importorskip("fakeredis")


class FakeSyncRedisService:
    def __init__(self, client):
        self.client = client

    def get(self, key, default=None):
        value = self.client.get(key)
        return default if value is None else value

    def set(self, key, value, ttl=None, ex=None):
        expire = ex or ttl
        return bool(self.client.set(key, value, ex=expire))

    def eval(self, script, keys, args=None):
        return self.client.eval(script, len(keys), *(list(keys) + list(args or [])))


def build_ali_manager(*, tokens=None):
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    manager = AliQuotaManager(
        cast(SyncRedisService, FakeSyncRedisService(redis_client)),
        tokens
        or [
            TokenConfig("ali-1", "test-ali-key-1", rpm_limit=300, daily_limit=10000),
            TokenConfig("ali-2", "test-ali-key-2", rpm_limit=300, daily_limit=10000),
        ],
    )
    return manager, redis_client


def test_acquire_request_returns_token():
    manager, _ = build_ali_manager()
    lease = manager.acquire_request(operation="chat_completion")
    assert lease.api_key in {"test-ali-key-1", "test-ali-key-2"}
    assert lease.token_id in {"ali-1", "ali-2"}


def test_round_robin_rotates_tokens():
    manager, _ = build_ali_manager()
    first = manager.acquire_request(operation="chat_completion")
    second = manager.acquire_request(operation="chat_completion")
    # Should get different tokens on consecutive calls (round-robin cursor advances)
    assert first.token_id != second.token_id


def test_cooldown_skips_rate_limited_token():
    manager, _ = build_ali_manager()
    manager.mark_rate_limited("ali-1", retry_after=30)
    # Next acquire should skip ali-1
    lease = manager.acquire_request(operation="chat_completion")
    assert lease.token_id == "ali-2"


def test_exhaustion_raises_unavailable():
    manager, redis_client = build_ali_manager(
        tokens=[
            TokenConfig("ali-1", "test-ali-key-1", rpm_limit=1, daily_limit=10000),
        ]
    )
    manager.acquire_request(operation="test")
    with pytest.raises(UnavailableException) as exc_info:
        manager.acquire_request(operation="test")
    assert exc_info.value.period == "minute"
    assert (
        exc_info.value.user_message
        == "AI service is busy right now. Please retry shortly."
    )


def test_redis_keys_use_ali_prefix():
    manager, _ = build_ali_manager()
    fixed_now = 1_700_000_000
    minute_key = manager._minute_key("ali-1", fixed_now)
    day_key = manager._day_key("ali-1", fixed_now)
    cooldown_key = manager._cooldown_key("ali-1")
    assert minute_key.startswith("ali:quota:")
    assert day_key.startswith("ali:quota:")
    assert cooldown_key.startswith("ali:quota:")


def test_parse_token_specs_comma_separated():
    specs = AliQuotaManager.parse_token_specs(
        "test-ali-key-abc,test-ali-key-def,test-ali-key-ghi",
        default_rpm_limit=300,
        default_daily_limit=10000,
    )
    assert len(specs) == 3
    assert specs[0].api_key == "test-ali-key-abc"
    assert specs[1].api_key == "test-ali-key-def"
    assert specs[2].api_key == "test-ali-key-ghi"


def test_parse_token_specs_json_array():
    specs = AliQuotaManager.parse_token_specs(
        '[{"key":"test-ali-key-json-1","rpm_limit":200},{"key":"test-ali-key-json-2"}]',
        default_rpm_limit=300,
        default_daily_limit=10000,
    )
    assert len(specs) == 2
    assert specs[0].rpm_limit == 200
    assert specs[1].rpm_limit == 300


def test_parse_tokens_from_settings_uses_ali_api_keys(monkeypatch):
    monkeypatch.setattr(
        settings,
        "ALI_API_KEYS",
        "ali-1=test-ali-key-abc,dummy-ali-key-for-tests",
        raising=False,
    )
    monkeypatch.setattr(settings, "ALI_TOKEN_RPM_LIMIT", 300, raising=False)
    monkeypatch.setattr(settings, "ALI_TOKEN_DAILY_LIMIT", 10000, raising=False)

    specs = AliQuotaManager.parse_tokens_from_settings()

    assert [spec.api_key for spec in specs] == [
        "test-ali-key-abc",
        "test-ali-key-def",
    ]


def test_parse_tokens_from_settings_requires_ali_api_keys(monkeypatch):
    monkeypatch.setattr(settings, "ALI_API_KEYS", "", raising=False)
    monkeypatch.setattr(settings, "ALI_TOKEN_RPM_LIMIT", 300, raising=False)
    monkeypatch.setattr(settings, "ALI_TOKEN_DAILY_LIMIT", 10000, raising=False)

    with pytest.raises(ValueError, match="ALI_API_KEYS"):
        AliQuotaManager.parse_tokens_from_settings()
