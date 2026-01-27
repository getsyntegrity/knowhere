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
from app.services.webhook.webhook_service import WebhookService
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
        webhook_repo = WebhookRepository()
        
        logs = await webhook_repo.get_webhook_logs(
            db=db,
            job_id=job_id,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        
        log_responses = [
            WebhookLogResponse(
                id=log.id,
                job_id=log.job_id,
                webhook_url=log.webhook_url,
                attempt_number=log.attempt_number,
                response_status_code=log.response_status_code,
                response_body=log.response_body,
                error_message=log.error_message,
                duration_ms=log.duration_ms,
                created_at=log.created_at,
            )
            for log in logs
        ]
        
        return WebhookLogList(
            logs=log_responses,
            total=len(log_responses),
            page=page,
            page_size=page_size,
        )
        
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to get webhook logs: {str(e)}"
        )


@router.post("/trigger", response_model=WebhookTriggerResponse, summary="Manually Trigger Webhook")
async def trigger_webhook(
    request: WebhookTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a webhook for a completed job (synchronous).
    
    This bypasses the async retry queue and executes the HTTP request immediately,
    returning the actual response from the user's webhook server.
    
    Use cases:
    - Immediate retry after a failed delivery
    - Debugging/testing webhook connectivity
    """
    try:
        job_repo = JobRepository()
        upload_service = FileUploadService()
        webhook_service = WebhookService()
        
        # 1. Fetch Job
        job = await job_repo.get_job_by_id(db, request.job_id)
        if not job:
            raise WebhookServiceException(
                internal_message=f"Job not found: {request.job_id}"
            )
        
        # 2. Validation
        if not job.is_terminal_state():
            raise WebhookServiceException(
                internal_message=f"Job is not in terminal state: {job.status}"
            )
        
        if not job.webhook_url:
            raise WebhookServiceException(
                internal_message="Job does not have webhook_url configured"
            )
        
        # 3. Get webhook secret from metadata
        secret = "default_webhook_secret"
        try:
            redis_service = RedisServiceFactory.get_service()
            metadata_service = JobMetadataService(redis_service)
            job_metadata = await metadata_service.get_metadata(job.job_id)
            
            if job_metadata:
                webhook_config = JobMetadataHelper.get_webhook(job_metadata)
                if webhook_config and webhook_config.get("secret"):
                    secret = webhook_config["secret"]
        except Exception:
            pass  # Fallback to default
        
        # 4. Construct payload
        webhook_payload = {
            "job_id": job.job_id,
            "delivery_mode": "manual_trigger",
            "triggered_at": datetime.utcnow().isoformat(),
        }
        
        if job.status == "done":
            webhook_payload["event"] = "job.completed"
            webhook_payload["status"] = "completed"
            webhook_payload["completed_at"] = (
                job.updated_at.isoformat() if job.updated_at else datetime.utcnow().isoformat()
            )
            
            if job.job_result:
                if job.job_result.result_s3_key:
                    result_url_info = await upload_service.generate_download_url(
                        job.job_result.result_s3_key
                    )
                    webhook_payload["result_url"] = result_url_info["download_url"]
                if job.job_result.inline_payload:
                    webhook_payload["result"] = job.job_result.inline_payload
                    
        elif job.status == "failed":
            webhook_payload["event"] = "job.failed"
            webhook_payload["status"] = "failed"
            webhook_payload["failed_at"] = (
                job.updated_at.isoformat() if job.updated_at else datetime.utcnow().isoformat()
            )
            webhook_payload["error"] = {
                "message": job.error_message or "Unknown error",
                "code": job.error_code or "UNKNOWN",
                "type": "JobFailed",
            }
        
        # 5. Execute synchronously
        start_time = time.time()
        result = await webhook_service.send_webhook(
            job_id=job.job_id,
            webhook_url=job.webhook_url,
            payload=webhook_payload,
            attempt_number=1,
            secret=secret,
        )
        duration_ms = int((time.time() - start_time) * 1000)
        
        # 6. Return response
        return WebhookTriggerResponse(
            success=result.get("success", False),
            status_code=result.get("status_code"),
            response_body=result.get("response_body"),
            duration_ms=duration_ms,
            delivery_id=result.get("delivery_id"),
            error_message=result.get("error"),
        )
        
    except WebhookServiceException:
        raise
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to trigger webhook: {str(e)}"
        )


@router.post("/test-callback", summary="Test Webhook Callback Endpoint")
async def test_webhook_callback(
    request: Request,
    payload: dict = Body(...),
):
    """
    Test endpoint to receive webhook callbacks.
    
    Use this endpoint to verify webhook delivery. It logs receiving data
    to the server console and returns the received payload.
    """
    # Log the event
    logger.info("🔔 [Test Callback] Webhook Received!")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Payload: {payload}")
    
    return {
        "status": "received",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
        "received_headers": {k: v for k, v in request.headers.items() if k.lower().startswith("x-") or k.lower() == "user-agent"},
    }
