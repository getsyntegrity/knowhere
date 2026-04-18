"""
Sync Job Lifecycle Service for Celery worker (gevent pool).

Encapsulates the complete job success/failure finalization that previously
used an API-side broker consumer. The worker now writes directly to the
database in a single atomic transaction,
using the same transactional outbox pattern for webhook events.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.core.database_sync import get_sync_db_context
from shared.core.response import build_standard_error_response
from shared.core.state_machine.service_sync import SyncStateMachineService
from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.models.database.job import Job
from shared.models.database.job_result import JobChunk, JobResult
from shared.models.database.knowledge_base import ContentBase
from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.services.billing.credits_sync_service import SyncCreditsService
from shared.services.redis.redis_sync_service import (
    SyncRedisServiceFactory,
)
from shared.utils.error_details import normalize_error_details
from shared.utils.redis_key_builder import RedisKeyType, redis_key_builder


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SyncJobLifecycleService:
    """Manages job lifecycle transitions in the worker process (sync/gevent).

    Implements the direct worker → DB write path for job completion and failure.
    """

    def __init__(self) -> None:
        self._state_machine = SyncStateMachineService()

    # ── Public API ──────────────────────────────────────────────────────

    def finalize_job_success(
        self,
        job_id: str,
        result_s3_key: str,
        checksum: str,
        zip_size: int,
        chunks: Optional[List[Dict[str, Any]]] = None,
        stored_count: int = 0,
        kb_records: Optional[List[Dict[str, Any]]] = None,
        delivery_mode: str = "url",
    ) -> Dict[str, Any]:
        """Finalize a successful job in a single atomic transaction.

        Steps (all within one DB transaction):
            1. Save KB records (bulk insert)
            2. Upsert JobResult + replace chunks
            3. Mark job as DONE via state machine (CAS)
            4. Create WebhookEvent if webhook_enabled
            5. COMMIT
            6. Post-commit: enqueue webhook
        """
        logger.info(f"Finalizing job success: job_id={job_id}")

        with get_sync_db_context() as db:
            try:
                if kb_records:
                    self._bulk_insert_kb_records(db, kb_records)
                    logger.info(f"Job {job_id} KB records inserted: count={len(kb_records)}")

                inline_payload = {"checksum": checksum}
                job_result = self._upsert_job_result(
                    db, job_id, delivery_mode,
                    inline_payload=inline_payload,
                    result_s3_key=result_s3_key,
                    result_size=zip_size,
                )

                normalized_chunks = chunks or []
                self._replace_chunks(db, job_result.id, normalized_chunks)
                self._publish_document_state(
                    db,
                    job_id=job_id,
                    job_result_id=job_result.id,
                    chunks=normalized_chunks,
                )

                transition_ok = self._state_machine.mark_completed(
                    db, job_id,
                    result_metadata={
                        "storage_completed": True,
                        "stored_count": stored_count,
                        "delivery_mode": delivery_mode,
                    },
                )
                if not transition_ok:
                    logger.error(f"Job {job_id} mark_completed transition failed")
                    db.rollback()
                    return {"status": "failed", "job_id": job_id, "reason": "state_transition_failed"}

                webhook_event = self._maybe_create_webhook_event(
                    db, job_id, event_type="job.completed",
                )

                db.commit()
                logger.info(f"Job {job_id} success transaction committed")

                self._post_commit_enqueue_webhook(webhook_event)

                return {
                    "status": "success",
                    "job_id": job_id,
                    "stored_count": stored_count,
                }

            except Exception as exc:
                logger.error(f"Failed to finalize job success {job_id}: {exc}")
                db.rollback()
                raise

    def finalize_job_failure(
        self,
        job_id: str,
        error_message: str,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
        should_refund: bool = False,
    ) -> bool:
        """Finalize a failed job in a single atomic transaction.

        Steps (all within one DB transaction):
            1. Mark job as FAILED via state machine (CAS + error fields)
            2. Refund credits if needed
            3. Create WebhookEvent if webhook_enabled
            4. COMMIT
            5. Post-commit: enqueue webhook
        """
        logger.info(f"Finalizing job failure: job_id={job_id}")

        with get_sync_db_context() as db:
            try:
                transition_ok = self._state_machine.mark_failed(
                    db, job_id, error_message,
                    error_code=error_code,
                    error_details=error_details,
                )
                if not transition_ok:
                    logger.error(f"Job {job_id} mark_failed transition failed")
                    db.rollback()
                    return False

                if should_refund:
                    self._try_refund_credits(db, job_id)

                normalized_error_details = normalize_error_details(error_details)
                webhook_event = self._maybe_create_webhook_event(
                    db, job_id, event_type="job.failed",
                    extra_payload={
                        "error": build_standard_error_response(
                            code=error_code,
                            message=error_message,
                            request_id=job_id,
                            details=normalized_error_details,
                        ),
                    },
                )

                db.commit()
                logger.info(f"Job {job_id} failure transaction committed")

                self._post_commit_enqueue_webhook(webhook_event)

                return True

            except Exception as exc:
                logger.error(f"Failed to finalize job failure {job_id}: {exc}")
                db.rollback()
                raise

    def update_progress(
        self,
        job_id: str,
        progress: int,
        message: str = "",
    ) -> bool:
        """Write job progress directly to Redis (replaces publish_progress_update).

        Best-effort — failures are logged but do not raise.
        """
        try:
            redis_service = SyncRedisServiceFactory.get_service()
            task_ttl = redis_key_builder.get_key_ttl(RedisKeyType.TASK)
            progress_key = redis_service._build_key(
                redis_key_builder.task_progress(job_id)
            )

            pipe = redis_service.pipeline()
            pipe.hset(progress_key, mapping={
                "progress": str(progress),
                "message": message,
                "timestamp": str(int(time.time())),
            })
            pipe.expire(progress_key, task_ttl)
            pipe.execute()
            return True
        except Exception as exc:
            logger.warning(f"Failed to update progress for job {job_id}: {exc}")
            return False

    # ── Private helpers ─────────────────────────────────────────────────

    def _upsert_job_result(
        self,
        db: Session,
        job_id: str,
        delivery_mode: str,
        *,
        inline_payload: Optional[Dict[str, Any]] = None,
        result_s3_key: Optional[str] = None,
        result_size: Optional[int] = None,
    ) -> JobResult:
        """Create or update JobResult row."""
        result = db.execute(
            select(JobResult).where(JobResult.job_id == job_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.delivery_mode = delivery_mode
            existing.document_metadata = {}
            existing.inline_payload = inline_payload
            existing.result_s3_key = result_s3_key
            existing.result_size = result_size
            db.flush()
            return existing

        job_result = JobResult(
            job_id=job_id,
            delivery_mode=delivery_mode,
            document_metadata={},
            inline_payload=inline_payload,
            result_s3_key=result_s3_key,
            result_size=result_size,
        )
        db.add(job_result)
        db.flush()
        return job_result

    def _replace_chunks(
        self,
        db: Session,
        job_result_id: str,
        chunks: List[Dict[str, Any]],
    ) -> None:
        """Delete existing chunks and insert new ones."""
        db.execute(delete(JobChunk).where(JobChunk.job_result_id == job_result_id))

        if not chunks:
            db.flush()
            return

        chunk_models = []
        for index, chunk in enumerate(chunks):
            chunk_identifier = chunk.get("chunk_id") or str(uuid4())
            chunk_models.append(JobChunk(
                job_result_id=job_result_id,
                chunk_id=chunk_identifier,
                chunk_type=chunk.get("type", "paragraph"),
                text=chunk.get("text"),
                path=chunk.get("metadata", {}).get("path"),
                chunk_metadata=chunk.get("metadata"),
                sort_order=chunk.get("order", index),
            ))
        db.add_all(chunk_models)
        db.flush()

    def _publish_document_state(
        self,
        db: Session,
        *,
        job_id: str,
        job_result_id: str,
        chunks: List[Dict[str, Any]],
    ) -> None:
        """Publish canonical document, section, and chunk rows for retrieval."""
        job = db.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
        if not job:
            logger.warning(f"Job not found for document publication: {job_id}")
            return

        metadata = job.job_metadata or {}
        namespace = metadata.get("namespace") or "default"
        document_id = metadata.get("document_id")
        source_file_name = metadata.get("source_file_name") or metadata.get("file_name")

        document = None
        if document_id:
            document = db.execute(
                select(Document).where(
                    Document.document_id == document_id,
                    Document.user_id == str(job.user_id),
                )
            ).scalar_one_or_none()

        if document is None:
            document = Document(
                document_id=document_id or f"doc_{uuid4().hex[:12]}",
                user_id=str(job.user_id),
                namespace=namespace,
                status="active",
                current_job_result_id=job_result_id,
                source_file_name=source_file_name,
            )
            db.add(document)
        else:
            document.namespace = namespace
            document.status = "active"
            document.current_job_result_id = job_result_id
            document.source_file_name = source_file_name or document.source_file_name
            document.updated_at = _utc_now_naive()

        db.flush()
        document_id = document.document_id
        result = db.execute(select(JobResult).where(JobResult.id == job_result_id))
        job_result = result.scalar_one_or_none()
        if job_result:
            job_result.document_id = document_id

        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        db.execute(delete(DocumentSection).where(DocumentSection.document_id == document_id))
        db.flush()

        sections_by_path: Dict[str, DocumentSection] = {}
        for index, chunk in enumerate(chunks):
            metadata = chunk.get("metadata") or {}
            source_path = metadata.get("path") or chunk.get("path")
            section_path = self._section_path_from_chunk_path(source_path)
            section = sections_by_path.get(section_path)
            if section is None:
                section = DocumentSection(
                    user_id=str(job.user_id),
                    namespace=namespace,
                    document_id=document_id,
                    job_result_id=job_result_id,
                    section_path=section_path,
                    section_title=section_path.split(" / ")[-1] if section_path else None,
                    section_level=len([part for part in section_path.split(" / ") if part]),
                    section_metadata={},
                    sort_order=len(sections_by_path),
                )
                db.add(section)
                db.flush()
                sections_by_path[section_path] = section

            chunk_id = chunk.get("chunk_id") or f"chunk_{uuid4().hex[:12]}"
            db.add(DocumentChunk(
                id=f"dchk_{uuid4().hex[:12]}",
                chunk_id=chunk_id,
                user_id=str(job.user_id),
                namespace=namespace,
                document_id=document_id,
                job_result_id=job_result_id,
                section_id=section.section_id,
                chunk_type=chunk.get("type") or chunk.get("chunk_type") or "text",
                text=chunk.get("text") or chunk.get("content"),
                source_chunk_path=source_path,
                file_path=metadata.get("file_path") or chunk.get("file_path"),
                chunk_metadata=metadata,
                sort_order=chunk.get("order", index),
            ))

        db.flush()

    @staticmethod
    def _section_path_from_chunk_path(source_path: Optional[str]) -> str:
        if not source_path:
            return "Root"
        parts = [part.strip() for part in source_path.split("-->") if part.strip()]
        if len(parts) <= 1:
            return "Root"
        section_parts = parts[1:]
        return " / ".join(section_parts) or "Root"

    def _bulk_insert_kb_records(
        self,
        db: Session,
        kb_records: List[Dict[str, Any]],
    ) -> None:
        """Bulk insert knowledge base records."""
        from shared.models.database.knowledge_base import KBPydantic

        object_mappings = []
        for rec in kb_records:
            kb = KBPydantic(**rec)
            data_dict = kb.model_dump()
            processed = {
                key: (value if value is not None else "")
                for key, value in data_dict.items()
            }
            object_mappings.append(processed)

        if object_mappings:
            db.bulk_insert_mappings(ContentBase, object_mappings)
            db.flush()

    def _maybe_create_webhook_event(
        self,
        db: Session,
        job_id: str,
        event_type: str,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[WebhookEvent]:
        """Create a WebhookEvent if the job has webhooks enabled."""
        result = db.execute(
            select(Job).where(Job.job_id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            logger.warning(f"Job not found for webhook check: {job_id}")
            return None

        webhook_url = getattr(job, "webhook_url", None)
        if not job.webhook_enabled or not webhook_url:
            return None

        status = "completed" if event_type == "job.completed" else "failed"
        timestamp_key = f"{status}_at"
        payload: Dict[str, Any] = {
            "event": event_type,
            "job_id": job_id,
            "status": status,
            timestamp_key: _utc_now_naive().isoformat(),
        }
        if extra_payload:
            payload.update(extra_payload)

        event = WebhookEvent(
            job_id=job_id,
            target_url=webhook_url,
            payload=payload,
            status=WebhookEventStatus.PENDING,
            attempts=0,
        )
        db.add(event)
        db.flush()
        logger.info(f"WebhookEvent created: event_id={event.id}, job_id={job_id}")
        return event

    def _try_refund_credits(self, db: Session, job_id: str) -> None:
        """Attempt to refund credits for a failed job."""
        try:
            result = db.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                return

            amount = getattr(job, "credits_charged", 0) or 0
            billing_status = getattr(job, "billing_status", "")
            if amount <= 0 or billing_status != "charged":
                return

            credits_service = SyncCreditsService()
            credits_service.refund_job_credits(
                session=db,
                user_id=str(job.user_id),
                amount=amount,
                job_id=job_id,
            )
            job.billing_status = "refunded"
            logger.info(f"Refunded {amount} credits for job {job_id}")
        except Exception as exc:
            logger.error(f"Credit refund failed for job {job_id}: {exc}")

    def _post_commit_enqueue_webhook(
        self, webhook_event: Optional[WebhookEvent],
    ) -> None:
        """Publish a persisted webhook via QStash after commit (best-effort)."""
        if not webhook_event:
            return

        try:
            from shared.services.webhook.qstash_publisher import get_qstash_webhook_publisher

            publisher = get_qstash_webhook_publisher()
            message_id = publisher.publish_event(webhook_event.id)
            if not message_id:
                logger.warning(
                    f"Webhook publish failed after commit: event_id={webhook_event.id}"
                )
                return
            logger.info(
                f"Webhook published after commit: event_id={webhook_event.id}, "
                f"message_id={message_id}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to publish webhook after commit (event persisted): "
                f"event_id={webhook_event.id}, error={exc}"
            )


# Module-level singleton
_lifecycle_service: Optional[SyncJobLifecycleService] = None


def get_sync_job_lifecycle_service() -> SyncJobLifecycleService:
    """Get the singleton sync job lifecycle service."""
    global _lifecycle_service
    if _lifecycle_service is None:
        _lifecycle_service = SyncJobLifecycleService()
    return _lifecycle_service
