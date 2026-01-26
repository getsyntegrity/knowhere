"""
Webhook Delivery Service (API Service Dedicated)
Responsible for sending Webhook requests and logging
"""
import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
from shared.core.config import settings
from shared.core.database import get_db_context
from app.repositories.webhook_repository import WebhookRepository
from loguru import logger


class WebhookService:
    """Webhook Delivery Service"""
    
    def __init__(self):
        self.webhook_repo = WebhookRepository()
        self.signing_secret = getattr(settings, 'WEBHOOK_SIGNING_SECRET', 'default_secret')
        self.max_retries = 5
        self.base_delay = 1  # Base delay (seconds)
        self.max_delay = 60  # Max delay (seconds)
    
    async def send_webhook(
        self, 
        job_id: str, 
        webhook_url: str, 
        payload: Dict[str, Any],
        attempt_number: int = 1,
        event_id: Optional[str] = None,
        secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send Webhook request.
        
        Args:
            job_id: Job ID
            webhook_url: Webhook destination URL
            payload: JSON payload to send
            attempt_number: Current attempt number (1-6)
            event_id: Associated WebhookEvent ID (optional)
            secret: HMAC signing secret (optional, uses global default if None)
            
        Returns:
            Dict: Result with success status, status_code, etc.
        """
        # Generate idempotency key (X-Knowhere-Attempt-ID per design spec)
        idempotency_key = str(uuid.uuid4())
        
        # Use provided secret or fallback to global default
        signing_secret = secret if secret else self.signing_secret
        signature = self._generate_signature(payload, signing_secret)
        
        import time
        start_time = time.time()
        
        try:
            # Build request headers (using X-Knowhere-* per design spec)
            headers = {
                'Content-Type': 'application/json',
                'X-Knowhere-Signature': signature,
                'X-Knowhere-Attempt-ID': idempotency_key,
                'X-Knowhere-Timestamp': str(int(datetime.utcnow().timestamp())),
                'User-Agent': 'Knowhere-Webhook/1.0'
            }
            
            # Send request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_body = await response.text()
                    
                    # Log Webhook attempt
                    log = await self._log_webhook_attempt(
                        job_id=job_id,
                        webhook_url=webhook_url,
                        attempt_number=attempt_number,
                        request_payload=payload,
                        signature=signature,
                        idempotency_key=idempotency_key,
                        response_status_code=response.status,
                        response_body=response_body,
                        error_message=None
                    )
                    
                    delivery_id = str(log.id) if log else None
                    
                    if 200 <= response.status < 300:
                        logger.info(f"Webhook sent successfully: job_id={job_id}, status={response.status}")
                        return {
                            "success": True,
                            "status_code": response.status,
                            "response_body": response_body,
                            "attempt_number": attempt_number,
                            "delivery_id": delivery_id
                        }
                    else:
                        logger.warning(f"Webhook failed: job_id={job_id}, status={response.status}")
                        return {
                            "success": False,
                            "status_code": response.status,
                            "response_body": response_body,
                            "attempt_number": attempt_number,
                            "delivery_id": delivery_id
                        }
                        
        except asyncio.TimeoutError:
            error_msg = "Webhook request timeout"
            logger.error(f"Webhook timeout: job_id={job_id}")
            log = await self._log_webhook_attempt(
                job_id, webhook_url, attempt_number, payload, 
                signature, idempotency_key, None, None, error_msg
            )
            delivery_id = str(log.id) if log else None
            return {"success": False, "error": error_msg, "attempt_number": attempt_number, "delivery_id": delivery_id}
            
        except Exception as e:
            error_msg = f"Webhook exception: {str(e)}"
            logger.error(f"Webhook exception: job_id={job_id}, error={e}")
            log = await self._log_webhook_attempt(
                job_id, webhook_url, attempt_number, payload,
                signature, idempotency_key, None, None, error_msg
            )
            delivery_id = str(log.id) if log else None
            return {"success": False, "error": error_msg, "attempt_number": attempt_number, "delivery_id": delivery_id}
    
    def _generate_signature(self, payload: Dict[str, Any], secret: str) -> str:
        """
        Generate HMAC-SHA256 signature.
        
        Per design spec: signs the raw JSON body (not sorted keys).
        Format: sha256=<hex_digest>
        """
        # Use compact JSON format without sorting per design spec
        payload_str = json.dumps(payload, separators=(',', ':'))
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate retry delay (exponential backoff + jitter)"""
        import random

        # Exponential backoff
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        
        # Add jitter (±25%)
        jitter = random.uniform(0.75, 1.25)
        delay = delay * jitter
        
        return delay
    
    async def _log_webhook_attempt(
        self,
        job_id: str,
        webhook_url: str,
        attempt_number: int,
        request_payload: Dict[str, Any],
        signature: str,
        idempotency_key: str,
        response_status_code: Optional[int],
        response_body: Optional[str],
        error_message: Optional[str]
    ):
        """Log Webhook Attempt"""
        try:
            async with get_db_context() as db:
                return await self.webhook_repo.log_webhook_attempt(
                    db=db,
                    job_id=job_id,
                    webhook_url=webhook_url,
                    attempt_number=attempt_number,
                    request_payload=request_payload,
                    signature=signature,
                    idempotency_key=idempotency_key,
                    response_status_code=response_status_code,
                    response_body=response_body,
                    error_message=error_message
                )
        except Exception as e:
            logger.error(f"Failed to log Webhook: {e}")
            return None
