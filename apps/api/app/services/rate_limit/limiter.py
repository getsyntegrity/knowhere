"""
Rate limiter layer implementations.

Wraps the ``limits`` library for Layer 0 (system limits), Layer 1 (Billing RPM),
and Layer 3 (Daily Quota) checks. Each layer raises RateLimitException on
rejection with appropriate retry headers.
"""

import time
from typing import Any

from loguru import logger

from app.services.rate_limit.config import RateLimitConfig
from shared.core.exceptions.domain_exceptions import RateLimitException

MAX_DAILY_QUOTA_RETRY_AFTER_SECONDS: int = 3600


class RateLimiter:
    """
    Stateless facade over the limits library strategies.

    All state (storage, strategies) lives in RateLimitConfig.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self._config: RateLimitConfig = config

    # ------------------------------------------------------------------
    # Layer 0 -- System limits (per-endpoint matched window)
    # ------------------------------------------------------------------

    async def check_system_limit(
        self,
        identifier: str,
        limit: int,
        matched_pattern: str,
        *,
        period: str = "minute",
        use_global_key: bool = False,
    ) -> None:
        """
        Layer 0: System limit check.

        Raises RateLimitException if the per-endpoint system limit
        is exhausted for the resolved identifier.
        """
        if self._config.is_bypassed or limit == -1:
            return

        rate_item = self._config.parse_rate(f"{limit}/{period}")
        namespace_suffix = (
            "system_limit" if period == "minute" else f"system_limit:{period}"
        )
        namespace = self._config.namespaced_namespace(namespace_suffix)
        rate_limit_key = (
            identifier
            if use_global_key
            else f"{identifier}:{matched_pattern}"
        )
        window = (
            self._config.fixed_window
            if period == "day"
            else self._config.sliding_window
        )
        strategy = "fixed" if period == "day" else "sliding"

        is_allowed: bool = await window.hit(
            rate_item, namespace, rate_limit_key
        )
        if not is_allowed:
            headers = await self._build_rejection_headers(
                rate_item,
                namespace,
                rate_limit_key,
                limit,
                period,
                strategy=strategy,
            )
            target = (
                f"route={identifier}, pattern={matched_pattern}"
                if use_global_key
                else f"user={identifier}, pattern={matched_pattern}"
            )
            logger.warning(
                "System limit exceeded: {}, limit={}/{}",
                target,
                limit,
                period,
            )
            exc = RateLimitException(
                retry_after=headers["retry_after"],
                limit=limit,
                period=period,
                internal_message=(
                    f"System limit exceeded for {target}, "
                    f"limit={limit}/{period}"
                ),
            )
            exc.details.update(
                {
                    "remaining": headers["remaining"],
                    "reset": headers["reset_time"],
                }
            )
            raise exc

    # ------------------------------------------------------------------
    # Layer 1 -- Billing RPM (per-user sliding window)
    # ------------------------------------------------------------------

    async def check_billing_rpm(
        self,
        user_id: str,
        rpm: int,
    ) -> None:
        """
        Layer 1: Billing RPM check.

        Raises RateLimitException if the user's tier RPM is exhausted.
        """
        if self._config.is_bypassed or rpm == -1:
            return

        rate_item = self._config.parse_rate(f"{rpm}/minute")
        namespace = self._config.namespaced_namespace("billing_rpm")
        identifier = user_id

        is_allowed: bool = await self._config.sliding_window.hit(
            rate_item, namespace, identifier
        )
        if not is_allowed:
            headers = await self._build_rejection_headers(
                rate_item, namespace, identifier, rpm, "minute", strategy="sliding"
            )
            logger.warning(
                f"Billing RPM exceeded: user={user_id}, limit={rpm}/min"
            )
            exc = RateLimitException(
                retry_after=headers["retry_after"],
                limit=rpm,
                period="minute",
                internal_message=(
                    f"Billing RPM exceeded for user={user_id}, "
                    f"limit={rpm}/min"
                ),
            )
            exc.details.update(
                {
                    "remaining": headers["remaining"],
                    "reset": headers["reset_time"],
                }
            )
            raise exc

    # ------------------------------------------------------------------
    # Layer 3 -- Daily Quota (fixed window)
    # ------------------------------------------------------------------

    async def check_daily_quota(
        self,
        user_id: str,
        quota: int,
    ) -> None:
        """
        Layer 3: Daily quota check.

        Raises RateLimitException if the user's daily request quota
        is exhausted.
        """
        if self._config.is_bypassed or quota == -1:
            return

        rate_item = self._config.parse_rate(f"{quota}/day")
        namespace = self._config.namespaced_namespace("daily_quota")
        identifier = user_id

        is_allowed: bool = await self._config.fixed_window.hit(
            rate_item, namespace, identifier
        )
        if not is_allowed:
            headers = await self._build_rejection_headers(
                rate_item, namespace, identifier, quota, "day", strategy="fixed"
            )
            logger.warning(
                f"Daily quota exceeded: user={user_id}, limit={quota}/day"
            )
            exc = RateLimitException(
                retry_after=min(
                    headers["retry_after"],
                    MAX_DAILY_QUOTA_RETRY_AFTER_SECONDS,
                ),
                limit=quota,
                period="day",
                internal_message=(
                    f"Daily quota exceeded for user={user_id}, "
                    f"limit={quota}/day"
                ),
            )
            exc.details.update(
                {
                    "remaining": headers["remaining"],
                    "reset": headers["reset_time"],
                }
            )
            raise exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _build_rejection_headers(
        self,
        rate_item: Any,
        namespace: str,
        identifier: str,
        limit: int,
        period: str,
        strategy: str = "sliding",
    ) -> dict[str, Any]:
        """
        Build X-RateLimit-* style header values from window stats.

        Returns a dict with keys: retry_after, limit, remaining, reset_time.
        """
        try:
            if strategy == "fixed":
                stats = await self._config.fixed_window.get_window_stats(
                    rate_item, namespace, identifier
                )
            else:
                stats = await self._config.sliding_window.get_window_stats(
                    rate_item, namespace, identifier
                )
            reset_time: int = int(stats.reset_time)
            remaining: int = max(0, int(stats.remaining))
            now: int = int(time.time())
            retry_after: int = max(1, reset_time - now)
        except Exception:
            logger.debug(
                "Failed to retrieve window stats, using defaults",
                exc_info=True,
            )
            retry_after = RateLimitException.DEFAULT_RETRY_AFTER
            remaining = 0
            reset_time = int(time.time()) + retry_after

        return {
            "retry_after": retry_after,
            "limit": limit,
            "remaining": remaining,
            "reset_time": reset_time,
        }
