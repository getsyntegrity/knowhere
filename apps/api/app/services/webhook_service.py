"""
Consolidated Webhook Service

Single responsibility: Create WebhookEvents and publish to message queue.
HTTP delivery is handled by shared.services.webhook.dispatcher.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.response import build_standard_error_response
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.core.exceptions.webhook_exceptions import WebhookConfigException
from shared.services.redis import JobMetadataService, RedisServiceFactory
from shared.models.schemas.job_metadata import JobMetadataHelper


class WebhookService:
    """
    Webhook Service - Transactional Outbox Pattern
    
    Creates WebhookEvent records and publishes to MQ for async delivery.
    """
    
    async def create_job_completion_event(
        self,
        db: AsyncSession,
        job_id: str,
        webhook_url: str
    ) -> WebhookEvent:
        """
        Create webhook event for job completion.
        
        Args:
            db: Database session (in active transaction)
            job_id: Job ID
            webhook_url: Webhook URL
            
        Returns:
            Created WebhookEvent
        """
        # Build minimal payload - dispatcher will enrich at delivery time
        payload: Dict[str, Any] = {
            "event": "job.completed",
            "job_id": job_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat()
            # NOTE: result_url and result added by dispatcher at delivery
        }
        
        # Create event
        event = await self._create_event(
            db=db,
            job_id=job_id,
            target_url=webhook_url,
            payload=payload
        )
        
        logger.info(f"Job completion webhook event created: event_id={event.id}, job_id={job_id}")
        return event
    
    async def create_job_failure_event(
        self,
        db: AsyncSession,
        job_id: str,
        error_message: str,
        error_type: Optional[str] = None,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
        webhook_url: str = None,
    ) -> WebhookEvent:
        """
        Create webhook event for job failure.
        
        Args:
            db: Database session (in active transaction)
            job_id: Job ID
            error_message: Error message
            error_type: Error type (optional)
            error_code: Error code
            error_details: Structured error details (optional)
            webhook_url: Webhook URL
            
        Returns:
            Created WebhookEvent
        """
        # Build payload with standardized error format
        payload: Dict[str, Any] = {
            "event": "job.failed",
            "job_id": job_id,
            "status": "failed",
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": build_standard_error_response(
                code=error_code,
                message=error_message,
                request_id=job_id,
                details=error_details
            )
        }
        
        # Create event
        event = await self._create_event(
            db=db,
            job_id=job_id,
            target_url=webhook_url,
            payload=payload
        )
        
        logger.info(f"Job failure webhook event created: event_id={event.id}, job_id={job_id}")
        return event
    
    async def publish_to_queue(self, event_id: str) -> bool:
        """Publish webhook event for async delivery.

        Routes to QStash or Celery based on the WEBHOOK_DELIVERY_PROVIDER
        feature flag.  Should be called AFTER transaction commit.
        """
        from shared.core.config import app_config

        if app_config.is_qstash_enabled:
            return await self._publish_via_qstash(event_id)
        return await self._publish_via_celery(event_id)

    async def _publish_via_celery(self, event_id: str) -> bool:
        """Legacy path: dispatch via Celery task."""
        try:
            from shared.core.celery_app import get_celery_app

            celery_app = get_celery_app()
            task = celery_app.send_task(
                "app.core.tasks.webhook_tasks.dispatch_webhook_task",
                args=[event_id],
            )
            logger.info(f"Webhook dispatch task scheduled: event_id={event_id}, task_id={task.id}")
            return True
        except Exception as exc:
            logger.error(f"Failed to schedule webhook dispatch task: event_id={event_id}, error={exc}")
            return False

    async def _publish_via_qstash(self, event_id: str) -> bool:
        """New path: publish via QStash for managed delivery + retry."""
        try:
            from shared.services.webhook.qstash_publisher import get_qstash_webhook_publisher

            publisher = get_qstash_webhook_publisher()
            message_id = publisher.publish_event(event_id)
            if message_id:
                logger.info(f"Webhook published via QStash: event_id={event_id}, message_id={message_id}")
                return True
            logger.warning(f"QStash publish returned no message_id: event_id={event_id}")
            return False
        except Exception as exc:
            logger.error(f"QStash publish failed: event_id={event_id}, error={exc}")
            return False

    async def _create_event(
        self,
        db: AsyncSession,
        job_id: str,
        target_url: str,
        payload: Dict[str, Any]
    ) -> WebhookEvent:
        """
        Create WebhookEvent record.
        
        Args:
            db: Database session
            job_id: Job ID
            target_url: Webhook URL
            payload: JSON payload
            
        Returns:
            Created WebhookEvent
            
        Raises:
            WebhookConfigException: If validation fails
        """
        # Validate
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
            
        # Create event
        event = WebhookEvent(
            job_id=job_id,
            target_url=target_url,
            payload=payload,
            status=WebhookEventStatus.PENDING,
            attempts=0,
        )
        
        db.add(event)
        await db.flush()  # Get ID, but don't commit (caller controls transaction)
        
        return event


# Singleton
_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """Get singleton WebhookService instance."""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service
