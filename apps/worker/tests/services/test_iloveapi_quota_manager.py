"""Tests for ILoveApiQuotaManager — token pool for iLoveAPI keys."""
from typing import cast

import pytest

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import UnavailableException
from shared.services.redis.redis_sync_service import SyncRedisService
from shared.utils.iloveapi_quota_manager import ILoveApiQuotaManager
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


class FailingSyncRedisService:
    def eval(self, script, keys, args=None):
        raise RuntimeError("redis unavailable")


DEFAULT_TOKENS = [
    TokenConfig("iloveapi-1", "pub1:sec1", rpm_limit=25, daily_limit=250),
    TokenConfig("iloveapi-2", "pub2:sec2", rpm_limit=25, daily_limit=250),
]


def build_iloveapi_manager(*, tokens=None, max_concurrent=5):
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    manager = ILoveApiQuotaManager(
        cast(SyncRedisService, FakeSyncRedisService(redis_client)),
        tokens or DEFAULT_TOKENS,
        max_concurrent=max_concurrent,
    )
    return manager, redis_client


# ------------------------------------------------------------------
# Token pool tests (BaseQuotaManager behavior for iLoveAPI)
# ------------------------------------------------------------------

def test_acquire_request_returns_lease():
    manager, _ = build_iloveapi_manager()
    lease = manager.acquire_request(operation="pptx_to_pdf")
    assert lease.api_key in {"pub1:sec1", "pub2:sec2"}
    assert lease.token_id in {"iloveapi-1", "iloveapi-2"}


def test_round_robin_rotates_tokens():
    manager, _ = build_iloveapi_manager()
    first = manager.acquire_request(operation="pptx_to_pdf")
    second = manager.acquire_request(operation="pptx_to_pdf")
    assert first.token_id != second.token_id


def test_cooldown_skips_rate_limited_token():
    manager, _ = build_iloveapi_manager()
    manager.mark_rate_limited("iloveapi-1", retry_after=30)
    lease = manager.acquire_request(operation="pptx_to_pdf")
    assert lease.token_id == "iloveapi-2"


def test_exhaustion_raises_unavailable():
    manager, _ = build_iloveapi_manager(
        tokens=[TokenConfig("iloveapi-1", "pub1:sec1", rpm_limit=1, daily_limit=250)]
    )
    manager.acquire_request(operation="test")
    with pytest.raises(UnavailableException) as exc_info:
        manager.acquire_request(operation="test")
    assert exc_info.value.period == "minute"
    assert "busy" in exc_info.value.user_message.lower()


def test_redis_keys_use_iloveapi_prefix():
    manager, _ = build_iloveapi_manager()
    fixed_now = 1_700_000_000
    minute_key = manager._minute_key("iloveapi-1", fixed_now)
    day_key = manager._day_key("iloveapi-1", fixed_now)
    cooldown_key = manager._cooldown_key("iloveapi-1")
    assert minute_key.startswith("iloveapi:quota:")
    assert day_key.startswith("iloveapi:quota:")
    assert cooldown_key.startswith("iloveapi:quota:")


# ------------------------------------------------------------------
# Token parsing from settings
# ------------------------------------------------------------------

def test_parse_tokens_from_settings_json_pool(monkeypatch):
    monkeypatch.setattr(
        settings, "ILOVEAPI_KEYS",
        '[{"public_key": "pub_a", "secret_key": "sec_a"}, {"public_key": "pub_b", "secret_key": "sec_b"}]',
        raising=False,
    )
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TOKEN_RPM_LIMIT", 25, raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TOKEN_DAILY_LIMIT", 250, raising=False)

    specs = ILoveApiQuotaManager.parse_tokens_from_settings()
    assert len(specs) == 2
    assert specs[0].api_key == "pub_a:sec_a"
    assert specs[1].api_key == "pub_b:sec_b"
    assert specs[0].token_id == "iloveapi-1"


def test_parse_tokens_from_settings_legacy_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_KEYS", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "legacy_pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "legacy_sec", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TOKEN_RPM_LIMIT", 25, raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TOKEN_DAILY_LIMIT", 250, raising=False)

    specs = ILoveApiQuotaManager.parse_tokens_from_settings()
    assert len(specs) == 1
    assert specs[0].api_key == "legacy_pub:legacy_sec"
    assert specs[0].token_id == "iloveapi-default"


def test_parse_tokens_from_settings_no_keys_raises(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_KEYS", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TOKEN_RPM_LIMIT", 25, raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TOKEN_DAILY_LIMIT", 250, raising=False)

    with pytest.raises(ValueError, match="iLoveAPI keys configured"):
        ILoveApiQuotaManager.parse_tokens_from_settings()


# ------------------------------------------------------------------
# In-flight concurrency limiter
# ------------------------------------------------------------------

def test_acquire_inflight_respects_max_concurrent():
    manager, _ = build_iloveapi_manager(max_concurrent=2)
    assert manager.acquire_inflight() is True
    assert manager.acquire_inflight() is True
    # Third acquisition should fail — at capacity
    assert manager.acquire_inflight() is False


def test_release_inflight_decrements():
    manager, _ = build_iloveapi_manager(max_concurrent=1)
    assert manager.acquire_inflight() is True
    assert manager.acquire_inflight() is False  # at capacity
    manager.release_inflight()
    # After release, should be able to acquire again
    assert manager.acquire_inflight() is True


def test_inflight_key_has_ttl_safety_net():
    manager, redis_client = build_iloveapi_manager(max_concurrent=5)
    manager.acquire_inflight()
    ttl = redis_client.ttl(ILoveApiQuotaManager.INFLIGHT_KEY)
    assert ttl > 0
    assert ttl <= ILoveApiQuotaManager.INFLIGHT_TTL_SECONDS


def test_get_inflight_count():
    manager, _ = build_iloveapi_manager(max_concurrent=5)
    assert manager.get_inflight_count() == 0
    manager.acquire_inflight()
    assert manager.get_inflight_count() == 1
    manager.acquire_inflight()
    assert manager.get_inflight_count() == 2
    manager.release_inflight()
    assert manager.get_inflight_count() == 1


def test_release_inflight_floors_at_zero():
    manager, _ = build_iloveapi_manager(max_concurrent=5)
    # Release without any acquisition should not go negative
    manager.release_inflight()
    assert manager.get_inflight_count() == 0
    # Acquire should still work after over-release
    assert manager.acquire_inflight() is True
    assert manager.get_inflight_count() == 1


def test_acquire_inflight_fail_open_returns_none():
    manager = ILoveApiQuotaManager(
        cast(SyncRedisService, FailingSyncRedisService()),
        DEFAULT_TOKENS,
        max_concurrent=5,
    )

    assert manager.acquire_inflight() is None
