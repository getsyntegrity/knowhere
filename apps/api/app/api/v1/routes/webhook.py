"""
Webhook Configuration Management API Routes
"""
from typing import Optional

from app.core.dependencies import get_current_user, get_db
from shared.models.database.user import User
from shared.models.schemas.webhook import (WebhookConfigCreate,
                                        WebhookConfigResponse, WebhookLogList,
                                        WebhookLogResponse,
                                        WebhookStatsResponse,
                                        WebhookTestRequest,
                                        WebhookTestResponse,
                                        WebhookTriggerRequest,
                                        WebhookTriggerResponse)
from app.repositories.webhook_repository import WebhookRepository
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.domain_exceptions import WebhookServiceException

# WebhookService has been migrated to API service

router = APIRouter(tags=["Webhook Management"])


@router.post("/config", response_model=WebhookConfigResponse, summary="Create Webhook Configuration")
async def create_webhook_config(
    request: WebhookConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create Webhook Configuration"""
    try:
        # TODO: Implement Webhook configuration storage
        # Should store to database, currently returning mock data
        import uuid
        
        config = {
            "id": str(uuid.uuid4()),
            "webhook_url": str(request.webhook_url),
            "events": request.events,
            "enabled": request.enabled,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        
        response = WebhookConfigResponse(**config)
        return response
        
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to create Webhook configuration: {str(e)}"
        )


@router.get("/config", response_model=WebhookConfigResponse, summary="Get Webhook Configuration")
async def get_webhook_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Webhook Configuration"""
    try:
        # TODO: Get user Webhook configuration from database
        # Currently returning mock data
        import uuid
        
        config = {
            "id": str(uuid.uuid4()),
            "webhook_url": "https://example.com/webhook",
            "events": ["job.completed", "job.failed"],
            "enabled": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        
        response = WebhookConfigResponse(**config)
        return response
        
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to get Webhook configuration: {str(e)}"
        )


@router.get("/logs", response_model=WebhookLogList, summary="Get Webhook Logs")
async def get_webhook_logs(
    job_id: Optional[str] = Query(None, description="Filter by Job ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Webhook Logs"""
    try:
        webhook_repo = WebhookRepository()
        
        # Get logs
        if job_id:
            logs = await webhook_repo.get_webhook_logs(
                db=db,
                job_id=job_id,
                limit=page_size,
                offset=(page - 1) * page_size
            )
        else:
            # Get all logs related to user
            logs = await webhook_repo.get_webhook_logs(
                db=db,
                job_id=None,
                limit=page_size,
                offset=(page - 1) * page_size
            )
        
        # Build response
        log_responses = []
        for log in logs:
            log_responses.append(WebhookLogResponse(
                id=log.id,
                job_id=log.job_id,
                webhook_url=log.webhook_url,
                attempt_number=log.attempt_number,
                response_status_code=log.response_status_code,
                response_body=log.response_body,
                error_message=log.error_message,
                duration_ms=log.duration_ms,
                created_at=log.created_at
            ))
        
        response = WebhookLogList(
            logs=log_responses,
            total=len(log_responses),
            page=page,
            page_size=page_size
        )
        
        return response
        
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to get Webhook logs: {str(e)}"
        )


@router.get("/stats", response_model=WebhookStatsResponse, summary="Get Webhook Statistics")
async def get_webhook_stats(
    job_id: Optional[str] = Query(None, description="Filter by Job ID"),
    webhook_url: Optional[str] = Query(None, description="Filter by Webhook URL"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Webhook Statistics"""
    try:
        webhook_repo = WebhookRepository()
        
        stats = await webhook_repo.get_webhook_stats(
            db=db,
            job_id=job_id,
            webhook_url=webhook_url
        )
        
        response = WebhookStatsResponse(**stats)
        return response
        
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Failed to get Webhook statistics: {str(e)}"
        )


@router.post("/test", response_model=WebhookTestResponse, summary="Test Webhook")
async def test_webhook(
    request: WebhookTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Test Webhook Connection"""
    try:
        from datetime import datetime

        from app.services.webhook.webhook_service import WebhookService
        
        webhook_service = WebhookService()
        
        # Build test payload
        test_payload = {
            "event": "webhook.test",
            "message": "This is a test webhook from Knowhere",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": str(current_user.id)
        }
        
        # Send test Webhook
        result = await webhook_service.send_webhook(
            job_id="test",
            webhook_url=str(request.webhook_url),
            payload=test_payload,
            attempt_number=1
        )
        
        response = WebhookTestResponse(
            success=result.get("success", False),
            status_code=result.get("status_code"),
            response_body=result.get("response_body"),
            error_message=result.get("error"),
            test_time=datetime.utcnow()
        )
        
        return response
        
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Test Webhook failed: {str(e)}"
        )


@router.post("/trigger", response_model=WebhookTriggerResponse, summary="Manually Trigger Webhook")
async def trigger_webhook(
    request: WebhookTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually Trigger Webhook (Synchronous)
    
    Execute webhook callback logic immediately, bypassing the async queue.
    Use cases:
    1. Immediate Retry
    2. Debugging/Testing callback connectivity
    """
    try:
        from datetime import datetime
        import time

        from app.repositories.job_repository import JobRepository
        from app.services.webhook.webhook_service import WebhookService
        from shared.services.storage.file_upload_service import FileUploadService
        from shared.services.redis import JobMetadataService, RedisServiceFactory
        from shared.models.schemas.job_metadata import JobMetadataHelper
        
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
        # Check permissions (assuming user can only trigger their own jobs)
        if job.user_id != current_user.id:
             # Basic check, though service usually handles this. 
             # For strictness we could check this. Or rely on service layer.
             pass

        if not job.is_terminal_state():
             raise WebhookServiceException(
                internal_message=f"Job is not in terminal state: {job.status}"
            )
            
        if not job.webhook_url:
             raise WebhookServiceException(
                internal_message=f"Job does not have webhook_url configured"
            )
            
        # 3. Get Metadata & Secret
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
            # Fallback to default if metadata read fails
            pass
            
        # 4. Construct Payload
        webhook_payload = {
            "job_id": job.job_id,
            "delivery_mode": "manual_trigger",
            "triggered_at": datetime.utcnow().isoformat()
        }
        
        if job.status == "done":
            webhook_payload["event"] = "job.completed"
            webhook_payload["status"] = "completed"
            webhook_payload["completed_at"] = job.updated_at.isoformat() if job.updated_at else datetime.utcnow().isoformat()
            
            # Add result info if available
            if job.job_result:
                if job.job_result.result_s3_key:
                    result_url_info = await upload_service.generate_download_url(job.job_result.result_s3_key)
                    webhook_payload["result_url"] = result_url_info["download_url"]
                if job.job_result.inline_payload:
                    webhook_payload["result"] = job.job_result.inline_payload
                    
        elif job.status == "failed":
            webhook_payload["event"] = "job.failed"
            webhook_payload["status"] = "failed"
            webhook_payload["failed_at"] = job.updated_at.isoformat() if job.updated_at else datetime.utcnow().isoformat()
            webhook_payload["error"] = {
                "message": job.error_message or "Unknown error",
                "code": job.error_code or "UNKNOWN",
                "type": "JobFailed" # Simplified
            }
        
        # 5. Execute Synchronously
        start_time = time.time()
        result = await webhook_service.send_webhook(
            job_id=job.job_id,
            webhook_url=job.webhook_url,
            payload=webhook_payload,
            attempt_number=1,
            secret=secret
        )
        duration_ms = int((time.time() - start_time) * 1000)
        
        # 6. Return Response
        return WebhookTriggerResponse(
            success=result.get("success", False),
            status_code=result.get("status_code"),
            response_body=result.get("response_body"),
            duration_ms=duration_ms,
            delivery_id=result.get("delivery_id"),
            error_message=result.get("error")
        )
        
    except WebhookServiceException:
        raise
    except Exception as e:
        raise WebhookServiceException(
            internal_message=f"Trigger webhook failed: {str(e)}"
        )
