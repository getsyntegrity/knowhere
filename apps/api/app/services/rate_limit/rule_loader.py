"""
Startup rule loader for rate limit configuration.

Queries tier_limits and system_limits from the database and updates the
RateLimitConfig singleton. Called at startup and periodically by the
background sync task.
"""
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rate_limit.config import RateLimitConfig
from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits
from shared.models.database.system_limit import SystemLimit
from shared.models.database.tier_limit import TierLimit


async def _fetch_tier_map(db: AsyncSession) -> dict[str, TierLimits]:
    """Query tier_limits table and build a tier_name -> TierLimits mapping."""
    stmt = select(TierLimit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    tier_map: dict[str, TierLimits] = {}
    for row in rows:
        tier_map[row.tier_name] = TierLimits(
            rpm_limit=row.rpm_limit,
            max_concurrent_jobs=row.max_concurrent_jobs,
            daily_quota=row.daily_quota,
        )

    return tier_map


async def _fetch_system_rules(
    db: AsyncSession,
) -> list[SystemRpmRule]:
    """Query system_limits table ordered by priority ASC."""
    stmt = select(SystemLimit).order_by(SystemLimit.priority.asc())
    result = await db.execute(stmt)
    rows = result.scalars().all()

    system_rules: list[SystemRpmRule] = []
    for row in rows:
        system_rules.append(
            SystemRpmRule(
                method=row.method,
                api_pattern=row.api_pattern,
                priority=row.priority,
                rpm=row.rpm,
            )
        )

    return system_rules


async def load_rules(db: AsyncSession) -> None:
    """
    Load rate limit rules from DB and update in-memory config.

    Called once at application startup and periodically by the
    background sync task.
    """
    try:
        tier_map = await _fetch_tier_map(db)
        system_rules = await _fetch_system_rules(db)

        config = RateLimitConfig.get_instance()
        has_changes = config.update_rules(tier_map, system_rules)

        if has_changes:
            logger.info("Rate limit rules loaded successfully")
    except Exception as exc:
        logger.error(
            "Failed to load rate limit rules",
            error=str(exc),
        )
        raise
