"""System rate-limit rule matching."""

import fnmatch

from app.services.rate_limit.config import DEFAULT_SYSTEM_LIMIT, DEFAULT_SYSTEM_PERIOD
from app.services.rate_limit.data_structures import SystemLimitRule


def find_system_rule(
    method: str,
    path: str,
    rules: list[SystemLimitRule],
) -> SystemLimitRule:
    """Find the first matching system rate-limit rule."""
    for rule in rules:
        is_method_match = (
            rule.method == "*" or fnmatch.fnmatch(method.upper(), rule.method.upper())
        )
        if not is_method_match:
            continue

        if fnmatch.fnmatch(path, rule.api_pattern):
            return rule

    return SystemLimitRule(
        method="*",
        api_pattern="*",
        priority=9999,
        limit=DEFAULT_SYSTEM_LIMIT,
        period=DEFAULT_SYSTEM_PERIOD,
    )
