"""
Webhook Celery Tasks

Provides Celery tasks for webhook dispatch with DLX-based exponential backoff.
Uses RabbitMQ Dead Letter Exchanges for non-blocking retries.

Sync implementation for gevent worker pool.
"""

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException
from shared.core.logging import (
    log_context,
    LogEvent,
)

from app.services.webhook.sync_dispatcher import get_sync_webhook_dispatcher

# Retry configuration
MAX_ATTEMPTS = 6

celery_app = get_celery_app()

# Wait queue mapping for DLX-based retry
# Index corresponds to attempt number (0-indexed)
WAIT_QUEUES = [
    'webhook_wait_1m',
    'webhook_wait_10m',
    'webhook_wait_30m',
    'webhook_wait_2h',
    'webhook_wait_6h',
]

# Dead letter queue for permanent failures
DEAD_QUEUE = 'webhook_dead'


class WebhookDispatchTask(Task):
    """Base task class for webhook dispatch with proper error handling."""

    def on_success(self, retval, task_id, args, kwargs):
        """Log successful webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.bind(
            event=LogEvent.WORKER_TASK_COMPLETE.value,
            task_id=task_id,
            event_id=event_id,
        ).info("Webhook dispatch task completed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log failed webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")

        logger.bind(
            event=LogEvent.WORKER_TASK_FAILURE.value,
            task_id=task_id,
            event_id=event_id,
        ).error(f"Webhook dispatch task failed permanently: {exc}")

        # Update status in DB (last resort status update)
        if event_id != "unknown":
            try:
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
def dispatch_webhook_task(self, event_id: str, attempt: int = 1, jitter_applied: bool = False) -> bool:
    """
    Dispatch a webhook event via Celery with DLX-based retry.

    Args:
        event_id: The WebhookEvent ID to dispatch
        attempt: Current attempt number (1-indexed, default=1)
        jitter_applied: Whether jitter has already been applied for this attempt

    Returns:
        True if successfully dispatched or terminal
    """
    with log_context(task_id=self.request.id, event_id=event_id):
        logger.bind(
            event=LogEvent.WORKER_TASK_START.value,
            attempt=attempt,
            max_attempts=MAX_ATTEMPTS,
            jitter_applied=jitter_applied,
        ).info("Webhook dispatch task started")

        # Non-Blocking Jitter Implementation:
        # If this is a retry (attempt > 1) and jitter hasn't been applied yet:
        # 1. Calculate random jitter delay
        # 2. Reschedule THIS task with countdown=jitter
        # 3. Mark jitter_applied=True in the rescheduled task
        # 4. Return immediately (freeing the worker)
        if attempt > 1 and not jitter_applied:
            import random

            # Attempt 2 (1m wait): 0-6s jitter
            # Attempt 3+ (10m+ wait): 0-30s jitter
            max_jitter = 30 if attempt > 2 else 6
            jitter_seconds = random.uniform(0, max_jitter)
            if jitter_seconds > 0.1:
                logger.info(f"Scheduling non-blocking jitter: {jitter_seconds:.2f}s (attempt {attempt})")
                # Use retry to reschedule with countdown.
                # max_retries=None avoids Celery's internal retry limit
                # interfering with our business logic limit.
                try:
                    self.retry(
                        countdown=jitter_seconds,
                        args=[event_id, attempt],
                        kwargs={"jitter_applied": True},
                        max_retries=None,
                    )
                except Exception:
                    # self.retry raises Retry exception to stop execution,
                    # which is expected behavior
                    raise
                return False

        try:
            dispatcher = get_sync_webhook_dispatcher()
            result = dispatcher.dispatch(event_id)

            logger.bind(event=LogEvent.WORKER_TASK_COMPLETE.value).info("Webhook dispatched successfully")
            return result

        except WebhookDeliveryException as exc:
            # Check if error is retryable (set by dispatcher)
            if not exc.retryable:
                # Permanent failure - do not retry
                logger.warning(
                    f"Webhook permanent failure (not retrying): event_id={event_id}, "
                    f"status={exc.response_status_code}"
                )
                return False

            # Retryable failure - schedule retry via DLX
            _schedule_retry(self, event_id, attempt)
            return False  # Task completes, retry is a new message

        except Exception as exc:
            raise exc

def _schedule_retry(task_instance: Task, event_id: str, current_attempt: int) -> None:
    """
    Schedule retry by publishing to the appropriate DLX wait queue.

    If DLX publishing fails (broker issue), falls back to Celery's native
    self.retry() to hold the task in the current worker/queue until recovery.
    """
    next_attempt = current_attempt + 1

    if next_attempt > MAX_ATTEMPTS:
        # All retries exhausted - send to dead letter queue
        logger.error(
            f"Webhook exhausted all retries: event_id={event_id}, "
            f"attempts={current_attempt}"
        )
        try:
            # Mark as permanently failed in DB, then archive to dead queue
            dispatcher = get_sync_webhook_dispatcher()
            dispatcher.mark_event_failed(event_id)

            dispatch_webhook_task.apply_async(
                args=[event_id, next_attempt],
                queue=DEAD_QUEUE,
            )
        except Exception as exc:
            logger.error(f"Failed to send to Dead Letter Queue: {exc}")
            task_instance.retry(exc=exc, countdown=60, max_retries=None)
        return

    # Map attempt number to wait queue.
    # Clamp to last queue if attempt exceeds queue count.
    queue_index = min(current_attempt - 1, len(WAIT_QUEUES) - 1)
    wait_queue = WAIT_QUEUES[queue_index]

    logger.info(
        f"Scheduling webhook retry via DLX: event_id={event_id}, "
        f"attempt={current_attempt}, next_attempt={next_attempt}, queue={wait_queue}"
    )

    try:
        dispatch_webhook_task.apply_async(
            args=[event_id, next_attempt],
            queue=wait_queue,
        )
    except Exception as exc:
        logger.error(
            f"Failed to schedule DLX retry, falling back to Celery countdown: "
            f"event_id={event_id}, error={exc}"
        )
        task_instance.retry(exc=exc, countdown=60, max_retries=None)


@celery_app.task(name="app.core.tasks.webhook_tasks.recover_orphaned_webhooks")
def recover_orphaned_webhooks() -> dict:
    """
    Periodic task to recover orphaned webhook events.

    Finds webhook events that were persisted to the database but never
    published to the message queue and republishes them.

    This handles the edge case where the DB commit succeeds but the
    subsequent Celery apply_async call fails (e.g., broker down).
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select as sa_select
    from shared.core.database_sync import get_sync_db_context
    from shared.models.database.webhook import WebhookEvent, WebhookEventStatus

    logger.debug("Starting orphaned webhook recovery job")

    age_minutes = 5
    cutoff_time = datetime.utcnow() - timedelta(minutes=age_minutes)
    recovered = 0

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
                    dispatch_webhook_task.apply_async(
                        args=[event.id],
                        queue="webhook_work",
                    )
                    recovered += 1
                    logger.info(f"Recovered orphaned webhook event: {event.id}")
                except Exception as e:
                    logger.error(f"Error recovering webhook event {event.id}: {e}")

        if recovered > 0:
            logger.info(f"Successfully recovered {recovered} orphaned webhook events")
        else:
            logger.debug("No orphaned webhook events found")

        return {"status": "success", "recovered": recovered}

    except Exception as e:
        logger.error(f"Orphaned webhook recovery job failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
