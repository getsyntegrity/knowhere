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
    logger.info(
        f"Webhook dispatch task started: event_id={event_id}, "
        f"attempt={attempt}/{MAX_ATTEMPTS}, jitter_applied={jitter_applied}"
    )
    
    # Non-Blocking Jitter Implementation:
    # If this is a retry (attempt > 1) and jitter hasn't been applied yet:
    # 1. Calculate random jitter delay (Strict 10% of previous wait)
    # 2. Reschedule THIS task with countdown=jitter
    # 3. Mark jitter_applied=True in the rescheduled task
    # 4. Return immediately (freeing the worker process)
    if attempt > 1 and not jitter_applied:
        import random
        
        # Determine previous wait duration
        # attempt=2 -> came from wait index 0 (1m)
        # attempt=3 -> came from wait index 1 (10m)
        prev_idx = min(attempt - 2, len(WAIT_DURATIONS_SECONDS) - 1)
        if prev_idx < 0: prev_idx = 0  # Should not happen given attempt > 1
        
        base_wait = WAIT_DURATIONS_SECONDS[prev_idx]
        max_jitter = base_wait * 0.1  # Strict 10% jitter
        
        jitter_seconds = random.uniform(0, max_jitter)

        if jitter_seconds > 0.1:
            logger.info(f"Scheduling non-blocking jitter: {jitter_seconds:.2f}s (attempt {attempt})")
            # Use retry to reschedule with countdown. 
            # We pass max_retries=None to avoid Celery's internal retry limit interfering with our business logic limit.
            try:
                self.retry(
                    countdown=jitter_seconds,
                    args=[event_id, attempt],
                    kwargs={"jitter_applied": True},
                    max_retries=None
                )
            except Exception:
                # self.retry raises Retry exception to stop execution, which is expected behavior
                raise
            return False
            
    try:
        # Jitter is handled above (non-blocking), so we just dispatch directly here
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
        _schedule_retry(self, event_id, attempt)
        return False  # Task completes, retry is a new message
        
    except Exception as exc:
        # Unexpected error - log and retry (could be transient)
        logger.error(
            f"Webhook dispatch unexpected error: event_id={event_id}, "
            f"error={type(exc).__name__}: {exc}"
        )
        _schedule_retry(self, event_id, attempt)
        return False


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
    
    if next_attempt > MAX_ATTEMPTS:
        # All retries exhausted - send to dead letter queue
        logger.error(
            f"Webhook exhausted all retries: event_id={event_id}, "
            f"attempts={current_attempt}"
        )
        try:
            dispatch_webhook_task.apply_async(
                args=[event_id, next_attempt],
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
            queue=wait_queue,
        )
    except Exception as exc:
        logger.error(
            f"Failed to schedule DLX retry, falling back to Celery countdown: "
            f"event_id={event_id}, error={exc}"
        )
        # Fallback: Re-raise as Celery retry exception to hold in queue
        task_instance.retry(exc=exc, countdown=60, max_retries=None)
