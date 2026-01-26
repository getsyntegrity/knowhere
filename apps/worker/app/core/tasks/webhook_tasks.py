"""
Webhook Celery Tasks

Provides Celery tasks for async webhook dispatch with exponential backoff.
These tasks wrap the WebhookDispatcher service.
"""
import asyncio

from celery import Task
from loguru import logger

from shared.core.celery_app import get_celery_app
from app.services.webhook import MAX_ATTEMPTS, RETRY_DELAYS, JITTER_FACTOR
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException


celery_app = get_celery_app()


class WebhookDispatchTask(Task):
    """Base task class for webhook dispatch with proper error handling."""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Log successful webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.info(f"Webhook dispatch task completed: task_id={task_id}, event_id={event_id}")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log failed webhook dispatch."""
        event_id = args[0] if args else kwargs.get("event_id", "unknown")
        logger.error(f"Webhook dispatch task failed: task_id={task_id}, event_id={event_id}, error={exc}")


@celery_app.task(
    bind=True,
    base=WebhookDispatchTask,
    name="app.core.tasks.webhook_tasks.dispatch_webhook_task",
    max_retries=MAX_ATTEMPTS - 1,  # 5 retries (initial + 5 = 6 total attempts)
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_webhook_task(self, event_id: str) -> bool:
    """
    Dispatch a webhook event via Celery.
    
    This task wraps WebhookDispatcher.dispatch() and handles retries
    using Celery's built-in retry mechanism with exponential backoff.
    
    Args:
        event_id: The WebhookEvent ID to dispatch
        
    Returns:
        True if successfully dispatched or terminal
    """
    attempt = self.request.retries + 1
    logger.info(f"Webhook dispatch task started: event_id={event_id}, attempt={attempt}/{MAX_ATTEMPTS}")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from app.services.webhook.dispatcher import get_webhook_dispatcher
            
            dispatcher = get_webhook_dispatcher()
            result = loop.run_until_complete(dispatcher.dispatch(event_id))
            
            return result
            
        finally:
            loop.close()
            
    except Exception as e:
        # Wrap unknown exceptions if needed, but primary failure mode is WebhookDeliveryException
        logger.error(f"Webhook dispatch failed: event_id={event_id}, error={e}")
        
        # Calculate retry delay from RETRY_DELAYS constant
        if attempt < MAX_ATTEMPTS:
            delay_index = min(attempt - 1, len(RETRY_DELAYS) - 1)
            base_delay = RETRY_DELAYS[delay_index]
            
            # Apply jitter (±10%)
            import random
            jitter = random.uniform(1 - JITTER_FACTOR, 1 + JITTER_FACTOR)
            delay = int(base_delay * jitter)
            
            logger.info(f"Scheduling retry: event_id={event_id}, attempt={attempt}, delay={delay}s (base={base_delay}s)")
            
            # Use the original exception for context
            raise self.retry(exc=e, countdown=delay)
        
        # All retries exhausted
        logger.error(f"Webhook dispatch exhausted all retries: event_id={event_id}")
        raise
