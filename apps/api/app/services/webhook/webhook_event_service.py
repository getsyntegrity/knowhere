"""
Webhook Event Service - Transactional Outbox Pattern Implementation

This service creates WebhookEvent records atomically with job state changes
and publishes events to RabbitMQ for async dispatch.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.core.exceptions.webhook_exceptions import WebhookConfigException


class WebhookEventService:
    """
    Service for creating and managing webhook events.
    
    Implements the Transactional Outbox pattern:
    1. WebhookEvent is created in the same transaction as job state change
    2. After commit, event is dispatched via Celery task for async processing
    """
    
    async def create_event(
        self,
        db: AsyncSession,
        job_id: str,
        target_url: str,
        secret: str,
        payload: Dict[str, Any],
    ) -> WebhookEvent:
        """
        Create a WebhookEvent record (the outbox).
        
        This should be called within the same transaction as the job state update
        to ensure atomicity. The event will be dispatched via Celery after commit.
        
        Args:
            db: Database session (should be in an active transaction)
            job_id: The job ID this webhook is for
            target_url: The webhook destination URL
            secret: The HMAC signing secret
            payload: The JSON payload to send
            
        Returns:
            The created WebhookEvent
            
        Raises:
            WebhookConfigException: If target_url or secret is invalid
        """
        # Validate configuration
        if not target_url:
            raise WebhookConfigException(
                internal_message="Missing webhook target_url",
                user_message="Webhook URL is required."
            )
            
        if not target_url.startswith(("http://", "https://")):
            raise WebhookConfigException(
                internal_message=f"Invalid webhook scheme: {target_url}",
                user_message="Webhook URL must start with http:// or https://."
            )
            
        if not secret:
            raise WebhookConfigException(
                internal_message="Missing webhook secret",
                user_message="Webhook secret is required for signature verification."
            )

        event = WebhookEvent(
            job_id=job_id,
            target_url=target_url,
            secret=secret,
            payload=payload,
            status=WebhookEventStatus.PENDING,
            attempts=0,
        )
        
        db.add(event)
        # Note: We don't commit here - caller is responsible for transaction management
        # This ensures atomicity with job state update
        await db.flush()  # Flush to get the ID assigned
        
        logger.info(f"WebhookEvent created: event_id={event.id}, job_id={job_id}")
        return event
    
    async def publish_event_to_queue(self, event_id: str) -> bool:
        """
        Schedule a Celery task to dispatch the webhook event.
        
        This should be called AFTER the transaction containing the WebhookEvent
        has been committed, to ensure the event exists in the database.
        
        Args:
            event_id: The WebhookEvent ID to dispatch
            
        Returns:
            True if task was scheduled successfully
        """
        try:
            from shared.core.celery_app import get_celery_app
            
            celery_app = get_celery_app()
            
            # Schedule the Celery task to dispatch this webhook event
            task = celery_app.send_task(
                "app.core.tasks.webhook_tasks.dispatch_webhook_task",
                args=[event_id],
            )
            
            logger.info(f"Webhook dispatch task scheduled: event_id={event_id}, task_id={task.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule webhook dispatch task: event_id={event_id}, error={e}")
            return False
    
    async def create_and_publish_event(
        self,
        db: AsyncSession,
        job_id: str,
        target_url: str,
        secret: str,
        payload: Dict[str, Any],
    ) -> Optional[WebhookEvent]:
        """
        Convenience method to create an event and publish it.
        
        Note: This commits the transaction! Use create_event + publish_event_to_queue
        separately if you need to control transaction boundaries.
        
        Args:
            db: Database session
            job_id: The job ID this webhook is for
            target_url: The webhook destination URL
            secret: The HMAC signing secret
            payload: The JSON payload to send
            
        Returns:
            The created WebhookEvent, or None if failed
        """
        try:
            event = await self.create_event(db, job_id, target_url, secret, payload)
            await db.commit()
            
            # Publish after commit to ensure event exists
            published = await self.publish_event_to_queue(event.id)
            if not published:
                logger.warning(f"Event created but publish failed: event_id={event.id}")
                # Event is still in DB, dispatcher can poll for it later
            
            return event
            
        except Exception as e:
            logger.error(f"Failed to create and publish webhook event: {e}")
            await db.rollback()
            return None


# Singleton instance
_webhook_event_service: Optional[WebhookEventService] = None


def get_webhook_event_service() -> WebhookEventService:
    """Get the singleton WebhookEventService instance."""
    global _webhook_event_service
    if _webhook_event_service is None:
        _webhook_event_service = WebhookEventService()
    return _webhook_event_service
