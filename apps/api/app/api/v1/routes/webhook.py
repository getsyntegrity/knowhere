"""
Webhook API Routes

- GET /logs: Get webhook delivery history
- POST /trigger: Manually trigger webhook for a job
"""
from datetime import datetime
import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.repositories.job_repository import JobRepository
from app.repositories.webhook_repository import WebhookRepository
from shared.services.webhook import get_webhook_dispatcher
from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.core.exceptions.domain_exceptions import WebhookServiceException
from shared.models.database.user import User
from shared.models.schemas.job_metadata import JobMetadataHelper
from shared.models.schemas.webhook import (
    WebhookLogList,
    WebhookLogResponse,
    WebhookTriggerRequest,
    WebhookTriggerResponse,
)
from shared.services.redis import JobMetadataService, RedisServiceFactory
from shared.services.storage.file_upload_service import FileUploadService


router = APIRouter(tags=["Webhook"])


@router.get("/logs", response_model=WebhookLogList, summary="Get Webhook Delivery Logs")
async def get_webhook_logs(
    job_id: Optional[str] = Query(None, description="Filter by Job ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get webhook delivery history logs.
    
    Returns a paginated list of webhook delivery attempts, optionally filtered by job_id.
    Each log entry includes the delivery status, duration, and response details.
    """
    try:
        repo = WebhookRepository()
        offset = (page - 1) * page_size
        logs, total = await repo.get_webhook_logs(
            db=db, job_id=job_id, limit=page_size, offset=offset
        )
        
        return WebhookLogList(
            total=total,
            page=page,
            page_size=page_size,
            logs=[
                WebhookLogResponse(
                    id=log.id,
                    job_id=log.job_id,
                    webhook_url=log.webhook_url,
                    attempt_number=log.attempt_number,
                    request_payload=log.request_payload,
                    signature=log.signature,
                    idempotency_key=log.idempotency_key,
                    response_status_code=log.response_status_code,
                    response_body=log.response_body,
                    error_message=log.error_message,
                    duration_ms=log.duration_ms,
                    created_at=log.created_at,
                )
                for log in logs
            ],
        )
    except Exception as e:
        logger.error(f"Failed to get webhook logs: {e}")
        raise WebhookServiceException(
            internal_message=f"Failed to retrieve webhook logs: {str(e)}"
        )


@router.post("/trigger", response_model=WebhookTriggerResponse, summary="Manually Trigger Webhook")
async def trigger_webhook(
    request: WebhookTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a webhook for a completed or failed job.
    
    This sends a webhook notification synchronously and returns the delivery result.
    Use this for testing or retrying failed webhook deliveries.
    """
    try:
        job_repo = JobRepository()
        
        # 1. Fetch Job
        job = await job_repo.get_job_by_id(db, request.job_id)
        if not job:
            from shared.core.exceptions.domain_exceptions import NotFoundException
            raise NotFoundException(
                resource="Job",
                resource_id=request.job_id
            )
        
        # 2. Validation - client errors (400)
        if not job.is_terminal_state():
            from shared.core.exceptions.domain_exceptions import ValidationException
            raise ValidationException(
                user_message=f"Job must be in terminal state to trigger webhook. Current status: {job.status}",
                violations=[{"field": "job_id", "description": f"Job status is '{job.status}', expected 'done' or 'failed'"}]
            )
        
        if not job.webhook_url:
            from shared.core.exceptions.webhook_exceptions import WebhookConfigException
            raise WebhookConfigException(
                internal_message=f"Job {request.job_id} does not have webhook_url configured",
                user_message="Job does not have a webhook URL configured. Configure webhook_url when creating the job.",
                details={"field": "webhook_url", "reason": "not_configured"}
            )
        
        # 3. Get webhook secret from metadata
        secret = None
        try:
            redis_service = RedisServiceFactory.get_service()
            metadata_service = JobMetadataService(redis_service)
            job_metadata = await metadata_service.get_metadata(request.job_id)
            
            if job_metadata:
                webhook_config = JobMetadataHelper.get_webhook(job_metadata)
                if webhook_config and webhook_config.get("secret"):
                    secret = webhook_config["secret"]
        except Exception as e:
            # Metadata fetch failed - internal error (5xx)
            from shared.core.exceptions.domain_exceptions import RedisServiceException
            raise RedisServiceException(
                internal_message=f"Failed to fetch job metadata from Redis: {e}",
                operation="get_metadata",
                original_exception=e
            )
        
        # If no secret in config - client error (400)
        if not secret:
            from shared.core.exceptions.webhook_exceptions import WebhookConfigException
            raise WebhookConfigException(
                internal_message=f"Job {request.job_id} webhook config does not have secret",
                user_message="Webhook secret is not configured. Provide webhook.secret when creating the job.",
                details={"field": "webhook.secret", "reason": "not_configured"}
            )
        
        # 4. Build webhook payload (mimicking dispatcher enrichment)
        if job.status == "done":
            webhook_payload = {
                "event": "job.completed",
                "job_id": job.job_id,
                "status": "completed",
                "completed_at": (
                    job.updated_at.isoformat() if job.updated_at else datetime.utcnow().isoformat()
                ),
            }
            # Add result_url if available
            if job.job_result and job.job_result.result_s3_key:
                upload_service = FileUploadService()
                url_info = await upload_service.generate_download_url(job.job_result.result_s3_key)
                webhook_payload["result_url"] = url_info["download_url"]
            # Add inline result
            if job.job_result and job.job_result.inline_payload:
                webhook_payload["result"] = job.job_result.inline_payload
        else:
            webhook_payload = {
                "event": "job.failed",
                "job_id": job.job_id,
                "status": "failed",
                "failed_at": (
                    job.updated_at.isoformat() if job.updated_at else datetime.utcnow().isoformat()
                ),
                "error": {
                    "message": job.error_message or "Unknown error",
                    "code": job.error_code or "UNKNOWN",
                    "type": "JobFailed",
                },
            }
        
        # 5. Create event and dispatch synchronously using dispatcher
        from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
        
        event = WebhookEvent(
            job_id=job.job_id,
            target_url=job.webhook_url,
            secret=secret,
            payload=webhook_payload,
            status=WebhookEventStatus.PENDING,
            attempts=0
        )
        
        # Use dispatcher to send synchronously
        dispatcher = get_webhook_dispatcher()
        success, status_code, duration_ms, error_message, payload, headers = await dispatcher._send_webhook(event)
        
        combined_payload = {
            "header": headers,
            "payload": payload
        }

        # 6. Return response
        return WebhookTriggerResponse(
            success=success,
            status_code=status_code,
            response_body=None,  # Dispatcher doesn't return response body
            duration_ms=duration_ms,
            delivery_id=None,  # Manual trigger doesn't create delivery log
            error_message=error_message,
            request_payload=combined_payload,
        )
        
    except KnowhereException:
        # Re-raise all known exceptions (NotFoundException, ValidationException, etc.)
        raise
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to trigger webhook: {str(e)}"
        )


# @router.post("/test-callback", summary="Test Webhook Callback Endpoint")
# async def test_webhook_callback(
#     request: Request,
#     payload: dict = Body(...),
# ):
#     """
#     Test endpoint to receive webhook callbacks.
    
#     Use this endpoint to verify webhook delivery. It logs receiving data
#     to the server console and returns the received payload.
#     """
#     # Log the event
#     logger.info("🔔 [Test Callback] Webhook Received!")
#     logger.info(f"Headers: {dict(request.headers)}")
#     logger.info(f"Payload: {payload}")
    
#     return {
#         "status": "received",
#         "timestamp": datetime.utcnow().isoformat(),
#         "payload": payload,
#         "received_headers": {k: v for k, v in request.headers.items() if k.lower().startswith("x-") or k.lower() == "user-agent"},
#     }
