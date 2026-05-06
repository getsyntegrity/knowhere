"""
Tier service.
Determines and refreshes a user's tier based on lifetime payment history.
"""

from typing import Optional

from app.services.rate_limit.config import RateLimitConfig
from app.services.rate_limit.data_structures import TierLimits
from app.services.rate_limit.identity_cache import identity_cache
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.config import redis_pool_manager
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.tier_limit import TierLimit
from shared.models.database.user_balance import UserBalance

_DEFAULT_TIER: str = "free"


class TierService:
    """Manages user tier assignment based on lifetime spend."""

    @staticmethod
    async def refresh_tier(user_id: str, session: AsyncSession) -> str:
        """Called on payment success.

        1. Sum credits_amount (micro-dollars) from payment_records WHERE status='succeeded'.
        2. Query tier_limits ordered by min_lifetime_amount_micro DESC.
        3. Pick the first tier where total >= threshold.
        4. Update user_balances.user_tier.
        5. Return the new tier name.
        """
        # Step 1: sum lifetime successful payments in micro-dollars
        stmt = (
            select(func.coalesce(func.sum(PaymentRecord.credits_amount), 0))
            .where(PaymentRecord.user_id == user_id)
            .where(PaymentRecord.status == "succeeded")
        )
        result = await session.execute(stmt)
        total_amount_micro: int = int(result.scalar_one() or 0)

        # Step 2 + 3: query tiers from DB, find highest qualifying
        tier_stmt = select(TierLimit).order_by(
            TierLimit.min_lifetime_amount_micro.desc()
        )
        tier_result = await session.execute(tier_stmt)
        tiers = tier_result.scalars().all()

        new_tier = _DEFAULT_TIER
        for tier in tiers:
            if total_amount_micro >= tier.min_lifetime_amount_micro:
                new_tier = tier.tier_name
                break

        # Step 4: persist the tier on user_balances
        # NOTE: caller is responsible for commit/rollback.
        stmt_update = (
            update(UserBalance)
            .where(UserBalance.user_id == user_id)
            .values(user_tier=new_tier)
        )
        await session.execute(stmt_update)
        await TierService._invalidate_user_tier_cache(user_id)

        logger.info(
            "Tier refreshed: user_id=%s total_micro=%d new_tier=%s",
            user_id,
            total_amount_micro,
            new_tier,
        )
        return new_tier

    @staticmethod
    def get_limits(user_tier: str) -> Optional[TierLimits]:
        """Read from in-memory tier_map via RateLimitConfig.

        Zero Redis calls.
        """
        config = RateLimitConfig.get_instance()
        return config.tier_map.get(user_tier)

    @staticmethod
    async def _invalidate_user_tier_cache(user_id: str) -> None:
        """Invalidate cached tier data without touching API-key auth cache."""
        try:
            await identity_cache.invalidate_user(
                redis_pool_manager.get_redis_service(),
                user_id,
            )
        except Exception:
            logger.warning(
                "Tier refresh cache invalidation failed for user_id={}",
                user_id,
            )
