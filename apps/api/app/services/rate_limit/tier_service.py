"""
Tier service.
Determines and refreshes a user's tier based on lifetime payment history.
"""
import logging
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.payment_record import PaymentRecord
from shared.models.database.tier_limit import TierLimit
from shared.models.database.user_balance import UserBalance
from app.services.rate_limit.config import RateLimitConfig
from app.services.rate_limit.data_structures import TierLimits

logger = logging.getLogger(__name__)

_DEFAULT_TIER: str = "free"


class TierService:
    """Manages user tier assignment based on lifetime spend."""

    @staticmethod
    async def refresh_tier(user_id: str, session: AsyncSession) -> str:
        """Called on payment success.

        1. Sum amount_cents from payment_records WHERE status='succeeded'.
        2. Query tier_limits ordered by min_lifetime_amount_cents DESC.
        3. Pick the first tier where total >= threshold.
        4. Update user_balances.user_tier.
        5. Return the new tier name.
        """
        # Step 1: sum lifetime successful payments
        stmt = (
            select(func.coalesce(func.sum(PaymentRecord.amount_cents), 0))
            .where(PaymentRecord.user_id == user_id)
            .where(PaymentRecord.status == "succeeded")
        )
        result = await session.execute(stmt)
        total_amount_cents: int = int(result.scalar_one())

        # Step 2 + 3: query tiers from DB, find highest qualifying
        tier_stmt = select(TierLimit).order_by(
            TierLimit.min_lifetime_amount_cents.desc()
        )
        tier_result = await session.execute(tier_stmt)
        tiers = tier_result.scalars().all()

        new_tier = _DEFAULT_TIER
        for tier in tiers:
            if total_amount_cents >= tier.min_lifetime_amount_cents:
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
            "Tier refreshed: user_id=%s total_cents=%d new_tier=%s",
            user_id,
            total_amount_cents,
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
