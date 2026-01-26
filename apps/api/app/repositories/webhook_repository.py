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
        job_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WebhookLog]:
        """
        Get webhook delivery logs with optional job_id filter.
        
        Args:
            db: Database session
            job_id: Optional filter by job ID (if None, returns all logs)
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of WebhookLog entries ordered by created_at descending
        """
        try:
            query = select(WebhookLog).order_by(desc(WebhookLog.created_at))
            
            if job_id:
                query = query.where(WebhookLog.job_id == job_id)
            
            query = query.limit(limit).offset(offset)
            
            result = await db.execute(query)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(f"Failed to get webhook logs: {e}")
            return []
