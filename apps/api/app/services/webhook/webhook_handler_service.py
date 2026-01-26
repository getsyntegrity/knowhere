"""
Webhook Handler Service (API Service)

Handles Job completion and failure webhook notifications using the
Transactional Outbox Pattern for reliability:
1. Creates WebhookEvent record atomically with job state
2. Publishes event to RabbitMQ for async dispatch
3. Falls back to immediate send + Celery retry for quick delivery
"""
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from app.repositories.webhook_repository import WebhookRepository
from shared.services.storage.file_upload_service import FileUploadService


class WebhookHandlerService:
    """Webhook Handler Service - Uses Transactional Outbox Pattern"""
    
    # Default signing secret if not provided in job metadata
    DEFAULT_SECRET = "default_webhook_secret"
    
    def __init__(self):
        self.webhook_repo = WebhookRepository()
        self.upload_service = FileUploadService()
    
    async def handle_job_completion_webhook(
        self,
        db,
        job_id: str,
        job_result: Any,
        webhook_url: str,
        webhook_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle Job completion Webhook.
        
        Creates a WebhookEvent record (outbox pattern) and publishes to queue
        for async dispatch with retries.
        
        Args:
            db: Database session
            job_id: Job ID
            job_result: JobResult object
            webhook_url: Webhook URL
            webhook_secret: HMAC signing secret (optional)
        
        Returns:
            Dict: Result with event_id if created
        """
        try:
            # Build webhook payload
            webhook_payload: Dict[str, Any] = {
                "event": "job.completed",
                "job_id": job_id,
                "status": "completed",
                "delivery_mode": "url",
                "completed_at": datetime.utcnow().isoformat()
            }
            
            # Add result_url (ZIP download link)
            if job_result and job_result.result_s3_key:
                result_url_info = await self.upload_service.generate_download_url(job_result.result_s3_key)
                webhook_payload["result_url"] = result_url_info["download_url"]
            
            # Add result (checksum and statistics)
            if job_result and job_result.inline_payload:
                webhook_payload["result"] = job_result.inline_payload
            
            # Get webhook secret from job metadata if not provided
            secret = webhook_secret or await self._get_webhook_secret(job_id)
            
            # Create WebhookEvent (outbox pattern)
            from app.services.webhook.webhook_event_service import get_webhook_event_service
            event_service = get_webhook_event_service()
            
            event = await event_service.create_event(
                db=db,
                job_id=job_id,
                target_url=webhook_url,
                secret=secret,
                payload=webhook_payload
            )
            
            # Flush to ensure event is in DB (transaction will be committed by caller)
            await db.flush()
            
            logger.info(f"WebhookEvent created for job completion: event_id={event.id}, job_id={job_id}")
            
            # For immediate delivery attempt, also use the existing service
            # This provides fast delivery while the outbox provides reliability
            try:
                from app.services.webhook.webhook_service import WebhookService
                webhook_service = WebhookService()
                
                first_result = await webhook_service.send_webhook(
                    job_id=job_id,
                    webhook_url=webhook_url,
                    payload=webhook_payload,
                    attempt_number=1,
                    event_id=event.id  # Link to the event
                )
                
                if first_result.get("success", False):
                    # Update event status to delivered
                    from shared.models.database.webhook import WebhookEventStatus
                    event.status = WebhookEventStatus.DELIVERED
                    event.attempts = 1
                    logger.info(f"Job completion Webhook sent successfully: job_id={job_id}")
                    return {"success": True, "event_id": event.id}
                
            except Exception as e:
                logger.warning(f"Immediate webhook send failed, will rely on dispatcher: {e}")
            
            # Return event info - dispatcher will handle async delivery
            return {
                "success": True,
                "event_id": event.id,
                "queued": True,
                "message": "WebhookEvent created, queued for async dispatch"
            }
            
        except Exception as e:
            logger.error(f"Failed to handle job completion webhook: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_job_failure_webhook(
        self,
        db,
        job_id: str,
        error_message: str,
        error_type: Optional[str] = None,
        error_code: str = "UNKNOWN",
        webhook_url: str = None,
        webhook_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle Job failure Webhook.
        
        Creates a WebhookEvent record (outbox pattern) and publishes to queue
        for async dispatch with retries.
        
        Args:
            db: Database session
            job_id: Job ID
            error_message: Error message
            error_type: Error type (optional)
            error_code: Canonical error code
            webhook_url: Webhook URL (optional, fetched from Job if not provided)
            webhook_secret: HMAC signing secret (optional)
        
        Returns:
            Dict: Result with event_id if created
        """
        try:
            # If webhook_url not provided, get from Job
            if not webhook_url:
                from app.repositories.job_repository import JobRepository
                job_repo = JobRepository()
                job = await job_repo.get_job_by_id(db, job_id)
                if not job or not job.webhook_enabled or not job.webhook_url:
                    logger.info(f"Job {job_id} Webhook not enabled, skipping")
                    return {"success": False, "skipped": True, "reason": "webhook_not_enabled"}
                webhook_url = job.webhook_url
            
            # Build webhook payload
            webhook_payload: Dict[str, Any] = {
                "event": "job.failed",
                "job_id": job_id,
                "status": "failed",
                "failed_at": datetime.utcnow().isoformat(),
                "error": {
                    "message": error_message,
                    "type": error_type or "Exception",
                    "code": error_code
                }
            }
            
            # Get webhook secret from job metadata if not provided
            secret = webhook_secret or await self._get_webhook_secret(job_id)
            
            # Create WebhookEvent (outbox pattern)
            from app.services.webhook.webhook_event_service import get_webhook_event_service
            event_service = get_webhook_event_service()
            
            event = await event_service.create_event(
                db=db,
                job_id=job_id,
                target_url=webhook_url,
                secret=secret,
                payload=webhook_payload
            )
            
            # Flush to ensure event is in DB
            await db.flush()
            
            logger.info(f"WebhookEvent created for job failure: event_id={event.id}, job_id={job_id}")
            
            # Attempt immediate delivery
            try:
                from app.services.webhook.webhook_service import WebhookService
                webhook_service = WebhookService()
                
                first_result = await webhook_service.send_webhook(
                    job_id=job_id,
                    webhook_url=webhook_url,
                    payload=webhook_payload,
                    attempt_number=1,
                    event_id=event.id
                )
                
                if first_result.get("success", False):
                    from shared.models.database.webhook import WebhookEventStatus
                    event.status = WebhookEventStatus.DELIVERED
                    event.attempts = 1
                    logger.info(f"Job failure Webhook sent successfully: job_id={job_id}")
                    return {"success": True, "event_id": event.id}
                    
            except Exception as e:
                logger.warning(f"Immediate webhook send failed, will rely on dispatcher: {e}")
            
            return {
                "success": True,
                "event_id": event.id,
                "queued": True,
                "message": "WebhookEvent created, queued for async dispatch"
            }
            
        except Exception as e:
            logger.error(f"Failed to handle job failure webhook: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_webhook_secret(self, job_id: str) -> str:
        """Get webhook secret from job metadata or use default."""
        try:
            from shared.services.redis import JobMetadataService, RedisServiceFactory
            from shared.models.schemas.job_metadata import JobMetadataHelper
            
            redis_service = RedisServiceFactory.get_service()
            metadata_service = JobMetadataService(redis_service)
            job_metadata = await metadata_service.get_metadata(job_id)
            
            if job_metadata:
                webhook_config = JobMetadataHelper.get_webhook(job_metadata)
                if webhook_config and webhook_config.get("secret"):
                    return webhook_config["secret"]
            
            return self.DEFAULT_SECRET
            
        except Exception as e:
            logger.warning(f"Failed to get webhook secret from metadata: {e}")
            return self.DEFAULT_SECRET
