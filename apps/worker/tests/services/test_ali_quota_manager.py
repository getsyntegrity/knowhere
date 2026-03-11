"""Tests for AliQuotaManager — token pool for Aliyun DashScope API keys."""
from typing import cast

import pytest

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
            TokenConfig("ali-1", "sk-ali-1", rpm_limit=300, daily_limit=10000),
            TokenConfig("ali-2", "sk-ali-2", rpm_limit=300, daily_limit=10000),
        ],
    )
    return manager, redis_client


def test_acquire_request_returns_token():
    manager, _ = build_ali_manager()
    lease = manager.acquire_request(operation="chat_completion")
    assert lease.api_key in {"sk-ali-1", "sk-ali-2"}
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
            TokenConfig("ali-1", "sk-ali-1", rpm_limit=1, daily_limit=10000),
        ]
    )
    manager.acquire_request(operation="test")
    with pytest.raises(UnavailableException) as exc_info:
        manager.acquire_request(operation="test")
    assert exc_info.value.period == "minute"
    assert exc_info.value.user_message == "AI service is busy right now. Please retry shortly."


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
        "sk-abc,sk-def,sk-ghi",
        default_rpm_limit=300,
        default_daily_limit=10000,
    )
    assert len(specs) == 3
    assert specs[0].api_key == "sk-abc"
    assert specs[1].api_key == "sk-def"
    assert specs[2].api_key == "sk-ghi"


def test_parse_token_specs_json_array():
    specs = AliQuotaManager.parse_token_specs(
        '[{"key":"sk-1","rpm_limit":200},{"key":"sk-2"}]',
        default_rpm_limit=300,
        default_daily_limit=10000,
    )
    assert len(specs) == 2
    assert specs[0].rpm_limit == 200
    assert specs[1].rpm_limit == 300
