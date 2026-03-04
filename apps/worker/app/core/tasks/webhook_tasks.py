"""
Webhook Celery Tasks

Provides Celery tasks for async webhook dispatch with DLX-based exponential backoff.
Uses RabbitMQ Dead Letter Exchanges for non-blocking retries.
"""
import asyncio

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException
from shared.core.logging import (
    LOG_CONTEXT_KEY,
    ContextPropagatingTask,
    log_context,
    get_log_context,
    LogEvent,
)

# Top-level imports (concern #3)
from shared.services.webhook import get_webhook_dispatcher
from shared.core.async_utils import run_async_task

# Retry configuration
MAX_ATTEMPTS = 6


celery_app = get_celery_app()


# Wait queue mapping for DLX-based retry
# Index corresponds to attempt number (0-indexed)
WAIT_QUEUES = [
    'webhook_wait_1m',   # After attempt 1: wait 1 minute
    'webhook_wait_10m',  # After attempt 2: wait 10 minutes
    'webhook_wait_30m',  # After attempt 3: wait 30 minutes
    'webhook_wait_2h',   # After attempt 4: wait 2 hours
    'webhook_wait_6h',   # After attempt 5: wait 6 hours
]

# Wait durations in seconds (must match queue TTLs)
WAIT_DURATIONS_SECONDS = [
    60,      # 1m
    600,     # 10m
    1800,    # 30m
    7200,    # 2h
    21600,   # 6h
]

# Dead letter queue for permanent failures
DEAD_QUEUE = 'webhook_dead'


class WebhookDispatchTask(ContextPropagatingTask):
    """Base task class for webhook dispatch with proper error handling."""

    def on_success(self, retval, task_id, args, kwargs):
        """Log successful webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        context = get_log_context()
        logger.bind(
            event=LogEvent.WORKER_TASK_COMPLETE.value,
            task_id=task_id,
            event_id=event_id,
            **context
        ).info("Webhook dispatch task completed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log failed webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        context = get_log_context()

        logger.bind(
            event=LogEvent.WORKER_TASK_FAILURE.value,
            task_id=task_id,
            event_id=event_id,
            **context
        ).error(f"Webhook dispatch task failed permanently: {exc}")

        # Update status in DB (last resort status update)
        if event_id != "unknown":
            try:
                dispatcher = get_webhook_dispatcher()
                run_async_task(dispatcher.mark_event_failed(event_id))
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
            jitter_applied=jitter_applied
        ).info("Webhook dispatch task started")

        # Non-Blocking Jitter Implementation:
        # If this is a retry (attempt > 1) and jitter hasn't been applied yet:
        # 1. Calculate random jitter delay (e.g., 5s)
        # 2. Reschedule THIS task with countdown=jitter
        # 3. Mark jitter_applied=True in the rescheduled task
        # 4. Return immediately (freeing the worker process)
        if attempt > 1 and not jitter_applied:
            import random

            # Attempt 2 (1m wait): 0-6s jitter
            # Attempt 3+ (10m+ wait): 0-30s jitter
            max_jitter = 30 if attempt > 2 else 6

            jitter_seconds = random.uniform(0, max_jitter)
            if jitter_seconds > 0.1:
                logger.info(f"Scheduling non-blocking jitter: {jitter_seconds:.2f}s (attempt {attempt})")
                # Use retry to reschedule with countdown.
                # We pass max_retries=None to avoid Celery's internal retry limit interfering with our business logic limit.
                try:
                    context_payload = ContextPropagatingTask.sanitize_log_context(get_log_context())
                    self.retry(
                        countdown=jitter_seconds,
                        args=[event_id, attempt],
                        kwargs={
                            "jitter_applied": True,
                            LOG_CONTEXT_KEY: context_payload,
                        },
                        max_retries=None
                    )
                except Exception:
                    # self.retry raises Retry exception to stop execution, which is expected behavior
                    raise
                return False

        try:
            # Jitter is handled above (non-blocking), so we just dispatch directly here
            # Use run_async_task to reuse event loop and connections
            result = run_async_task(_dispatch_async(event_id))

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
            # Unexpected error
            raise exc

async def _dispatch_async(event_id: str) -> bool:
    """
    Async wrapper for dispatcher.dispatch().
    """
    dispatcher = get_webhook_dispatcher()
    return await dispatcher.dispatch(event_id)


def _schedule_retry(task_instance: Task, event_id: str, current_attempt: int) -> None:
    """
    Schedule retry by publishing to the appropriate DLX wait queue.
    
    If DLX publishing fails (Broker issue), falls back to Celery's native self.retry()
    to hold the task in the current worker/queue until recovery.
    """
    next_attempt = current_attempt + 1
    
    context_payload = ContextPropagatingTask.sanitize_log_context(get_log_context())

    if next_attempt > MAX_ATTEMPTS:
        # All retries exhausted - send to dead letter queue
        logger.error(
            f"Webhook exhausted all retries: event_id={event_id}, "
            f"attempts={current_attempt}"
        )
        try:
            # Mark as failed in DB before sending to DLQ (so UI shows failed)
            dispatcher = get_webhook_dispatcher()
            run_async_task(dispatcher.mark_event_failed(event_id))
            
            dispatch_webhook_task.apply_async(
                args=[event_id, next_attempt],
                kwargs={LOG_CONTEXT_KEY: context_payload},
                queue=DEAD_QUEUE,
            )
        except Exception as exc:
            logger.error(f"Failed to send to Dead Letter Queue: {exc}")
            # If we can't even send to dead queue, we retry locally to avoid data loss
            task_instance.retry(exc=exc, countdown=60, max_retries=None)
        return
    
    # Get appropriate wait queue (0-indexed)
    queue_index = min(current_attempt - 1, len(WAIT_QUEUES) - 1)
    wait_queue = WAIT_QUEUES[queue_index]
    
    logger.info(
        f"Scheduling webhook retry via DLX: event_id={event_id}, "
        f"attempt={current_attempt}, next_attempt={next_attempt}, queue={wait_queue}"
    )
    
    # Publish NEW message to wait queue
    try:
        dispatch_webhook_task.apply_async(
            args=[event_id, next_attempt],
            kwargs={LOG_CONTEXT_KEY: context_payload},
            queue=wait_queue,
        )
    except Exception as exc:
        logger.error(
            f"Failed to schedule DLX retry, falling back to Celery countdown: "
            f"event_id={event_id}, error={exc}"
        )
        # Fallback: Re-raise as Celery retry exception to hold in queue
        task_instance.retry(exc=exc, countdown=60, max_retries=None)


@celery_app.task(name="app.core.tasks.webhook_tasks.recover_orphaned_webhooks")
def recover_orphaned_webhooks() -> dict:
    """
    Periodic task to recover orphaned webhook events.
    
    Finds webhook events that were persisted to the database but never
    published to the message queue (due to RabbitMQ failure, network issues, etc.)
    and republishes them.
    
    This ensures the "eventual delivery" guarantee of the Transactional Outbox pattern.
    
    Runs every 5 minutes via Celery Beat.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from shared.core.database import get_db_context
    from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
    
    logger.info("Starting orphaned webhook recovery job")
    
    age_minutes = 5
    cutoff_time = datetime.utcnow() - timedelta(minutes=age_minutes)
    recovered = 0
    
    async def _recover():
        nonlocal recovered
        async with get_db_context() as db:
            # Find orphaned events (PENDING status, created more than 5 minutes ago, attempts=0)
            stmt = select(WebhookEvent).where(
                WebhookEvent.status == WebhookEventStatus.PENDING,
                WebhookEvent.attempts == 0,
                WebhookEvent.created_at < cutoff_time
            ).limit(100)
            
            result = await db.execute(stmt)
            orphaned_events = result.scalars().all()
            
            logger.info(f"Found {len(orphaned_events)} orphaned webhook events")
            
            for event in orphaned_events:
                try:
                    # Republish to queue
                    dispatch_webhook_task.apply_async(
                        args=[event.id],
                        queue='webhook_work',
                    )
                    recovered += 1
                    logger.info(f"Recovered orphaned webhook event: {event.id}")
                except Exception as e:
                    logger.error(f"Error recovering webhook event {event.id}: {e}")
    
    try:
        run_async_task(_recover())
        
        if recovered > 0:
            logger.info(f"Successfully recovered {recovered} orphaned webhook events")
        else:
            logger.debug("No orphaned webhook events found")
            
        return {"status": "success", "recovered": recovered}
        
    except Exception as e:
        logger.error(f"Orphaned webhook recovery job failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
