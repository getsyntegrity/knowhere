"""
Startup rule loader for rate limit configuration.

Queries tier_limits and system_limits from the database, updates the
RateLimitConfig singleton, and writes a compiled JSON snapshot to Redis
for other services to consume.
"""
from dataclasses import asdict

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rate_limit.config import RateLimitConfig, RATE_LIMIT_KEY_PREFIX
from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits
from shared.models.database.system_limit import SystemLimit
from shared.models.database.tier_limit import TierLimit
from shared.services.redis.redis_service import RedisService

# Redis key for the compiled active rules snapshot
ACTIVE_RULES_KEY = f"{RATE_LIMIT_KEY_PREFIX}rate_limit:active_rules"
RATE_LIMIT_UPDATES_CHANNEL = f"{RATE_LIMIT_KEY_PREFIX}rate_limit:updates"


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

    logger.info(
        "Fetched tier limits from DB",
        tier_count=len(tier_map),
        tiers=list(tier_map.keys()),
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

    logger.info(
        "Fetched system limits from DB",
        rule_count=len(system_rules),
    )
    return system_rules


async def _publish_snapshot_to_redis(
    redis_service: RedisService,
    tier_map: dict[str, TierLimits],
    system_rules: list[SystemRpmRule],
) -> None:
    """Compile tier_map + system_rules to JSON and SET to Redis."""
    snapshot = {
        "tier_map": {k: asdict(v) for k, v in tier_map.items()},
        "system_rules": [asdict(r) for r in system_rules],
    }
    await redis_service.set(
        ACTIVE_RULES_KEY,
        snapshot,
        ttl=86400,  # 24 hours fallback TTL
    )
    raw_client = await redis_service._get_client()
    await raw_client.publish(
        RATE_LIMIT_UPDATES_CHANNEL,
        '{"event":"rules_updated"}',
    )
    logger.info("Published rate limit snapshot to Redis")


async def load_rules(
    db: AsyncSession,
    redis_service: RedisService,
) -> None:
    """
    Load rate limit rules from DB, update in-memory config, and
    publish a compiled snapshot to Redis.

    Called once at application startup and can be re-invoked by the
    Pub/Sub listener when rules change at runtime.
    """
    try:
        tier_map = await _fetch_tier_map(db)
        system_rules = await _fetch_system_rules(db)

        # Atomically swap in-memory config on the RateLimitConfig singleton
        config = RateLimitConfig.get_instance()
        config.update_rules(tier_map, system_rules)

        # Publish compiled snapshot to Redis
        await _publish_snapshot_to_redis(
            redis_service, tier_map, system_rules
        )

        logger.info("Rate limit rules loaded successfully")
    except Exception as exc:
        logger.error(
            "Failed to load rate limit rules",
            error=str(exc),
        )
        raise
