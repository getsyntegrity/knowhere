"""
Tier service.
Determines and refreshes a user's tier based on lifetime payment history.
"""
from typing import Optional

from loguru import logger
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.payment_record import PaymentRecord
from shared.models.database.tier_limit import TierLimit
from shared.models.database.user_balance import UserBalance
from app.services.rate_limit.config import RateLimitConfig
from app.services.rate_limit.data_structures import TierLimits

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
        try:
            stmt_update = (
                update(UserBalance)
                .where(UserBalance.user_id == user_id)
                .values(user_tier=new_tier)
            )
            await session.execute(stmt_update)
            await session.commit()
        except Exception:
            logger.warning(
                "Failed to persist tier to user_balances, "
                "user_id=%s tier=%s",
                user_id,
                new_tier,
            )
            await session.rollback()

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
