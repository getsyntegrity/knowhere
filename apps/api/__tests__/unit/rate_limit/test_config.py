from app.services.rate_limit.config import (
    RateLimitConfig,
    _is_rate_limit_bypassed,
)
from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits
from shared.core.exceptions.redis_exceptions import RedisConfigurationError


def test_is_rate_limit_bypassed_reads_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_BYPASSED", "true")
    assert _is_rate_limit_bypassed() is True
    monkeypatch.setenv("RATE_LIMIT_BYPASSED", "false")
    assert _is_rate_limit_bypassed() is False


def test_get_instance_requires_redis_url_on_first_call():
    RateLimitConfig.reset_instance()
    try:
        try:
            RateLimitConfig.get_instance()
            assert False, "Expected RuntimeError"
        except RedisConfigurationError as exc:
            assert "requires redis_url on first call" in str(exc)
    finally:
        RateLimitConfig.reset_instance()


def test_update_rules_sorts_system_rules_by_priority():
    cfg = object.__new__(RateLimitConfig)
    cfg._tier_map = {}
    cfg._system_rules = []
    cfg._key_prefix = "knowhere-api:"

    tier_map = {
        "free": TierLimits(rpm_limit=2, max_concurrent_jobs=2, daily_quota=20)
    }
    unsorted_rules = [
        SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000),
        SystemRpmRule(method="POST", api_pattern="/v1/jobs", priority=100, rpm=30),
    ]

    cfg.update_rules(tier_map, unsorted_rules)

    assert cfg.tier_map == tier_map
    assert [r.priority for r in cfg.system_rules] == [100, 9999]
    assert (
        cfg.namespaced_namespace("system_rpm")
        == "knowhere-api:rate_limit:system_rpm"
    )
