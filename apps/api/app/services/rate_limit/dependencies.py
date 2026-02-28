"""
FastAPI dependencies for the rate-limit layer.

Dependency chain (outermost -> innermost):
    require_billing_limits  ->  with_current_user  ->  get_current_user_id
                            ->  generate_job_id
                            ->  get_db

``with_current_user`` resolves identity (user_id + user_tier), caches it in
Redis, and enforces the system-wide RPM limit (Layer 0).

``require_billing_limits`` enforces billing RPM (Layer 1) and yields control
to the route handler. Concurrency (Layer 2) and daily quota (Layer 3) are
enforced just before insert in the create-job route.
"""

import os
import hashlib
import math
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import Depends, Request
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_id
from shared.core.config import redis_pool_manager
from app.services.rate_limit.config import (
    CONCURRENCY_RETRY_AFTER_SECONDS,
    RateLimitConfig,
)
from app.services.rate_limit.data_structures import CurrentUser, TierLimits
from app.services.rate_limit.identity_cache import identity_cache
from app.services.rate_limit.limiter import RateLimiter
from app.services.rate_limit.system_rpm import find_system_rpm
from shared.core.database import get_db, get_db_context
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)
from shared.core.state_machine.states import JobStatus
from shared.models.database.api_key import APIKey
from shared.models.database.job import Job
from shared.models.database.user import User
from shared.models.database.user_balance import UserBalance

_RATE_LIMIT_BYPASSED: bool = os.getenv("RATE_LIMIT_BYPASSED", "").lower() == "true"

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


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract bearer token from Authorization header."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def _resolve_apikey_cache_ttl_seconds(api_key_hash: str) -> int:
    """Resolve cache TTL for API key identity (max 1 hour)."""
    max_ttl_seconds = 3600
    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(APIKey.expires_at)
                .where(APIKey.key_hash == api_key_hash)
                .limit(1)
            )
            expires_at = result.scalar_one_or_none()
            if expires_at is None:
                return max_ttl_seconds

            # APIKey.expires_at is stored as UTC-naive datetime.
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            remaining = int((expires_at - now).total_seconds())
            return max(1, min(max_ttl_seconds, remaining))
    except Exception:
        return max_ttl_seconds


def generate_job_id() -> str:
    """Create a short, unique job identifier."""
    return f"job_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# with_current_user -- Layer 0 (system RPM)
# ---------------------------------------------------------------------------


async def with_current_user(
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> CurrentUser:
    """Resolve identity and enforce the system-wide RPM limit.

    Steps:
        1. ``get_current_user_id`` already authenticated the user (401
           on failure).
        2. Resolve ``user_tier`` from the identity cache; fall back to DB on
           cache miss or Redis error.
        3. If ``RATE_LIMIT_BYPASSED`` is set, return immediately.
        4. Check system RPM via the rate limiter (fail-open on Redis error).
    """
    redis_service = redis_pool_manager.get_redis_service()

    # -- Resolve user_tier (cache -> DB fallback) --
    user_tier: str = _DEFAULT_TIER
    token = _extract_bearer_token(request.headers.get("authorization"))
    is_api_key_auth = bool(token and token.startswith("sk_"))
    api_key_hash = hashlib.sha256(token.encode()).hexdigest() if is_api_key_auth else None
    cache_key: str = (
        identity_cache._apikey_key(api_key_hash)
        if is_api_key_auth and api_key_hash
        else identity_cache._jwt_key(user_id)
    )
    try:
        cached: dict | None = await identity_cache.get_cached_identity(
            redis_service, cache_key
        )
        if cached is not None:
            user_tier = cached.get("user_tier", _DEFAULT_TIER)
        else:
            user_tier = await _resolve_user_tier_from_db(user_id)
            if is_api_key_auth and api_key_hash:
                ttl_seconds = await _resolve_apikey_cache_ttl_seconds(api_key_hash)
                await identity_cache.set_apikey_identity(
                    redis_service,
                    api_key_hash,
                    user_id,
                    user_tier,
                    ttl_seconds=ttl_seconds,
                )
            else:
                await identity_cache.set_jwt_identity(redis_service, user_id, user_tier)
    except Exception:
        logger.warning(
            "rate_limit: Redis error during identity resolution, "
            "falling back to DB for user_id={}",
            user_id,
        )
        user_tier = await _resolve_user_tier_from_db(user_id)

    current_user = CurrentUser(user_id=user_id, user_tier=user_tier)

    # -- Bypass switch --
    if _RATE_LIMIT_BYPASSED:
        return current_user

    # -- Layer 0: system RPM --
    try:
        config = RateLimitConfig.get_instance()
        scope_path: str = request.scope.get("path", request.url.path)
        root_path: str = request.scope.get("root_path", "")
        route_path: str = (
            scope_path[len(root_path):]
            if root_path and scope_path.startswith(root_path)
            else scope_path
        )
        rpm, matched_pattern = find_system_rpm(
            request.method, route_path, config.system_rules
        )
        limiter = RateLimiter(config)
        await limiter.check_system_rpm(user_id, rpm, matched_pattern)
    except RateLimitException:
        raise
    except Exception as exc:
        # Fail-open: log and let the request through.
        logger.warning(
            "rate_limit: Redis error during system RPM check, "
            "failing open for user_id={}, error={}",
            user_id,
            exc,
        )

    return current_user


# ---------------------------------------------------------------------------
# require_billing_limits -- Layer 1
# (billing RPM)
# ---------------------------------------------------------------------------

_RETRY_AFTER_SECONDS: int = 15


async def require_billing_limits(
    request: Request,
    current_user: CurrentUser = Depends(with_current_user),
    job_id: str = Depends(generate_job_id),
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

    On any Redis failure the dependency raises 503 (fail-close) because
    billing enforcement must not be silently skipped.
    """
    config = RateLimitConfig.get_instance()
    tier_limits: TierLimits | None = config.tier_map.get(
        current_user.user_tier
    )
    if tier_limits is None:
        logger.error(
            "rate_limit: no tier config for tier='{}', user_id={}",
            current_user.user_tier,
            current_user.user_id,
        )
        raise UnavailableException(
            internal_message=(
                f"Missing tier config for tier={current_user.user_tier}"
            ),
            retry_after=_RETRY_AFTER_SECONDS,
        )

    if _RATE_LIMIT_BYPASSED:
        request.state.job_id = job_id
        yield current_user
        return

    redis_service = redis_pool_manager.get_redis_service()
    try:
        await redis_service._get_client()
    except Exception as exc:
        raise UnavailableException(
            internal_message=f"Redis error acquiring client: {exc}",
            retry_after=_RETRY_AFTER_SECONDS,
        )

    # -- Layer 1: billing RPM --
    limiter = RateLimiter(config)
    try:
        await limiter.check_billing_rpm(
            current_user.user_id, tier_limits.rpm_limit
        )
    except RateLimitException:
        raise
    except Exception as exc:
        raise UnavailableException(
            internal_message=(
                f"Redis error in billing RPM check: {exc}"
            ),
            retry_after=_RETRY_AFTER_SECONDS,
        )

    # -- Hand control to the route handler --
    request.state.rate_limit_tier_limits = tier_limits
    request.state.job_id = job_id
    yield current_user


async def enforce_job_creation_capacity(
    request: Request,
    db: AsyncSession,
    current_user: CurrentUser,
) -> None:
    """Enforce Layers 2-3 immediately before job insert."""
    if _RATE_LIMIT_BYPASSED:
        return

    config = RateLimitConfig.get_instance()
    tier_limits = getattr(request.state, "rate_limit_tier_limits", None)
    if not isinstance(tier_limits, TierLimits):
        tier_limits = config.tier_map.get(current_user.user_tier)

    if tier_limits is None:
        logger.error(
            "rate_limit: no tier config for tier='{}', user_id={}",
            current_user.user_tier,
            current_user.user_id,
        )
        raise UnavailableException(
            internal_message=(
                f"Missing tier config for tier={current_user.user_tier}"
            ),
            retry_after=_RETRY_AFTER_SECONDS,
        )

    limiter = RateLimiter(config)

    # -- Layer 2: non-terminal jobs concurrency (DB-locked) --
    if tier_limits.max_concurrent_jobs != -1:
        try:
            await _acquire_user_concurrency_lock(db, current_user.user_id)
            active_jobs = await _count_non_terminal_jobs(
                db, current_user.user_id
            )
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
                        "Please retry after {retry_after} seconds."
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
                internal_message=(
                    f"DB error in concurrency check: {exc}"
                ),
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
                internal_message=(
                    f"Redis error in daily quota check: {exc}"
                ),
                retry_after=_RETRY_AFTER_SECONDS,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _acquire_user_concurrency_lock(
    db: AsyncSession,
    user_id: str,
) -> None:
    """Acquire a per-user row lock to serialize concurrent job creation."""
    result = await db.execute(
        select(User.id).where(User.id == user_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise RuntimeError(f"User row not found for user_id={user_id}")


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
