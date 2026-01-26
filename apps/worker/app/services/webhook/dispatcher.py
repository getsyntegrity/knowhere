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
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db_context
from shared.core.database import get_db_context
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.models.database.webhook_log import WebhookLog
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException

from . import HTTP_TIMEOUT_SECONDS, MAX_ATTEMPTS


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
            success, status_code, duration_ms, error_message = await self._send_webhook(event)
            
            # 5. Log the delivery attempt
            await self._log_delivery(
                db=db,
                event=event,
                status_code=status_code,
                duration_ms=duration_ms,
                error_message=error_message
            )
            
            # 6. Handle result
            if success:
                await self._mark_delivered(db, event)
                return True  # Success
            else:
                # Increment attempts, Celery will handle retry
                await self._increment_attempts(db, event)
                
                if event.attempts >= MAX_ATTEMPTS:
                    await self._mark_failed(db, event)
                    return True  # Final failure, no more retries
                
                # Raise exception so Celery task will retry
                raise WebhookDeliveryException(
                    internal_message=f"Webhook delivery failed: {error_message}",
                    retryable=True
                )
    
    async def _fetch_event(self, db: AsyncSession, event_id: str) -> Optional[WebhookEvent]:
        """Fetch WebhookEvent by ID."""
        result = await db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()
    
    async def _send_webhook(self, event: WebhookEvent) -> Tuple[bool, Optional[int], int, Optional[str]]:
        """
        Send HTTP POST request to webhook target.
        
        Returns:
            Tuple of (success, status_code, duration_ms, error_message)
        """
        # Generate attempt ID
        attempt_id = str(uuid.uuid4())
        
        # Sign payload
        signature = self._sign_payload(event.payload, event.secret)
        
        # Build headers
        headers = {
            'Content-Type': 'application/json',
            'X-Knowhere-Signature': signature,
            'X-Knowhere-Attempt-ID': attempt_id,
            'X-Knowhere-Timestamp': str(int(datetime.utcnow().timestamp())),
            'User-Agent': 'Knowhere-Webhook/1.0'
        }
        
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    event.target_url,
                    json=event.payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
                ) as response:
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    if 200 <= response.status < 300:
                        logger.info(f"Webhook delivered: event_id={event.id}, status={response.status}")
                        return True, response.status, duration_ms, None
                    else:
                        logger.warning(f"Webhook failed: event_id={event.id}, status={response.status}")
                        return False, response.status, duration_ms, f"HTTP {response.status}"
                        
        except aiohttp.ClientTimeout:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Webhook timeout: event_id={event.id}")
            return False, None, duration_ms, "Connection timeout"
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Webhook error: event_id={event.id}, error={e}")
            return False, None, duration_ms, str(e)
    
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
        error_message: Optional[str]
    ) -> None:
        """Log delivery attempt to webhook_logs."""
        log = WebhookLog(
            job_id=event.job_id,
            event_id=event.id,
            webhook_url=event.target_url,
            attempt_number=event.attempts + 1,
            request_payload=event.payload,
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

