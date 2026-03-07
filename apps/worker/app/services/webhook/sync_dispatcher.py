"""
Sync Webhook Dispatcher for gevent worker.

Worker path uses sync DB + sync HTTP to avoid asyncio event-loop coupling.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import urllib3
from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.services.storage.sync_storage_service import generate_download_url
from shared.core.database_sync import get_sync_db_context
from shared.core.exceptions.domain_exceptions import (
    SystemSettingInvalidException,
    SystemSettingMissingException,
)
from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException
from shared.models.database.job import Job
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.models.database.webhook_log import WebhookLog
from shared.models.database.webhook_secret import WebhookSecret, WebhookSecretStatus
from shared.services.encryption import get_fernet_service
from shared.services.webhook.validator import (
    WebhookValidationResult,
    validate_webhook_url,
)

# Constants
HTTP_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 6


class SyncWebhookDispatcher:
    """Synchronous webhook dispatcher used by gevent Celery workers."""

    def dispatch(self, event_id: str) -> bool:
        with get_sync_db_context() as db:
            event = self._fetch_event(db, event_id)
            if not event:
                logger.warning(f"WebhookEvent not found: {event_id}")
                return True

            if event.is_terminal():
                logger.info(f"WebhookEvent already terminal: {event_id}, status={event.status}")
                return True

            if event.attempts >= MAX_ATTEMPTS:
                logger.warning(f"WebhookEvent max attempts exceeded: {event_id}, attempts={event.attempts}")
                self._mark_failed(db, event)
                return True

            success, status_code, _duration_ms, error_message = self._send_webhook(
                db=db,
                event=event,
                is_manual=False,
            )

            if success:
                self._mark_delivered(db, event)
                return True

            if not self._is_retryable_error(status_code):
                logger.warning(
                    f"WebhookEvent permanent failure (non-retryable): "
                    f"event_id={event_id}, status={status_code}"
                )
                self._mark_failed(db, event)
                return True

            self._increment_attempts(db, event)
            if event.attempts >= MAX_ATTEMPTS:
                self._mark_failed(db, event)
                return True

            raise WebhookDeliveryException(
                internal_message=f"Webhook delivery failed: {error_message}",
                retryable=True,
                status_code=status_code,
            )

    def mark_event_failed(self, event_id: str) -> None:
        with get_sync_db_context() as db:
            event = self._fetch_event(db, event_id)
            if not event:
                logger.warning(f"Cannot mark failed: WebhookEvent {event_id} not found")
                return
            self._mark_failed(db, event)

    def _fetch_event(self, db: Session, event_id: str) -> Optional[WebhookEvent]:
        result = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
        return result.scalar_one_or_none()

    def _post_webhook_pinned(
        self,
        *,
        target_url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        pinned_ip: str,
        original_hostname: str,
    ) -> Tuple[int, str]:
        parsed = urlparse(target_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers = dict(headers)
        request_headers["Host"] = original_hostname

        timeout = urllib3.Timeout(connect=HTTP_TIMEOUT_SECONDS, read=HTTP_TIMEOUT_SECONDS)
        pool: urllib3.HTTPConnectionPool
        if parsed.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                host=pinned_ip,
                port=port,
                timeout=timeout,
                assert_hostname=original_hostname,
                server_hostname=original_hostname,
                cert_reqs="CERT_REQUIRED",
            )
        else:
            pool = urllib3.HTTPConnectionPool(host=pinned_ip, port=port, timeout=timeout)

        try:
            response = pool.request(
                "POST",
                path,
                body=body,
                headers=request_headers,
                redirect=False,
                preload_content=True,
            )
            response_body = response.data.decode("utf-8", errors="replace")
            return int(response.status), response_body
        finally:
            pool.close()

    def _send_webhook(
        self,
        *,
        db: Session,
        event: WebhookEvent,
        is_manual: bool = False,
    ) -> Tuple[bool, Optional[int], int, Optional[str]]:
        attempt_id = str(uuid.uuid4())

        validation: WebhookValidationResult = validate_webhook_url(event.target_url)
        if not validation.is_valid:
            logger.warning(f"SSRF validation failed: event_id={event.id}, error={validation.error_message}")
            return False, 400, 0, f"SSRF: {validation.error_message}"

        enriched_payload = self._enrich_payload(db, event)
        if is_manual:
            enriched_payload["trigger"] = "manual"

        user_id = self._get_job_owner(db, event.job_id)
        if not user_id:
            logger.warning(f"Could not resolve secret: Job {event.job_id} has no user_id")
            return False, 424, 0, "Secret resolution failed"

        try:
            secret = self._resolve_secret(db, user_id, event.target_url)
        except (SystemSettingMissingException, SystemSettingInvalidException) as exc:
            logger.error(f"Configuration error during secret resolution: {exc}")
            return False, 424, 0, f"Configuration Error: {exc}"
        except Exception as exc:
            logger.error(f"Secret resolution failed: {exc}")
            return False, 424, 0, "Secret resolution failed"

        if not secret:
            logger.error(f"No secret found or created for event {event.id}")
            return False, 424, 0, "Secret resolution failed"

        signature = self._sign_payload(enriched_payload, secret)
        headers = {
            "Content-Type": "application/json",
            "X-Knowhere-Signature": signature,
            "X-Knowhere-Attempt-ID": attempt_id,
            "User-Agent": "Knowhere-Webhook/1.0",
        }

        start_time = time.time()
        status_code: Optional[int] = None
        response_body: Optional[str] = None
        error_message: Optional[str] = None
        success = False

        try:
            status_code, response_body = self._post_webhook_pinned(
                target_url=event.target_url,
                payload=enriched_payload,
                headers=headers,
                pinned_ip=validation.validated_ip or "",
                original_hostname=validation.hostname or "",
            )
            if 200 <= status_code < 300:
                success = True
                logger.info(f"Webhook delivered: event_id={event.id}, status={status_code}")
            elif 300 <= status_code < 400:
                success = False
                error_message = f"Redirect blocked: HTTP {status_code}"
                logger.warning(
                    f"Webhook redirect blocked (SSRF protection): "
                    f"event_id={event.id}, status={status_code}"
                )
            else:
                success = False
                error_message = f"HTTP {status_code}"
                logger.warning(f"Webhook failed: event_id={event.id}, status={status_code}")
        except urllib3.exceptions.TimeoutError:
            error_message = "Connection timeout"
            success = False
            logger.error(f"Webhook timeout: event_id={event.id}")
        except Exception as exc:
            error_message = str(exc)
            success = False
            logger.error(f"Webhook error: event_id={event.id}, error={exc}")

        duration_ms = int((time.time() - start_time) * 1000)
        log_event_id = None if is_manual else event.id

        try:
            log = WebhookLog(
                job_id=event.job_id,
                event_id=log_event_id,
                webhook_url=event.target_url,
                attempt_number=event.attempts + 1,
                request_payload={"header": headers, "payload": enriched_payload},
                signature=signature,
                idempotency_key=str(uuid.uuid4()),
                response_status_code=status_code,
                response_body=response_body,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            db.add(log)
            db.commit()
        except Exception as exc:
            logger.error(f"Failed to log webhook delivery: {exc}")
            db.rollback()

        return success, status_code, duration_ms, error_message

    def _enrich_payload(self, db: Session, event: WebhookEvent) -> Dict[str, Any]:
        payload = dict(event.payload)
        if payload.get("event") != "job.completed":
            return payload

        try:
            result = db.execute(
                select(Job)
                .options(selectinload(Job.job_result))
                .where(Job.job_id == event.job_id)
            )
            job = result.scalar_one_or_none()
            if not job or not job.job_result:
                logger.warning(f"Job or result not found for enrichment: job_id={event.job_id}")
                return payload

            job_result = job.job_result
            if job_result.result_s3_key:
                url_info = generate_download_url(job_result.result_s3_key)
                payload["result_url"] = url_info["download_url"]

            if job_result.inline_payload:
                payload["result"] = job_result.inline_payload
        except Exception as exc:
            logger.error(f"Failed to enrich payload for event {event.id}: {exc}")
        return payload

    def _get_job_owner(self, db: Session, job_id: str) -> Optional[str]:
        result = db.execute(select(Job.user_id).where(Job.job_id == job_id))
        return result.scalar_one_or_none()

    def _resolve_secret(self, db: Session, user_id: str, endpoint: str) -> Optional[str]:
        fernet = get_fernet_service()

        secret_obj: Optional[WebhookSecret] = None
        if endpoint:
            result = db.execute(
                select(WebhookSecret).where(
                    and_(
                        WebhookSecret.user_id == user_id,
                        WebhookSecret.endpoint == endpoint,
                        WebhookSecret.status == WebhookSecretStatus.ACTIVE,
                    )
                )
            )
            secret_obj = result.scalar_one_or_none()

        if secret_obj is None:
            result = db.execute(
                select(WebhookSecret).where(
                    and_(
                        WebhookSecret.user_id == user_id,
                        WebhookSecret.endpoint.is_(None),
                        WebhookSecret.status == WebhookSecretStatus.ACTIVE,
                    )
                )
            )
            secret_obj = result.scalar_one_or_none()

        if secret_obj is None:
            raw_secret = fernet.generate_webhook_secret()
            secret_obj = WebhookSecret(
                user_id=user_id,
                endpoint=endpoint,
                secret_encrypted=fernet.encrypt(raw_secret),
                status=WebhookSecretStatus.ACTIVE,
            )
            db.add(secret_obj)
            db.commit()
            db.refresh(secret_obj)

        secret_obj.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(secret_obj)
        decrypted = fernet.decrypt(secret_obj.secret_encrypted)
        return decrypted

    def _is_retryable_error(self, status_code: Optional[int]) -> bool:
        if status_code is None:
            return True
        if status_code == 429:
            return True
        if 500 <= status_code < 600:
            return True
        return False

    def _sign_payload(self, payload: Dict[str, Any], secret: str) -> str:
        timestamp = int(time.time())
        payload_str = json.dumps(payload, separators=(",", ":"))
        signed_content = f"{timestamp}.{payload_str}"
        signature = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    def _mark_delivered(self, db: Session, event: WebhookEvent) -> None:
        event.status = WebhookEventStatus.DELIVERED
        event.attempts += 1
        event.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        logger.info(f"WebhookEvent delivered: {event.id}")

    def _mark_failed(self, db: Session, event: WebhookEvent) -> None:
        event.status = WebhookEventStatus.FAILED
        event.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        logger.warning(f"WebhookEvent failed permanently: {event.id}")

    def _increment_attempts(self, db: Session, event: WebhookEvent) -> None:
        event.attempts += 1
        event.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        logger.info(f"WebhookEvent attempt incremented: {event.id}, attempts={event.attempts}")


_dispatcher: Optional[SyncWebhookDispatcher] = None


def get_sync_webhook_dispatcher() -> SyncWebhookDispatcher:
    """Get singleton sync webhook dispatcher."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SyncWebhookDispatcher()
    return _dispatcher

