"""
Rate limit configuration singleton.

Holds tier maps, system rules, and limits library instances.
Supports atomic hot-reload of rules via GIL-safe reference swaps.
"""

import os
from typing import Optional

from loguru import logger

from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_RPM: int = 1000
CONCURRENCY_RETRY_AFTER_SECONDS: int = 30
REDIS_KEY_PREFIX: str = "knowhere-api:"

_RATE_LIMIT_BYPASSED_ENV: str = "RATE_LIMIT_BYPASSED"


def _is_rate_limit_bypassed() -> bool:
    """Check whether rate limiting is globally bypassed via env var."""
    return os.getenv(_RATE_LIMIT_BYPASSED_ENV, "false").lower() == "true"


class RateLimitConfig:
    """
    Singleton that owns the limits-library strategy instances and
    the in-memory tier / system-rule maps.

    Usage:
        config = RateLimitConfig.get_instance(redis_url)
    """

    _instance: Optional["RateLimitConfig"] = None

    def __init__(
        self, redis_url: str, key_prefix: str = REDIS_KEY_PREFIX
    ) -> None:
        from limits import parse as parse_rate
        from limits.aio.storage import RedisStorage
        from limits.aio.strategies import (
            FixedWindowRateLimiter,
            MovingWindowRateLimiter,
        )

        self._parse_rate = parse_rate
        self._key_prefix: str = key_prefix
        self._is_bypassed: bool = _is_rate_limit_bypassed()

        # Limits library instances
        async_redis_url = redis_url
        if not async_redis_url.startswith("async+"):
            async_redis_url = f"async+{redis_url}"

        self._storage: RedisStorage = RedisStorage(async_redis_url, implementation="redispy")
        self._sliding_window = MovingWindowRateLimiter(self._storage)
        self._fixed_window = FixedWindowRateLimiter(self._storage)

        # In-memory maps (GIL-safe reference swap on update)
        self._tier_map: dict[str, TierLimits] = {}
        self._system_rules: list[SystemRpmRule] = []

        logger.info(
            "RateLimitConfig initialised "
            f"(bypassed={self._is_bypassed}, prefix={self._key_prefix})"
        )

    # ------------------------------------------------------------------
    # Singleton accessor
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(
        cls,
        redis_url: Optional[str] = None,
        key_prefix: str = REDIS_KEY_PREFIX,
    ) -> "RateLimitConfig":
        if cls._instance is None:
            if redis_url is None:
                raise RuntimeError(
                    "RateLimitConfig.get_instance() requires redis_url "
                    "on first call."
                )
            cls._instance = cls(redis_url, key_prefix)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (useful for tests)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_bypassed(self) -> bool:
        return self._is_bypassed

    @property
    def key_prefix(self) -> str:
        return self._key_prefix

    @property
    def tier_map(self) -> dict[str, TierLimits]:
        return self._tier_map

    @property
    def system_rules(self) -> list[SystemRpmRule]:
        return self._system_rules

    @property
    def sliding_window(self):
        """MovingWindowRateLimiter instance."""
        return self._sliding_window

    @property
    def fixed_window(self):
        """FixedWindowRateLimiter instance."""
        return self._fixed_window

    @property
    def storage(self):
        """Underlying RedisStorage."""
        return self._storage

    # ------------------------------------------------------------------
    # Hot-reload
    # ------------------------------------------------------------------

    def update_rules(
        self,
        tier_map: dict[str, TierLimits],
        system_rules: list[SystemRpmRule],
    ) -> bool:
        """
        Atomically swap both maps.

        CPython's GIL guarantees that a single reference assignment is
        atomic, so readers never see a half-updated structure.

        Returns:
            True if rules were changed, False if no changes detected.
        """
        sorted_rules = sorted(system_rules, key=lambda r: r.priority)

        # Check if there are actual changes
        has_changes = (
            self._tier_map != tier_map
            or self._system_rules != sorted_rules
        )

        if has_changes:
            self._tier_map = tier_map
            self._system_rules = sorted_rules
            logger.info(
                f"Rate limit rules updated: "
                f"{len(tier_map)} tiers, {len(sorted_rules)} system rules"
            )

        return has_changes

    def parse_rate(self, rate_string: str):
        """Thin wrapper around limits.parse()."""
        return self._parse_rate(rate_string)

    def namespaced_namespace(self, namespace: str) -> str:
        """Build a Redis-safe namespace scoped by the configured key prefix."""
        base = (
            f"{self._key_prefix}rate_limit"
            if self._key_prefix.endswith(":")
            else f"{self._key_prefix}:rate_limit"
        )
        return f"{base}:{namespace}"
