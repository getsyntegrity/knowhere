"""
QStash callback endpoints.

These endpoints receive delivery status from Upstash QStash after it
delivers (or fails to deliver) a webhook to the customer's endpoint.

Both endpoints verify the QStash JWT signature before processing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Response
from loguru import logger
from sqlalchemy import select

from shared.core.config import app_config
from shared.core.database_sync import get_sync_db_context
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.models.database.webhook_log import WebhookLog

router = APIRouter(tags=["QStash Callbacks"])


def _get_qstash_verification_url(callback_path: str, request_url: str) -> str:
    """Build the URL used for QStash signature verification.

    Prefer the configured public callback URL because ingress/TLS termination
    can make ``request.url`` appear as an internal ``http://`` URL.
    """
    callback_base_url = app_config.QSTASH_CALLBACK_BASE_URL

    if callback_base_url:
        return f"{callback_base_url.rstrip('/')}{callback_path}"

    return request_url


def _verify_qstash_signature(raw_body: bytes, signature: str, url: str) -> bool:
    """Verify the QStash JWT signature on an inbound callback."""
    current_key = app_config.QSTASH_CURRENT_SIGNING_KEY
    next_key = app_config.QSTASH_NEXT_SIGNING_KEY

    if not current_key or not next_key:
        logger.error("QStash signing keys not configured — rejecting callback")
        return False

    try:
        from qstash import Receiver

        receiver = Receiver(
            current_signing_key=current_key,
            next_signing_key=next_key,
        )
        receiver.verify(
            body=raw_body.decode("utf-8"),
            signature=signature,
            url=url,
        )
        return True
    except Exception as exc:
        logger.warning(
            "QStash signature verification failed: error_type={error_type}, url={url}",
            error_type=type(exc).__name__,
            url=url,
        )
        return False


def _extract_callback_data(body: bytes) -> Dict[str, Any]:
    """Parse the QStash callback body."""
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return {"raw": body.decode("utf-8", errors="replace")}


def _find_event_id(data: Dict[str, Any]) -> Optional[str]:
    """Extract the Knowhere event ID from QStash sourceHeader."""
    source_header = data.get("sourceHeader", {}) or {}
    event_id = source_header.get("X-Knowhere-Event-Id") or source_header.get("x-knowhere-event-id")
    if not event_id:
        for key, value in source_header.items():
            if key.lower() == "x-knowhere-event-id":
                event_id = value[0] if isinstance(value, list) else value
                break
    return event_id


def _process_qstash_callback(
    data: Dict[str, Any],
    event_id: str,
    terminal_status: str,
    log_label: str,
) -> Response:
    """Shared logic for both success and failure QStash callbacks.

    Fetches the WebhookEvent, updates its status, and writes a WebhookLog entry.
    """
    response_status = data.get("status")
    response_body = data.get("body", "")
    qstash_message_id = data.get("sourceMessageId")
    retried = data.get("retried", 0)
    error_message = data.get("error", response_body) if terminal_status == WebhookEventStatus.FAILED else None

    with get_sync_db_context() as db:
        event = db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        ).scalar_one_or_none()

        if not event:
            logger.warning(f"QStash {log_label}: event {event_id} not found in DB")
            return Response(status_code=200, content="OK (event not found)")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        event.status = terminal_status
        event.attempts = retried + 1
        event.updated_at = now

        log = WebhookLog(
            job_id=event.job_id,
            event_id=event.id,
            webhook_url=event.target_url,
            attempt_number=retried + 1,
            request_payload=event.payload,
            signature="",
            idempotency_key=qstash_message_id or "",
            response_status_code=int(response_status) if response_status else None,
            response_body=response_body[:4096] if response_body else None,
            error_message=str(error_message)[:4096] if error_message else None,
            duration_ms=0,
        )
        db.add(log)
        db.commit()

    return Response(status_code=200, content="OK")


@router.post("/qstash/callback")
async def handle_qstash_callback(request: Request) -> Response:
    """Handle QStash success callback after webhook delivery."""
    raw_body = await request.body()
    signature = request.headers.get("upstash-signature", "")
    verification_url = _get_qstash_verification_url(
        "/webhooks/qstash/callback",
        str(request.url),
    )

    if not _verify_qstash_signature(raw_body, signature, verification_url):
        return Response(status_code=401, content="Invalid signature")

    data = _extract_callback_data(raw_body)
    event_id = _find_event_id(data)

    if not event_id:
        logger.warning("QStash callback: missing event_id, cannot correlate")
        return Response(status_code=200, content="OK (no event_id)")

    retried = data.get("retried", 0)
    logger.info(
        f"QStash callback: event_id={event_id}, status={data.get('status')}, "
        f"retried={retried}, qstash_message_id={data.get('sourceMessageId')}"
    )

    return _process_qstash_callback(data, event_id, WebhookEventStatus.DELIVERED, "callback")


@router.post("/qstash/failure")
async def handle_qstash_failure(request: Request) -> Response:
    """Handle QStash failure callback after all retries exhausted."""
    raw_body = await request.body()
    signature = request.headers.get("upstash-signature", "")
    verification_url = _get_qstash_verification_url(
        "/webhooks/qstash/failure",
        str(request.url),
    )

    if not _verify_qstash_signature(raw_body, signature, verification_url):
        return Response(status_code=401, content="Invalid signature")

    data = _extract_callback_data(raw_body)
    event_id = _find_event_id(data)

    if not event_id:
        logger.warning("QStash failure callback: missing event_id, cannot correlate")
        return Response(status_code=200, content="OK (no event_id)")

    retried = data.get("retried", 0)
    max_retries = data.get("maxRetries", 0)
    logger.warning(
        f"QStash failure: event_id={event_id}, status={data.get('status')}, "
        f"retried={retried}/{max_retries}, qstash_message_id={data.get('sourceMessageId')}"
    )

    return _process_qstash_callback(data, event_id, WebhookEventStatus.FAILED, "failure")
