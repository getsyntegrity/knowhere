"""
Webhook-related Celery tasks.

Only the orphan recovery beat task remains here. Webhook delivery is always
published through QStash, which owns retries and callback handling.
"""

from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.logging import (
    LogEvent,
)
from shared.services.redis.periodic_task_lock import periodic_task_lock

# Matches the beat_schedule period in celery_app.py
_WEBHOOK_RECOVERY_PERIOD_SECONDS = 1800

celery_app = get_celery_app()


@celery_app.task(name="app.core.tasks.webhook_tasks.recover_orphaned_webhooks")
def recover_orphaned_webhooks() -> dict:
    """Periodic task to recover orphaned webhook events.

    Finds PENDING events with attempts=0 older than 5 minutes and republishes
    them via QStash.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select as sa_select

    from shared.core.database_sync import get_sync_db_context
    from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
    from shared.services.webhook.qstash_publisher import get_qstash_webhook_publisher

    with periodic_task_lock(
        "app.core.tasks.webhook_tasks.recover_orphaned_webhooks",
        period_seconds=_WEBHOOK_RECOVERY_PERIOD_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "duplicate Beat firing"}

        logger.debug("Starting orphaned webhook recovery job")

        age_minutes = 5
        cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=age_minutes
        )
        recovered = 0
        publisher = get_qstash_webhook_publisher()

        try:
            with get_sync_db_context() as db:
                stmt = (
                    sa_select(WebhookEvent)
                    .where(
                        WebhookEvent.status == WebhookEventStatus.PENDING,
                        WebhookEvent.attempts == 0,
                        WebhookEvent.created_at < cutoff_time,
                    )
                    .limit(100)
                )

                result = db.execute(stmt)
                orphaned_events = result.scalars().all()

                for event in orphaned_events:
                    try:
                        message_id = publisher.publish_event(event.id)
                        if not message_id:
                            logger.warning(
                                f"Orphaned webhook republish returned no message_id: {event.id}"
                            )
                            continue
                        recovered += 1
                        logger.info(
                            f"Recovered orphaned webhook event: {event.id}, "
                            f"message_id={message_id}"
                        )
                    except Exception as e:
                        logger.error(f"Error recovering webhook event {event.id}: {e}")

            if recovered > 0:
                logger.bind(event=LogEvent.WORKER_TASK_COMPLETE.value).info(
                    f"Recovered {recovered} orphaned webhook events via QStash"
                )
            else:
                logger.debug("No orphaned webhook events found")

            return {"status": "success", "recovered": recovered, "provider": "qstash"}

        except Exception as e:
            logger.error(f"Orphaned webhook recovery job failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
