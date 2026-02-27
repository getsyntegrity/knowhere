"""
Frozen dataclasses for the rate limiting domain.

These are immutable value objects shared across the rate limiting package.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    """Identifies the current authenticated user and their billing tier."""

    user_id: str
    user_tier: str


@dataclass(frozen=True)
class TierLimits:
    """
    Rate limits for a specific billing tier.

    A value of -1 means unlimited (no enforcement).
    """

    rpm_limit: int
    max_concurrent_jobs: int
    daily_quota: int


@dataclass(frozen=True)
class SystemRpmRule:
    """
    A system-level RPM rule that matches HTTP method + path pattern.

    Rules are sorted by priority ascending; first match wins.
    """

    method: str
    api_pattern: str
    priority: int
    rpm: int
