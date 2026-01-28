"""
Webhook Dispatcher Service

Dispatches webhook events via HTTP requests with HMAC signing and delivery logging.
Called by Celery task for async processing.
"""
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import asyncio

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Use standard db context - run_async_task handles the loop reuse
from shared.core.database import get_db_context
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus

from shared.models.database.webhook_log import WebhookLog
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException

# Configuration constants
HTTP_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 6



class WebhookDispatcher:
    """
    Webhook Dispatcher - Consumes events and sends HTTP requests.
    
    Implements the consumer side of the Transactional Outbox Pattern:
    1. Fetches WebhookEvent from database
    2. Checks if terminal or max attempts exceeded
    3. Signs payload and sends HTTP request
    4. Logs delivery attempt
    5. On failure, schedules retry via DLX
    """
    
    async def dispatch(self, event_id: str) -> bool:
        """
        Dispatch a webhook event.
        
        Args:
            event_id: The WebhookEvent ID to dispatch
            
        Returns:
            True if successfully dispatched or terminal, False if should retry
        """
        async with get_db_context() as db:
            # 1. Fetch event from database
            event = await self._fetch_event(db, event_id)
            
            if not event:
                logger.warning(f"WebhookEvent not found: {event_id}")
                return True  # ACK - event doesn't exist
            
            # 2. Check if already terminal (idempotency)
            if event.is_terminal():
                logger.info(f"WebhookEvent already terminal: {event_id}, status={event.status}")
                return True  # ACK
            
            # 3. Check max attempts
            if event.attempts >= MAX_ATTEMPTS:
                logger.warning(f"WebhookEvent max attempts exceeded: {event_id}, attempts={event.attempts}")
                await self._mark_failed(db, event)
                return True  # ACK
            
            # 4. Dispatch the webhook
            # Logging is now handled inside _send_webhook
            success, status_code, duration_ms, error_message = await self._send_webhook(
                db=db, 
                event=event, 
                is_manual=False
            )
            
            # 6. Handle result (Logging already done)
            if success:
                await self._mark_delivered(db, event)
                return True  # Success
            else:
                # Determine if error is retryable
                # Retryable: 5xx, timeout (None), 429 (rate limit)
                # NOT retryable: 4xx (except 429) - client errors won't be fixed by retrying
                is_retryable = self._is_retryable_error(status_code)
                
                if not is_retryable:
                    # Permanent failure - don't retry
                    logger.warning(
                        f"WebhookEvent permanent failure (non-retryable): "
                        f"event_id={event_id}, status={status_code}"
                    )
                    await self._mark_failed(db, event)
                    return True  # ACK - no point retrying
                
                # Increment attempts for transient errors
                await self._increment_attempts(db, event)
                
                if event.attempts >= MAX_ATTEMPTS:
                    await self._mark_failed(db, event)
                    return True  # Final failure, no more retries
                
                # Raise exception so Celery task will retry
                raise WebhookDeliveryException(
                    internal_message=f"Webhook delivery failed: {error_message}",
                    retryable=True,
                    status_code=status_code
                )

    async def mark_event_failed(self, event_id: str) -> None:
        """
        Mark a webhook event as permanently failed (public helper).
        Used by Celery task on_failure or when retries exhausted.
        """
        async with get_db_context() as db:
            event = await self._fetch_event(db, event_id)
            if event:
                await self._mark_failed(db, event)
            else:
                logger.warning(f"Cannot mark failed: WebhookEvent {event_id} not found")
    
    async def _fetch_event(self, db: AsyncSession, event_id: str) -> Optional[WebhookEvent]:
        """Fetch WebhookEvent by ID."""
        result = await db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()
    
    async def _send_webhook(
        self, 
        db: AsyncSession,
        event: WebhookEvent,
        is_manual: bool = False
    ) -> Tuple[bool, Optional[int], int, Optional[str]]:
        """
        Send HTTP POST request to webhook target and log the attempt.
        
        Args:
            db: Database session
            event: WebhookEvent object
            is_manual: True if manually triggered (adds 'trigger': 'manual' to payload)
            
        Returns:
            Tuple of (success, status_code, duration_ms, error_message)
        """
        # Generate attempt ID
        attempt_id = str(uuid.uuid4())
        
        # Enrich payload with job result data at delivery time
        enriched_payload = await self._enrich_payload(event)
        
        # Add manual mark if requested
        if is_manual:
            enriched_payload["trigger"] = "manual"
        
        # Sign payload
        signature = self._sign_payload(enriched_payload, event.secret)
        
        # Build headers
        headers = {
            'Content-Type': 'application/json',
            'X-Knowhere-Signature': signature,
            'X-Knowhere-Attempt-ID': attempt_id,
            'X-Knowhere-Timestamp': str(int(datetime.now(timezone.utc).timestamp())),
            'User-Agent': 'Knowhere-Webhook/1.0'
        }
        
        start_time = time.time()
        status_code = None
        error_message = None
        success = False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    event.target_url,
                    json=enriched_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
                ) as response:
                    duration_ms = int((time.time() - start_time) * 1000)
                    status_code = response.status
                    
                    if 200 <= response.status < 300:
                        logger.info(f"Webhook delivered: event_id={event.id}, status={response.status}")
                        success = True
                    else:
                        logger.warning(f"Webhook failed: event_id={event.id}, status={response.status}")
                        error_message = f"HTTP {response.status}"
                        success = False
                        
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Webhook timeout: event_id={event.id}")
            error_message = "Connection timeout"
            success = False
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Webhook error: event_id={event.id}, error={e}")
            error_message = str(e)
            success = False
            
        # Log delivery attempt
        # If manual, event_id is None to avoid FK violation
        log_event_id = None if is_manual else event.id
        
        try:
            # We construct log manually here to handle potential detached execution
            # or we can reuse _log_delivery but need to handle is_manual
            
            # Combine headers and payload
            combined_payload = {
                "header": headers,
                "payload": enriched_payload
            }

            log = WebhookLog(
                job_id=event.job_id,
                event_id=log_event_id,
                webhook_url=event.target_url,
                attempt_number=event.attempts + 1,
                request_payload=combined_payload,
                signature=signature,
                idempotency_key=str(uuid.uuid4()),
                response_status_code=status_code,
                error_message=error_message,
                duration_ms=duration_ms
            )
            db.add(log)
            # If auto-commit is needed? 
            # Dispatcher.dispatch uses passed 'db' session which is managed by 'async with get_db_context()'.
            # It commits inside _mark_delivered etc.
            # We should probably commit/flush here to persist log even if update fails?
            await db.commit() 
            
        except Exception as e:
            logger.error(f"Failed to log webhook delivery: {e}")
            
        return success, status_code, duration_ms, error_message
    
    async def _enrich_payload(self, event: WebhookEvent) -> Dict[str, Any]:
        """
        Enrich webhook payload with job result data at delivery time.
        
        For job.completed events:
        - Adds result_url (fresh download URL for result zip)
        - Adds result (inline payload with checksum/statistics)
        
        This ensures download URLs are generated fresh (they expire)
        and data is current at delivery time.
        """
        payload = dict(event.payload)  # Copy to avoid mutating stored payload
        
        # Only enrich completion events
        if payload.get("event") != "job.completed":
            return payload
        
        try:
            # Fetch job with result
            from shared.models.database.job import Job
            from sqlalchemy.orm import selectinload
            
            async with get_db_context() as db:
                result = await db.execute(
                    select(Job)
                    .options(selectinload(Job.job_result))
                    .where(Job.job_id == event.job_id)
                )
                job = result.scalar_one_or_none()
                
                if not job or not job.job_result:
                    logger.warning(f"Job or result not found for enrichment: job_id={event.job_id}")
                    return payload
                
                job_result = job.job_result
                
                # Add result_url (fresh download link)
                if job_result.result_s3_key:
                    from shared.services.storage.file_upload_service import FileUploadService
                    upload_service = FileUploadService()
                    url_info = await upload_service.generate_download_url(job_result.result_s3_key)
                    payload["result_url"] = url_info["download_url"]
                    logger.debug(f"Enriched payload with result_url for job {event.job_id}")
                
                # Add result (inline payload)
                if job_result.inline_payload:
                    payload["result"] = job_result.inline_payload
                
        except Exception as e:
            logger.error(f"Failed to enrich payload for event {event.id}: {e}")
            # Continue with original payload if enrichment fails
        
        return payload
    
    def _is_retryable_error(self, status_code: Optional[int]) -> bool:
        """
        Determine if an HTTP error is transient and worth retrying.
        
        Retryable (transient) errors:
        - None (timeout/network error)
        - 429 (rate limited)
        - 500-599 (server errors)
        
        NOT retryable (permanent) errors:
        - 400-428, 430-499 (client errors - won't be fixed by retrying)
        
        Args:
            status_code: HTTP response status code, or None for timeout/network
            
        Returns:
            True if error is transient and should be retried
        """
        if status_code is None:
            # Timeout or network error - always retry
            return True
        
        if status_code == 429:
            # Rate limited - retry after backoff
            return True
        
        if 500 <= status_code < 600:
            # Server error - transient, retry
            return True
        
        # 4xx (except 429) - client error, permanent failure
        # Examples: 400 Bad Request, 401 Unauthorized, 404 Not Found
        return False
    
    def _sign_payload(self, payload: Dict[str, Any], secret: str) -> str:
        """Generate HMAC-SHA256 signature."""
        payload_str = json.dumps(payload, separators=(',', ':'))
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    async def _log_delivery(
        self,
        db: AsyncSession,
        event: WebhookEvent,
        status_code: Optional[int],
        duration_ms: int,
        error_message: Optional[str],
        request_payload: Dict[str, Any],
        request_headers: Dict[str, Any]
    ) -> None:
        """Log delivery attempt to webhook_logs."""
        # Combine headers and payload into log storage
        combined_payload = {
            "header": request_headers,
            "payload": request_payload
        }

        log = WebhookLog(
            job_id=event.job_id,
            event_id=event.id,
            webhook_url=event.target_url,
            attempt_number=event.attempts + 1,
            request_payload=combined_payload,
            signature=self._sign_payload(event.payload, event.secret),
            idempotency_key=str(uuid.uuid4()),
            response_status_code=status_code,
            error_message=error_message,
            duration_ms=duration_ms
        )
        db.add(log)
        await db.commit()
    
    async def _mark_delivered(self, db: AsyncSession, event: WebhookEvent) -> None:
        """Mark event as delivered."""
        event.status = WebhookEventStatus.DELIVERED
        event.attempts += 1
        event.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"WebhookEvent delivered: {event.id}")
    
    async def _mark_failed(self, db: AsyncSession, event: WebhookEvent) -> None:
        """Mark event as failed (max retries exceeded)."""
        event.status = WebhookEventStatus.FAILED
        event.updated_at = datetime.utcnow()
        await db.commit()
        logger.warning(f"WebhookEvent failed permanently: {event.id}")
    
    async def _increment_attempts(self, db: AsyncSession, event: WebhookEvent) -> None:
        """Increment attempt count for failed delivery (Celery will retry)."""
        event.attempts += 1
        event.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"WebhookEvent attempt incremented: {event.id}, attempts={event.attempts}")


# Singleton instance
_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Get the singleton WebhookDispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = WebhookDispatcher()
    return _dispatcher

