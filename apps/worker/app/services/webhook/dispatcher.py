"""
Webhook Dispatcher Service

Consumes webhook events from RabbitMQ and dispatches HTTP requests
with retry logic, HMAC signing, and delivery logging.
"""
import hashlib
import hmac
import json
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db_context
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.models.database.webhook_log import WebhookLog

from . import (
    BASE_DELAY_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    JITTER_FACTOR,
    MAX_ATTEMPTS,
    RETRY_LEVELS,
    WEBHOOK_RETRY_EXCHANGE,
)


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
                return True  # ACK
            else:
                # Schedule retry if attempts remaining
                if event.attempts < MAX_ATTEMPTS - 1:
                    await self._schedule_retry(db, event)
                    return True  # ACK - will be retried via DLX
                else:
                    await self._mark_failed(db, event)
                    return True  # ACK - final failure
    
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
    
    async def _schedule_retry(self, db: AsyncSession, event: WebhookEvent) -> None:
        """
        Update event for retry and calculate next retry time.
        
        The actual retry is handled by RabbitMQ DLX - we just update
        the database state here.
        """
        event.attempts += 1
        event.status = WebhookEventStatus.DELIVERING
        
        # Calculate next retry time with jitter
        delay_seconds = self._calculate_backoff(event.attempts)
        event.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        event.updated_at = datetime.utcnow()
        
        await db.commit()
        logger.info(f"WebhookEvent scheduled for retry: {event.id}, attempt={event.attempts}, next_retry_at={event.next_retry_at}")
    
    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Formula: base_delay * 2^(attempt-1) ± 10% jitter
        """
        base_delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        
        # Apply jitter (±10%)
        jitter = random.uniform(1 - JITTER_FACTOR, 1 + JITTER_FACTOR)
        delay = base_delay * jitter
        
        return delay
    
    def get_retry_queue_for_attempt(self, attempt: int) -> str:
        """
        Get the appropriate retry queue based on attempt number.
        
        Maps attempt number to retry level delays.
        """
        if attempt <= 1:
            return RETRY_LEVELS[0]["routing_key"]  # 1 min
        elif attempt <= 2:
            return RETRY_LEVELS[1]["routing_key"]  # 10 min
        elif attempt <= 3:
            return RETRY_LEVELS[2]["routing_key"]  # 30 min
        elif attempt <= 4:
            return RETRY_LEVELS[3]["routing_key"]  # 2 hours
        else:
            return RETRY_LEVELS[4]["routing_key"]  # 6 hours


# Singleton instance
_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Get the singleton WebhookDispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = WebhookDispatcher()
    return _dispatcher
