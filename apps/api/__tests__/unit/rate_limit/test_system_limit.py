from app.services.rate_limit.config import DEFAULT_SYSTEM_LIMIT
from app.services.rate_limit.data_structures import SystemLimitRule
from app.services.rate_limit.system_limit import find_system_rule


def test_find_system_rule_matches_rule_and_returns_the_rule():
    rules = [
        SystemLimitRule(
            method="GET", api_pattern="/v1/jobs/*", priority=100, limit=200
        ),
        SystemLimitRule(method="*", api_pattern="*", priority=9999, limit=1000),
    ]
    rule = find_system_rule("GET", "/v1/jobs/abc", rules)
    assert rule.limit == 200
    assert rule.api_pattern == "/v1/jobs/*"
    assert rule.period == "minute"


def test_find_system_rule_method_match_is_case_insensitive():
    rules = [
        SystemLimitRule(method="post", api_pattern="/v1/jobs", priority=100, limit=30),
    ]
    rule = find_system_rule("POST", "/v1/jobs", rules)
    assert rule.limit == 30
    assert rule.api_pattern == "/v1/jobs"
    assert rule.period == "minute"


def test_find_system_rule_first_match_wins_by_rule_order():
    rules = [
        SystemLimitRule(method="GET", api_pattern="/v1/*", priority=200, limit=300),
        SystemLimitRule(
            method="GET", api_pattern="/v1/jobs/*", priority=100, limit=100
        ),
    ]
    rule = find_system_rule("GET", "/v1/jobs/abc", rules)
    assert rule.limit == 300
    assert rule.api_pattern == "/v1/*"
    assert rule.period == "minute"


def test_find_system_rule_falls_back_to_default_when_no_match():
    rules = [
        SystemLimitRule(
            method="GET", api_pattern="/v1/jobs/*", priority=100, limit=200
        ),
    ]
    rule = find_system_rule("POST", "/v1/unknown", rules)
    assert rule.limit == DEFAULT_SYSTEM_LIMIT
    assert rule.api_pattern == "*"
    assert rule.period == "minute"
