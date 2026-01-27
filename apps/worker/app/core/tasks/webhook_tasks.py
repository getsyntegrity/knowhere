"""
Webhook Celery Tasks

Provides Celery tasks for async webhook dispatch with DLX-based exponential backoff.
Uses RabbitMQ Dead Letter Exchanges for non-blocking retries.
"""
import asyncio
from typing import Optional

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException

# Top-level imports (concern #3)
from app.services.webhook import MAX_ATTEMPTS
from app.services.webhook.dispatcher import get_webhook_dispatcher


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

# Dead letter queue for permanent failures
DEAD_QUEUE = 'webhook_dead'


class WebhookDispatchTask(Task):
    """Base task class for webhook dispatch with proper error handling."""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Log successful webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.info(f"Webhook dispatch task completed: task_id={task_id}, event_id={event_id}")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log failed webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.error(
            f"Webhook dispatch task failed permanently: task_id={task_id}, "
            f"event_id={event_id}, error={exc}"
        )


@celery_app.task(
    bind=True,
    base=WebhookDispatchTask,
    name="app.core.tasks.webhook_tasks.dispatch_webhook_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_webhook_task(self, event_id: str, attempt: int = 1) -> bool:
    """
    Dispatch a webhook event via Celery with DLX-based retry.
    
    Uses asyncio.run() for proper event loop management.
    Only retries on transient errors.
    
    Args:
        event_id: The WebhookEvent ID to dispatch
        attempt: Current attempt number (1-indexed, default=1)
        
    Returns:
        True if successfully dispatched or terminal
    """
    logger.info(
        f"Webhook dispatch task started: event_id={event_id}, "
        f"attempt={attempt}/{MAX_ATTEMPTS}"
    )
    
    try:
        result = asyncio.run(_dispatch_async(event_id))
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
        _schedule_retry(event_id, attempt)
        return False  # Task completes, retry is a new message
        
    except Exception as exc:
        # Unexpected error - log and retry (could be transient)
        logger.error(
            f"Webhook dispatch unexpected error: event_id={event_id}, "
            f"error={type(exc).__name__}: {exc}"
        )
        _schedule_retry(event_id, attempt)
        return False


async def _dispatch_async(event_id: str) -> bool:
    """
    Async wrapper for dispatcher.dispatch().
    
    Separated to keep the sync task clean.
    """
    dispatcher = get_webhook_dispatcher()
    return await dispatcher.dispatch(event_id)


def _schedule_retry(event_id: str, current_attempt: int) -> None:
    """
    Schedule retry by publishing to the appropriate DLX wait queue.
    
    Uses RabbitMQ Dead Letter Exchange mechanism:
    - Message is published to wait queue (no consumers)
    - RabbitMQ holds message for queue's TTL
    - After TTL expires, message is dead-lettered to webhook_work
    - A worker picks up the retry from webhook_work
    
    This is non-blocking - worker memory is freed immediately.
    """
    next_attempt = current_attempt + 1
    
    if next_attempt > MAX_ATTEMPTS:
        # All retries exhausted - send to dead letter queue
        logger.error(
            f"Webhook exhausted all retries: event_id={event_id}, "
            f"attempts={current_attempt}"
        )
        dispatch_webhook_task.apply_async(
            args=[event_id, next_attempt],
            queue=DEAD_QUEUE,
        )
        return
    
    # Get appropriate wait queue (0-indexed)
    queue_index = min(current_attempt - 1, len(WAIT_QUEUES) - 1)
    wait_queue = WAIT_QUEUES[queue_index]
    
    logger.info(
        f"Scheduling webhook retry via DLX: event_id={event_id}, "
        f"attempt={current_attempt}, next_attempt={next_attempt}, queue={wait_queue}"
    )
    
    # Publish NEW message to wait queue
    dispatch_webhook_task.apply_async(
        args=[event_id, next_attempt],
        queue=wait_queue,
    )
