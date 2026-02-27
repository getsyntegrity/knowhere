"""
Redis Pub/Sub listener for rate limit rule hot-swap.

Runs as a background asyncio task. When a message arrives on the
configured channel, it fetches the latest compiled snapshot from Redis
and atomically updates the RateLimitConfig singleton.

Uses ``get_message(timeout=300)`` polling -- NOT the blocking
``listen()`` iterator -- so the task can be cancelled cleanly.
"""
import asyncio
import json
from typing import Optional

from loguru import logger
from shared.services.redis.redis_service import RedisService

from app.services.rate_limit.config import RateLimitConfig
from app.services.rate_limit.data_structures import SystemRpmRule, TierLimits
from .rule_loader import ACTIVE_RULES_KEY, RATE_LIMIT_UPDATES_CHANNEL


class RateLimitPubSubListener:
    """Background listener that hot-swaps rate limit rules via Pub/Sub."""

    def __init__(self, redis_service: RedisService) -> None:
        self._redis_service: RedisService = redis_service
        self._task: Optional[asyncio.Task] = None
        self._is_running: bool = False

    async def start(self) -> None:
        """Start the background listener task."""
        if self._is_running:
            logger.warning("Rate limit Pub/Sub listener is already running")
            return

        self._is_running = True
        self._task = asyncio.create_task(
            self._listen_loop(),
            name="rate_limit_pubsub_listener",
        )
        logger.info(
            "Rate limit Pub/Sub listener started",
            channel=RATE_LIMIT_UPDATES_CHANNEL,
        )

    async def stop(self) -> None:
        """Gracefully stop the background listener task."""
        self._is_running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Rate limit Pub/Sub listener stopped")

    async def _listen_loop(self) -> None:
        """
        Core polling loop.

        Subscribes to the channel and polls with ``get_message(timeout=300)``.
        On each valid message, fetches the latest snapshot from Redis and
        updates the in-memory config.
        """
        pubsub = None
        try:
            client = await self._redis_service._get_client()
            pubsub = client.pubsub()
            await pubsub.subscribe(RATE_LIMIT_UPDATES_CHANNEL)
            logger.info(
                "Subscribed to Pub/Sub channel",
                channel=RATE_LIMIT_UPDATES_CHANNEL,
            )

            while self._is_running:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=300,
                    )
                    if message is not None:
                        await self._handle_update(message)
                    else:
                        await self._refresh_from_snapshot(source="poll")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "Error in Pub/Sub poll loop",
                        error=str(exc),
                    )
                    # Back off before retrying to avoid tight error loops
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.debug("Pub/Sub listener task cancelled")
        except Exception as exc:
            logger.error(
                "Fatal error in Pub/Sub listener",
                error=str(exc),
            )
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(RATE_LIMIT_UPDATES_CHANNEL)
                    await pubsub.close()
                except Exception:
                    pass

    async def _handle_update(self, message: dict) -> None:
        """Fetch the latest snapshot from Redis and swap in-memory config."""
        logger.info(
            "Received rate limit rule update notification",
            message_type=message.get("type"),
        )
        await self._refresh_from_snapshot(source="pubsub")

    async def _refresh_from_snapshot(self, source: str) -> None:
        """Fetch latest snapshot and hot-swap in-memory rate-limit rules."""
        try:
            snapshot = await self._redis_service.get(ACTIVE_RULES_KEY)
            if snapshot is None:
                logger.warning(
                    "No active rules snapshot found in Redis"
                )
                return

            # snapshot is already deserialized by RedisService.get()
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)

            raw_tier_map = snapshot.get("tier_map", {})
            raw_system_rules = snapshot.get("system_rules", [])

            # Reconstruct typed objects from the JSON snapshot
            tier_map: dict[str, TierLimits] = {
                k: TierLimits(**v) for k, v in raw_tier_map.items()
            }
            system_rules: list[SystemRpmRule] = [
                SystemRpmRule(**r) for r in raw_system_rules
            ]

            config = RateLimitConfig.get_instance()
            config.update_rules(tier_map, system_rules)
            logger.info(
                "In-memory rate limit config hot-swapped via Pub/Sub",
                tier_count=len(tier_map),
                rule_count=len(system_rules),
                source=source,
            )
        except Exception as exc:
            logger.error(
                "Failed to handle rate limit rule update",
                error=str(exc),
            )
