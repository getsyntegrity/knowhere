"""
Webhook Celery Tasks.

After the RabbitMQ → Redis + QStash migration:
- dispatch_webhook_task is kept as a legacy fallback (WEBHOOK_DELIVERY_PROVIDER=celery)
- recover_orphaned_webhooks routes to QStash or Celery based on the feature flag
- DLX wait queues have been removed; retry is handled by QStash or Celery countdown
"""

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException
from shared.services.redis.periodic_task_lock import periodic_task_lock
from shared.core.logging import (
    log_context,
    LogEvent,
)

# Retry configuration (legacy Celery path)
MAX_ATTEMPTS = 6

# Retry delays in seconds for Celery countdown-based retry (replaces DLX)
RETRY_DELAYS = [60, 600, 1800, 7200, 21600]  # 1m, 10m, 30m, 2h, 6h

# Matches the beat_schedule period in celery_app.py
_WEBHOOK_RECOVERY_PERIOD_SECONDS = 1800

celery_app = get_celery_app()


class WebhookDispatchTask(Task):
    """Base task class for legacy webhook dispatch (Celery path)."""

    def on_success(self, retval, task_id, args, kwargs):
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.bind(
            event=LogEvent.WORKER_TASK_COMPLETE.value,
            task_id=task_id,
            event_id=event_id,
        ).info("Webhook dispatch task completed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.bind(
            event=LogEvent.WORKER_TASK_FAILURE.value,
            task_id=task_id,
            event_id=event_id,
        ).error(f"Webhook dispatch task failed permanently: {exc}")

        if event_id != "unknown":
            try:
                from app.services.webhook.sync_dispatcher import get_sync_webhook_dispatcher
                dispatcher = get_sync_webhook_dispatcher()
                dispatcher.mark_event_failed(event_id)
            except Exception as e:
                logger.error(f"Failed to update webhook status in on_failure: {e}")


@celery_app.task(
    bind=True,
    base=WebhookDispatchTask,
    name="app.core.tasks.webhook_tasks.dispatch_webhook_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_webhook_task(self, event_id: str, attempt: int = 1) -> bool:
    """Dispatch a webhook event (legacy Celery path).

    Uses countdown-based retry instead of DLX wait queues.
    Only active when WEBHOOK_DELIVERY_PROVIDER=celery.
    """
    with log_context(task_id=self.request.id, event_id=event_id):
        logger.bind(
            event=LogEvent.WORKER_TASK_START.value,
            attempt=attempt,
            max_attempts=MAX_ATTEMPTS,
        ).info("Webhook dispatch task started")

        try:
            from app.services.webhook.sync_dispatcher import get_sync_webhook_dispatcher
            dispatcher = get_sync_webhook_dispatcher()
            result = dispatcher.dispatch(event_id)

            logger.bind(event=LogEvent.WORKER_TASK_COMPLETE.value).info("Webhook dispatched successfully")
            return result

        except WebhookDeliveryException as exc:
            if not exc.retryable:
                logger.warning(
                    f"Webhook permanent failure: event_id={event_id}, "
                    f"status={exc.response_status_code}"
                )
                return False

            # Retry via Celery countdown (replaces DLX)
            _schedule_retry(self, event_id, attempt)
            return False

        except Exception as exc:
            raise exc


def _schedule_retry(task_instance: Task, event_id: str, current_attempt: int) -> None:
    """Schedule retry via Celery countdown (replaces DLX wait queues)."""
    next_attempt = current_attempt + 1

    if next_attempt > MAX_ATTEMPTS:
        logger.error(
            f"Webhook exhausted all retries: event_id={event_id}, "
            f"attempts={current_attempt}"
        )
        try:
            from app.services.webhook.sync_dispatcher import get_sync_webhook_dispatcher
            dispatcher = get_sync_webhook_dispatcher()
            dispatcher.mark_event_failed(event_id)
        except Exception as exc:
            logger.error(f"Failed to mark webhook as failed: {exc}")
        return

    delay_index = min(current_attempt - 1, len(RETRY_DELAYS) - 1)
    countdown = RETRY_DELAYS[delay_index]

    logger.info(
        f"Scheduling webhook retry: event_id={event_id}, "
        f"attempt={current_attempt}, next_attempt={next_attempt}, "
        f"countdown={countdown}s"
    )

    try:
        dispatch_webhook_task.apply_async(
            args=[event_id, next_attempt],
            countdown=countdown,
        )
    except Exception as exc:
        logger.error(f"Failed to schedule retry: event_id={event_id}, error={exc}")
        task_instance.retry(exc=exc, countdown=60, max_retries=None)


@celery_app.task(name="app.core.tasks.webhook_tasks.recover_orphaned_webhooks")
def recover_orphaned_webhooks() -> dict:
    """Periodic task to recover orphaned webhook events.

    Finds PENDING events with attempts=0 older than 5 minutes and
    re-publishes them via the configured delivery provider (QStash or Celery).
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select as sa_select
    from shared.core.config import app_config
    from shared.core.database_sync import get_sync_db_context
    from shared.models.database.webhook import WebhookEvent, WebhookEventStatus

    with periodic_task_lock(
        "app.core.tasks.webhook_tasks.recover_orphaned_webhooks",
        period_seconds=_WEBHOOK_RECOVERY_PERIOD_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "duplicate Beat firing"}

        logger.debug("Starting orphaned webhook recovery job")

        age_minutes = 5
        cutoff_time = datetime.utcnow() - timedelta(minutes=age_minutes)
        recovered = 0
        provider = app_config.WEBHOOK_DELIVERY_PROVIDER

        try:
            with get_sync_db_context() as db:
                stmt = sa_select(WebhookEvent).where(
                    WebhookEvent.status == WebhookEventStatus.PENDING,
                    WebhookEvent.attempts == 0,
                    WebhookEvent.created_at < cutoff_time,
                ).limit(100)

                result = db.execute(stmt)
                orphaned_events = result.scalars().all()

                for event in orphaned_events:
                    try:
                        if provider == "qstash" and app_config.is_qstash_enabled:
                            from shared.services.webhook.qstash_publisher import (
                                get_qstash_webhook_publisher,
                            )
                            publisher = get_qstash_webhook_publisher()
                            publisher.publish_event(event.id)
                        else:
                            dispatch_webhook_task.apply_async(
                                args=[event.id],
                            )
                        recovered += 1
                        logger.info(f"Recovered orphaned webhook event: {event.id}")
                    except Exception as e:
                        logger.error(f"Error recovering webhook event {event.id}: {e}")

            if recovered > 0:
                logger.info(f"Recovered {recovered} orphaned webhook events via {provider}")
            else:
                logger.debug("No orphaned webhook events found")

            return {"status": "success", "recovered": recovered, "provider": provider}

        except Exception as e:
            logger.error(f"Orphaned webhook recovery job failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
