"""
FastAPI dependencies for the rate-limit layer.

Dependency chain (outermost -> innermost):
    require_billing_limits  ->  with_current_user  ->  get_current_user_id
                            ->  generate_job_id

``with_current_user`` resolves identity (user_id + user_tier), caches it in
Redis, and enforces the system-wide RPM limit (Layer 0).

``require_billing_limits`` enforces the billing layers (RPM, concurrency
semaphore, daily quota) and yields control to the route handler.
"""

import os
import hashlib
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import Depends, Request
from loguru import logger
from sqlalchemy import select

from app.core.dependencies import get_current_user_id
from shared.core.config import redis_pool_manager
from app.services.rate_limit.config import (
    CONCURRENCY_RETRY_AFTER_SECONDS,
    RateLimitConfig,
)
from app.services.rate_limit.data_structures import CurrentUser, TierLimits
from app.services.rate_limit.identity_cache import identity_cache
from app.services.rate_limit.limiter import RateLimiter
from app.services.rate_limit.semaphore import ConcurrencySemaphore
from app.services.rate_limit.system_rpm import find_system_rpm
from shared.core.database import get_db_context
from shared.core.exceptions.domain_exceptions import (
    RateLimitException,
    UnavailableException,
)
from shared.models.database.api_key import APIKey
from shared.models.database.user_balance import UserBalance

_RATE_LIMIT_BYPASSED: bool = os.getenv("RATE_LIMIT_BYPASSED", "").lower() == "true"

_DEFAULT_TIER: str = "free"


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
        rpm, matched_pattern = find_system_rpm(
            request.method, request.url.path, config.system_rules
        )
        limiter = RateLimiter(config)
        await limiter.check_system_rpm(user_id, rpm, matched_pattern)
    except RateLimitException:
        raise
    except Exception:
        # Fail-open: log and let the request through.
        logger.warning(
            "rate_limit: Redis error during system RPM check, "
            "failing open for user_id={}",
            user_id,
        )

    return current_user


# ---------------------------------------------------------------------------
# require_billing_limits -- Layers 1-3 (billing RPM, semaphore, daily quota)
# ---------------------------------------------------------------------------

_RETRY_AFTER_SECONDS: int = 15


async def require_billing_limits(
    request: Request,
    current_user: CurrentUser = Depends(with_current_user),
    job_id: str = Depends(generate_job_id),
) -> AsyncGenerator[CurrentUser, None]:
    """Enforce billing-layer rate limits around the route handler.

    This is an async-generator (yield) dependency so that teardown logic
    (semaphore release) runs after the route handler completes.

    Layers enforced before yield:
        1. Billing RPM  -- per-user requests-per-minute
        2. Concurrency semaphore -- max parallel in-flight requests
        3. Daily quota (free tier only) -- hard daily cap

    Teardown (after yield):
        Always release the semaphore slot when the request completes.

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
    raw_redis = None
    semaphore_acquired: bool = False

    try:
        try:
            raw_redis = await redis_service._get_client()
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

        # -- Layer 2: concurrency semaphore --
        semaphore = ConcurrencySemaphore()
        try:
            semaphore_acquired = await semaphore.acquire(
                raw_redis, current_user.user_id, job_id,
                tier_limits.max_concurrent_jobs,
            )
            if not semaphore_acquired:
                raise RateLimitException(
                    retry_after=CONCURRENCY_RETRY_AFTER_SECONDS,
                    limit=tier_limits.max_concurrent_jobs,
                    period="concurrent",
                    user_message=(
                        "Too many concurrent requests. "
                        "Please retry after {retry_after} seconds."
                    ),
                )
        except RateLimitException:
            raise
        except Exception as exc:
            raise UnavailableException(
                internal_message=(
                    f"Redis error in semaphore acquire: {exc}"
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
                # Release semaphore before re-raising.
                await _safe_release_semaphore(
                    semaphore, raw_redis, current_user.user_id, job_id
                )
                semaphore_acquired = False
                raise
            except Exception as exc:
                await _safe_release_semaphore(
                    semaphore, raw_redis, current_user.user_id, job_id
                )
                semaphore_acquired = False
                raise UnavailableException(
                    internal_message=(
                        f"Redis error in daily quota check: {exc}"
                    ),
                    retry_after=_RETRY_AFTER_SECONDS,
                )

        # -- Hand control to the route handler --
        request.state.job_id = job_id
        yield current_user

    finally:
        # Teardown: always release semaphore on request completion.
        if semaphore_acquired and raw_redis is not None:
            semaphore = ConcurrencySemaphore()
            await _safe_release_semaphore(
                semaphore, raw_redis, current_user.user_id, job_id
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _safe_release_semaphore(
    semaphore: ConcurrencySemaphore,
    redis,
    user_id: str,
    job_id: str,
) -> None:
    """Release a semaphore slot, swallowing errors to avoid masking the
    original exception during teardown."""
    try:
        await semaphore.release(redis, user_id, job_id)
    except Exception:
        logger.warning(
            "rate_limit: failed to release semaphore for "
            "user_id={}, job_id={}",
            user_id,
            job_id,
        )
