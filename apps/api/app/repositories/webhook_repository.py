"""
Webhook Repository Layer

Provides database operations for webhook delivery logging.
"""
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.webhook_log import WebhookLog


class WebhookRepository:
    """Repository for webhook delivery log operations."""
    
    async def log_webhook_attempt(
        self,
        db: AsyncSession,
        job_id: str,
        webhook_url: str,
        attempt_number: int,
        request_payload: Dict[str, Any],
        signature: str,
        idempotency_key: str,
        response_status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: int = 0,
        event_id: Optional[str] = None,
    ) -> Optional[WebhookLog]:
        """
        Log a webhook delivery attempt.
        
        Creates a WebhookLog entry for the delivery attempt with all
        request and response details for auditing purposes.
        """
        try:
            webhook_log = WebhookLog(
                job_id=job_id,
                event_id=event_id,
                webhook_url=webhook_url,
                attempt_number=attempt_number,
                request_payload=request_payload,
                signature=signature,
                idempotency_key=idempotency_key,
                response_status_code=response_status_code,
                response_body=response_body,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            
            db.add(webhook_log)
            await db.commit()
            
            logger.info(
                f"Webhook log recorded: job_id={job_id}, attempt={attempt_number}, "
                f"status={response_status_code}, duration_ms={duration_ms}"
            )
            return webhook_log
            
        except Exception as e:
            logger.error(f"Failed to record webhook log: {e}")
            await db.rollback()
            return None
    
    async def get_webhook_logs(
        self,
        db: AsyncSession,
        user_id: str,
        job_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[WebhookLog], int]:
        """
        Get webhook delivery logs filtered by user_id (required).
        
        Args:
            db: Database session
            user_id: ID of the user who owns the logs (Required for security)
            job_id: Optional filter by job ID
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            Tuple containing (List of WebhookLog entries, Total count)
        """
        try:
            from sqlalchemy import func
            from shared.models.database.job import Job
            
            # Base query - Join with Job to filter by user_id
            query = select(WebhookLog).join(Job, WebhookLog.job_id == Job.job_id).order_by(desc(WebhookLog.created_at))
            count_query = select(func.count()).select_from(WebhookLog).join(Job, WebhookLog.job_id == Job.job_id)
            
            # Application Security: Always filter by user_id
            query = query.where(Job.user_id == user_id)
            count_query = count_query.where(Job.user_id == user_id)
            
            if job_id:
                # If job_id provided, ensure it belongs to the user (implicit via join, but good to be explicit)
                query = query.where(WebhookLog.job_id == job_id)
                count_query = count_query.where(WebhookLog.job_id == job_id)
            
            # Application pagination
            paginated_query = query.limit(limit).offset(offset)
            
            # Execute
            result = await db.execute(paginated_query)
            logs = list(result.scalars().all())
            
            count_result = await db.execute(count_query)
            total = count_result.scalar() or 0
            
            return logs, total
            
        except Exception as e:
            logger.error(f"Failed to get webhook logs: {e}")
            return [], 0
