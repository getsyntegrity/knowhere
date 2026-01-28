"""
Consolidated Webhook Service

Single responsibility: Create WebhookEvents and publish to message queue.
HTTP delivery is handled by shared.services.webhook.dispatcher.
"""
from datetime import datetime
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
        webhook_url: str,
        webhook_secret: Optional[str] = None
    ) -> WebhookEvent:
        """
        Create webhook event for job completion.
        
        Args:
            db: Database session (in active transaction)
            job_id: Job ID
            webhook_url: Webhook URL
            webhook_secret: HMAC secret (optional, fetched from metadata if None)
            
        Returns:
            Created WebhookEvent
        """
        # Build minimal payload - dispatcher will enrich at delivery time
        payload: Dict[str, Any] = {
            "event": "job.completed",
            "job_id": job_id,
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat()
            # NOTE: result_url and result added by dispatcher at delivery
        }
        
        # Get secret
        secret = webhook_secret or await self._get_webhook_secret(job_id)
        
        # Create event
        event = await self._create_event(
            db=db,
            job_id=job_id,
            target_url=webhook_url,
            secret=secret,
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
        webhook_secret: Optional[str] = None
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
            webhook_secret: HMAC secret (optional, fetched from metadata if None)
            
        Returns:
            Created WebhookEvent
        """
        # Build payload with standardized error format
        payload: Dict[str, Any] = {
            "event": "job.failed",
            "job_id": job_id,
            "status": "failed",
            "failed_at": datetime.utcnow().isoformat(),
            "error": build_standard_error_response(
                code=error_code,
                message=error_message,
                request_id=job_id,
                details=error_details
            )
        }
        
        # Get secret
        secret = webhook_secret or await self._get_webhook_secret(job_id)
        
        # Create event
        event = await self._create_event(
            db=db,
            job_id=job_id,
            target_url=webhook_url,
            secret=secret,
            payload=payload
        )
        
        logger.info(f"Job failure webhook event created: event_id={event.id}, job_id={job_id}")
        return event
    
    async def publish_to_queue(self, event_id: str) -> bool:
        """
        Publish webhook event to message queue for async delivery.
        
        Should be called AFTER transaction commit.
        
        Args:
            event_id: WebhookEvent ID
            
        Returns:
            True if published successfully
        """
        try:
            from shared.core.celery_app import get_celery_app
            
            celery_app = get_celery_app()
            task = celery_app.send_task(
                "app.core.tasks.webhook_tasks.dispatch_webhook_task",
                args=[event_id],
            )
            
            logger.info(f"Webhook dispatch task scheduled: event_id={event_id}, task_id={task.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule webhook dispatch task: event_id={event_id}, error={e}")
            return False
    
    async def create_and_publish_completion(
        self,
        db: AsyncSession,
        job_id: str,
        webhook_url: str,
        webhook_secret: Optional[str] = None
    ) -> bool:
        """
        Create job completion webhook and publish immediately (no outbox pattern).
        
        Args:
            db: Database session
            job_id: Job ID
            webhook_url: Webhook URL
            webhook_secret: HMAC secret (optional)
            
        Returns:
            True if created and published successfully
        """
        try:
            event = await self.create_job_completion_event(db, job_id, webhook_url, webhook_secret)
            await db.commit()
            return await self.publish_to_queue(event.id)
        except Exception as e:
            logger.error(f"Failed to create and publish completion webhook: {e}")
            await db.rollback()
            return False
    
    async def create_and_publish_failure(
        self,
        db: AsyncSession,
        job_id: str,
        error_message: str,
        error_type: Optional[str] = None,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
        webhook_url: str = None,
        webhook_secret: Optional[str] = None
    ) -> bool:
        """
        Create job failure webhook and publish immediately (no outbox pattern).
        
        Args:
            db: Database session
            job_id: Job ID
            error_message: Error message
            error_type: Error type (optional)
            error_code: Error code
            error_details: Error details (optional)
            webhook_url: Webhook URL
            webhook_secret: HMAC secret (optional)
            
        Returns:
            True if created and published successfully
        """
        try:
            event = await self.create_job_failure_event(
                db, job_id, error_message, error_type, error_code, error_details, webhook_url, webhook_secret
            )
            await db.commit()
            return await self.publish_to_queue(event.id)
        except Exception as e:
            logger.error(f"Failed to create and publish failure webhook: {e}")
            await db.rollback()
            return False
    
    async def _create_event(
        self,
        db: AsyncSession,
        job_id: str,
        target_url: str,
        secret: str,
        payload: Dict[str, Any]
    ) -> WebhookEvent:
        """
        Create WebhookEvent record.
        
        Args:
            db: Database session
            job_id: Job ID
            target_url: Webhook URL
            secret: HMAC secret
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
            
        if not secret:
            raise WebhookConfigException(
                internal_message="Missing webhook secret",
                user_message="Webhook secret is required for signature verification."
            )
        
        # Create event
        event = WebhookEvent(
            job_id=job_id,
            target_url=target_url,
            secret=secret,
            payload=payload,
            status=WebhookEventStatus.PENDING,
            attempts=0,
        )
        
        db.add(event)
        await db.flush()  # Get ID, but don't commit (caller controls transaction)
        
        return event
    
    async def _get_webhook_secret(self, job_id: str) -> str:
        """
        Get webhook secret from job metadata or use default.
        
        Args:
            job_id: Job ID
            
        Returns:
            Webhook secret
        """
        try:
            redis_service = RedisServiceFactory.get_service()
            metadata_service = JobMetadataService(redis_service)
            job_metadata = await metadata_service.get_metadata(job_id)
            
            if job_metadata:
                webhook_config = JobMetadataHelper.get_webhook(job_metadata)
                if webhook_config and webhook_config.get("secret"):
                    return webhook_config["secret"]
        except Exception as e:
            logger.warning(f"Failed to get webhook secret from metadata: {e}")
        
        # Default fallback
        return "default_webhook_secret"


# Singleton
_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """Get singleton WebhookService instance."""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service
