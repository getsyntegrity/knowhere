"""
FastAPI dependencies for the rate-limit layer.

Dependency chain (outermost -> innermost):
    require_billing_limits  ->  with_current_user  ->  get_current_user_id
                            ->  get_db

``with_current_user`` resolves the user's billing tier, caches it in Redis,
and enforces the matched system limit (Layer 0).

``require_billing_limits`` enforces billing RPM (Layer 1) when billing is
enabled and yields control to the route handler. Concurrency (Layer 2) and
daily quota (Layer 3) are enforced just before insert in the create-job route
only when billing is enabled.
"""

import math
from typing import AsyncGenerator

from app.core.dependencies import get_current_user_id
from app.services.rate_limit.config import (
    CONCURRENCY_RETRY_AFTER_SECONDS,
    RateLimitConfig,
)
from app.services.rate_limit.data_structures import CurrentUser, TierLimits
from app.services.rate_limit.identity_cache import identity_cache
from app.services.rate_limit.limiter import RateLimiter
from app.services.rate_limit.system_limit import find_system_rule
from fastapi import Depends, Request
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.config import redis_pool_manager, settings
from shared.core.database import get_db, get_db_context
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)
from shared.core.logging import log_context
from shared.core.state_machine.states import JobStatus
from shared.models.database.job import Job
from shared.models.database.user_balance import UserBalance

_DEFAULT_TIER: str = "free"
_ACTIVE_JOB_STATES: tuple[str, ...] = (
    JobStatus.WAITING_FILE.value,
    JobStatus.PENDING.value,
    JobStatus.RUNNING.value,
    JobStatus.CONVERTING.value,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_user_tier_from_db(user_id: str) -> str:
    """Query the user_balances table for the user's tier.

    Returns ``"free"`` when no balance record exists.
    """
    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(UserBalance.user_tier)
                .where(UserBalance.user_id == user_id)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row if row is not None else _DEFAULT_TIER
    except Exception:
        logger.warning(
            "rate_limit: DB fallback for user_tier failed, "
            "defaulting to '{}' for user_id={}",
            _DEFAULT_TIER,
            user_id,
        )
        return _DEFAULT_TIER


def _get_route_path(request: Request) -> str:
    """Return the request path without the application's root_path prefix."""
    scope_path: str = request.scope.get("path", request.url.path)
    root_path: str = request.scope.get("root_path", "")
    if root_path and scope_path.startswith(root_path):
        return scope_path[len(root_path) :]
    return scope_path


def _get_route_limit_identifier(request: Request) -> str:
    """Return a stable identifier for route-scoped system limits."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path

    route_path_format = getattr(route, "path_format", None)
    if isinstance(route_path_format, str) and route_path_format:
        return route_path_format

    return _get_route_path(request)


# ---------------------------------------------------------------------------
# with_current_user -- Layer 0 (matched system limit)
# ---------------------------------------------------------------------------


async def with_current_user(
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> AsyncGenerator[CurrentUser, None]:
    """Resolve identity and enforce the matched system limit.

    Steps:
        1. ``get_current_user_id`` already authenticated the user (401
           on failure).
        2. Resolve ``user_tier`` from the tier cache; fall back to DB on
           cache miss or Redis error.
        3. If ``RATE_LIMIT_ENABLED=false`` is set, return immediately.
        4. Check the matched system limit via the rate limiter (fail-open on
           Redis error).
    """
    redis_service = redis_pool_manager.get_redis_service()

    # -- Resolve user_tier (cache -> DB fallback) --
    user_tier: str | None = None
    try:
        cached: dict[str, str] | None = await identity_cache.get_user_tier(
            redis_service, user_id
        )
        if cached is not None:
            user_tier = cached.get("user_tier", _DEFAULT_TIER)
        else:
            user_tier = await _resolve_user_tier_from_db(user_id)
            await identity_cache.set_user_tier(redis_service, user_id, user_tier)
    except Exception:
        logger.warning(
            "rate_limit: Redis error during tier resolution, "
            "falling back to DB for user_id={}",
            user_id,
        )
        user_tier = await _resolve_user_tier_from_db(user_id)

    if user_tier is None:
        user_tier = _DEFAULT_TIER

    current_user = CurrentUser(user_id=user_id, user_tier=user_tier)

    with log_context(user_id=user_id):
        # -- Global rate-limit switch --
        config = RateLimitConfig.get_instance()
        if not config.is_enabled:
            yield current_user
            return

        # -- Layer 0: matched system limit --
        try:
            route_path = _get_route_path(request)
            rule = find_system_rule(request.method, route_path, config.system_rules)
            limiter = RateLimiter(config)
            await limiter.check_system_limit(
                identifier=user_id,
                limit=rule.limit,
                matched_pattern=rule.api_pattern,
                period=rule.period,
            )
        except RateLimitException:
            raise
        except Exception as exc:
            # Fail-open: log and let the request through.
            logger.warning(
                "rate_limit: Redis error during system limit check, "
                "failing open for user_id={}, error={}",
                user_id,
                exc,
            )

        yield current_user


# ---------------------------------------------------------------------------
# require_billing_limits -- Layer 1
# (billing RPM)
# ---------------------------------------------------------------------------

_RETRY_AFTER_SECONDS: int = 15


async def require_billing_limits(
    request: Request,
    current_user: CurrentUser = Depends(with_current_user),
    _db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[CurrentUser, None]:
    """Enforce billing RPM (Layer 1) around the route handler.

    This is an async-generator (yield) dependency so that teardown logic
    can run after the route handler completes.

    Layer enforced before yield:
        1. Billing RPM  -- per-user requests-per-minute

    Layers enforced inside route just before insert:
        2. Non-terminal jobs concurrency -- max pending/running jobs
        3. Daily quota (free tier only) -- hard daily cap

    When ``BILLING_ENABLED=false``, this yields after identity and system
    route limiting. Otherwise, Redis failures raise 503 because billing
    enforcement must not be silently skipped.
    """
    if not settings.BILLING_ENABLED:
        yield current_user
        return

    config = RateLimitConfig.get_instance()
    if not config.is_enabled:
        yield current_user
        return

    tier_limits: TierLimits | None = config.tier_map.get(current_user.user_tier)
    if tier_limits is None:
        logger.error(
            "rate_limit: no tier config for tier='{}', user_id={}",
            current_user.user_tier,
            current_user.user_id,
        )
        raise UnavailableException(
            internal_message=(f"Missing tier config for tier={current_user.user_tier}"),
            retry_after=_RETRY_AFTER_SECONDS,
        )

    # -- Layer 1: billing RPM --
    limiter = RateLimiter(config)
    try:
        await limiter.check_billing_rpm(current_user.user_id, tier_limits.rpm_limit)
    except RateLimitException:
        raise
    except Exception as exc:
        raise UnavailableException(
            internal_message=(f"Redis error in billing RPM check: {exc}"),
            retry_after=_RETRY_AFTER_SECONDS,
        )

    yield current_user


async def require_route_system_limit(request: Request) -> None:
    """Apply the matched system limit to the current route using a route key.

    Prefer the framework route template so paths with different parameters
    share the same budget bucket. If no explicit rule matches, the default
    system rule still protects the route with the wider fallback budget.
    Fail closed when Redis or limiter state is unavailable.
    """
    config = RateLimitConfig.get_instance()
    if not config.is_enabled:
        return

    route_path = _get_route_path(request)
    route_identifier = _get_route_limit_identifier(request)
    rule = find_system_rule(request.method, route_path, config.system_rules)
    limiter = RateLimiter(config)
    try:
        await limiter.check_system_limit(
            identifier=route_identifier,
            limit=rule.limit,
            matched_pattern=rule.api_pattern,
            period=rule.period,
            use_global_key=True,
        )
    except RateLimitException:
        raise
    except Exception as exc:
        raise UnavailableException(
            internal_message=(f"Redis error in route system limit: {exc}"),
            retry_after=_RETRY_AFTER_SECONDS,
            limit=rule.limit,
            period=rule.period,
        )


async def enforce_job_creation_capacity(
    request: Request,
    db: AsyncSession,
    current_user: CurrentUser,
) -> None:
    """Enforce Layers 2-3 immediately before job insert."""
    if not settings.BILLING_ENABLED:
        return

    config = RateLimitConfig.get_instance()
    if not config.is_enabled:
        return

    tier_limits = config.tier_map.get(current_user.user_tier)
    if tier_limits is None:
        logger.error(
            "rate_limit: no tier config for tier='{}', user_id={}",
            current_user.user_tier,
            current_user.user_id,
        )
        raise UnavailableException(
            internal_message=(f"Missing tier config for tier={current_user.user_tier}"),
            retry_after=_RETRY_AFTER_SECONDS,
        )

    limiter = RateLimiter(config)

    # -- Layer 2: non-terminal jobs concurrency (DB-locked) --
    if tier_limits.max_concurrent_jobs != -1:
        try:
            await _acquire_user_concurrency_lock(db, current_user.user_id)
            active_jobs = await _count_non_terminal_jobs(db, current_user.user_id)
            if active_jobs >= tier_limits.max_concurrent_jobs:
                retry_after_seconds = _compute_concurrency_retry_after_seconds(
                    base_retry_after_seconds=CONCURRENCY_RETRY_AFTER_SECONDS,
                    rpm_limit=tier_limits.rpm_limit,
                )
                exc = RateLimitException(
                    retry_after=retry_after_seconds,
                    limit=tier_limits.max_concurrent_jobs,
                    period="concurrent",
                    user_message=(
                        f"Too many concurrent requests "
                        f"({active_jobs}/{tier_limits.max_concurrent_jobs} active). "
                        f"Please retry after {retry_after_seconds} seconds."
                    ),
                    internal_message=(
                        "Concurrency limit exceeded: "
                        f"user_id={current_user.user_id}, "
                        f"active_jobs={active_jobs}, "
                        f"limit={tier_limits.max_concurrent_jobs}, "
                        f"retry_after={retry_after_seconds}s"
                    ),
                )
                exc.details.update(
                    {
                        "active_jobs": active_jobs,
                        "available_slots": max(
                            0, tier_limits.max_concurrent_jobs - active_jobs
                        ),
                    }
                )
                raise exc
        except RateLimitException:
            raise
        except Exception as exc:
            raise UnavailableException(
                internal_message=(f"DB error in concurrency check: {exc}"),
                retry_after=_RETRY_AFTER_SECONDS,
            )

    # -- Layer 3: daily quota --
    if tier_limits.daily_quota != -1:
        try:
            await limiter.check_daily_quota(
                current_user.user_id, tier_limits.daily_quota
            )
        except RateLimitException:
            raise
        except Exception as exc:
            raise UnavailableException(
                internal_message=(f"Redis error in daily quota check: {exc}"),
                retry_after=_RETRY_AFTER_SECONDS,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _acquire_user_concurrency_lock(
    db: AsyncSession,
    user_id: str,
) -> None:
    """Acquire a per-user row lock to serialize concurrent job creation.

    Locks the UserBalance row instead of User to avoid contention with
    unrelated operations (profile updates, etc.) that may also lock User.
    """
    result = await db.execute(
        select(UserBalance.user_id)
        .where(UserBalance.user_id == user_id)
        .with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise RateLimitException(
            internal_message=f"UserBalance row not found for user_id={user_id}"
        )


def _compute_concurrency_retry_after_seconds(
    base_retry_after_seconds: int,
    rpm_limit: int,
) -> int:
    """
    Compute Retry-After hint for concurrency rejections.

    Concurrency has no deterministic reset timestamp, so we provide a
    conservative client hint:
    - floor: configured base retry (currently 30s)
    - if billing RPM is finite, also respect one request spacing
      (ceil(60 / rpm_limit)) to reduce immediate repeated 429s
    """
    if rpm_limit <= 0:
        return base_retry_after_seconds
    return max(base_retry_after_seconds, int(math.ceil(60 / rpm_limit)))


async def _count_non_terminal_jobs(
    db: AsyncSession,
    user_id: str,
) -> int:
    """Count non-terminal jobs for a user in the current transaction."""
    result = await db.execute(
        select(func.count(Job.job_id))
        .where(Job.user_id == user_id)
        .where(Job.status.in_(_ACTIVE_JOB_STATES))
    )
    return int(result.scalar_one() or 0)
