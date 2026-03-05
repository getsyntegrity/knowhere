"""
System RPM rule matching.

Iterates pre-sorted rules and returns the first fnmatch hit.
Falls back to DEFAULT_SYSTEM_RPM when no rule matches.
"""

import fnmatch

from app.services.rate_limit.config import DEFAULT_SYSTEM_RPM
from app.services.rate_limit.data_structures import SystemRpmRule


def find_system_rpm(
    method: str,
    path: str,
    rules: list[SystemRpmRule],
) -> tuple[int, str]:
    """
    Find the applicable system RPM for a given HTTP method and path.

    Args:
        method: HTTP method (e.g. "GET", "POST").
        path: Request path (e.g. "/api/v1/jobs").
        rules: Pre-sorted list of SystemRpmRule (ascending priority).

    Returns:
        A tuple of (rpm, matched_pattern).
        Falls back to (DEFAULT_SYSTEM_RPM, "*") when no rule matches.
    """
    for rule in rules:
        is_method_match = (
            rule.method == "*" or fnmatch.fnmatch(method.upper(), rule.method.upper())
        )
        if not is_method_match:
            continue

        if fnmatch.fnmatch(path, rule.api_pattern):
            return rule.rpm, rule.api_pattern

    return DEFAULT_SYSTEM_RPM, "*"
