from app.services.rate_limit.config import DEFAULT_SYSTEM_RPM
from app.services.rate_limit.data_structures import SystemRpmRule
from app.services.rate_limit.system_rpm import find_system_rpm


def test_find_system_rpm_matches_rule_and_returns_pattern():
    rules = [
        SystemRpmRule(method="GET", api_pattern="/v1/jobs/*", priority=100, rpm=200),
        SystemRpmRule(method="*", api_pattern="*", priority=9999, rpm=1000),
    ]
    rpm, pattern = find_system_rpm("GET", "/v1/jobs/abc", rules)
    assert rpm == 200
    assert pattern == "/v1/jobs/*"


def test_find_system_rpm_method_match_is_case_insensitive():
    rules = [
        SystemRpmRule(method="post", api_pattern="/v1/jobs", priority=100, rpm=30),
    ]
    rpm, pattern = find_system_rpm("POST", "/v1/jobs", rules)
    assert rpm == 30
    assert pattern == "/v1/jobs"


def test_find_system_rpm_first_match_wins_by_rule_order():
    rules = [
        SystemRpmRule(method="GET", api_pattern="/v1/*", priority=200, rpm=300),
        SystemRpmRule(method="GET", api_pattern="/v1/jobs/*", priority=100, rpm=100),
    ]
    rpm, pattern = find_system_rpm("GET", "/v1/jobs/abc", rules)
    assert rpm == 300
    assert pattern == "/v1/*"


def test_find_system_rpm_falls_back_to_default_when_no_match():
    rules = [
        SystemRpmRule(method="GET", api_pattern="/v1/jobs/*", priority=100, rpm=200),
    ]
    rpm, pattern = find_system_rpm("POST", "/v1/unknown", rules)
    assert rpm == DEFAULT_SYSTEM_RPM
    assert pattern == "*"
