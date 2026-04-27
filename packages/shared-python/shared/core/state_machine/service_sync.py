"""
Sync state machine service — core transition logic for Worker (gevent).

Mirror of ``AsyncStateMachineService`` using synchronous SQLAlchemy
``Session`` and ``SyncRedisService``.  Every public method signature matches
the async variant minus ``await``.
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import cast, literal, select, update
from sqlalchemy.orm import Session, load_only

from shared.core.state_machine.states import (
    JobStatus,
    is_valid_transition,
)
from shared.models.database.job import Job
from shared.models.database.job_state_audit_log import JobStateAuditLog
from shared.services.redis.redis_sync_service import SyncRedisServiceFactory
from shared.utils.error_details import normalize_error_details
from shared.utils.json_utils import make_json_safe
from shared.utils.redis_key_builder import RedisKeyType, redis_key_builder


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SyncStateMachineService:
    """Sync state machine service — used by the Worker (gevent + psycopg2)."""

    def __init__(self, redis_service=None):
        self.redis = redis_service or SyncRedisServiceFactory.get_service()

    # ── Public API ──────────────────────────────────────────────────────

    def transition(
        self,
        db: Session,
        job_id: str,
        to_state: str,
        transition_reason: str = "normal_transition",
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Execute an optimistic-lock state transition with up to 3 retries."""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                job = self._get_job_with_version(db, job_id)
                if not job:
                    logger.error(f"Job {job_id} does not exist")
                    return False

                if not is_valid_transition(job.status, to_state):
                    logger.warning(
                        f"Job {job_id}: illegal transition {job.status} → {to_state}, rejected"
                    )
                    return False

                old_state = job.status
                old_version = job.version

                self._record_audit_log(
                    db,
                    job_id,
                    old_state,
                    to_state,
                    transition_reason,
                    operator_id,
                    operator_type,
                    metadata,
                )

                success = self._cas_update_state(db, job_id, to_state, old_version)
                if success:
                    self._update_redis_cache(job_id, to_state, metadata)
                    db.flush()
                    logger.info(
                        f"Job {job_id} state transition: {old_state} → {to_state}"
                    )
                    return True

                if attempt < max_retries - 1:
                    logger.warning(
                        f"Job {job_id} CAS conflict, retry {attempt + 1}/{max_retries}"
                    )
                    import gevent

                    gevent.sleep(0.1 * (2**attempt))
                    continue
                else:
                    logger.error(f"Job {job_id} CAS retries exhausted")
                    return False

            except Exception as e:
                logger.error(f"Job {job_id} transition failed: {e}")
                try:
                    if db.is_active:
                        db.rollback()
                except Exception as rollback_err:
                    logger.warning(f"Job {job_id} rollback failed: {rollback_err}")
                return False

        return False

    def mark_failed(
        self,
        db: Session,
        job_id: str,
        error_message: str,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mark a job as failed with error information."""
        try:
            normalized_details = normalize_error_details(error_details)
            self._update_job_error(
                db,
                job_id,
                error_message,
                error_code,
                normalized_details,
            )

            transition_metadata = (metadata or {}).copy()
            transition_metadata["error_message"] = error_message
            transition_metadata["error_code"] = error_code
            if normalized_details:
                transition_metadata["error_details"] = normalized_details

            return self.transition(
                db,
                job_id,
                JobStatus.FAILED.value,
                "mark_failed",
                operator_id,
                "system",
                transition_metadata,
            )
        except Exception as e:
            logger.error(f"Failed to mark Job {job_id} as failed: {e}")
            return False

    def mark_completed(
        self,
        db: Session,
        job_id: str,
        result_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None,
    ) -> bool:
        """Mark a job as completed."""
        try:
            return self.transition(
                db,
                job_id,
                JobStatus.DONE.value,
                "mark_completed",
                operator_id,
                "system",
                result_metadata,
            )
        except Exception as e:
            logger.error(f"Failed to mark Job {job_id} as completed: {e}")
            return False

    # ── Private helpers ─────────────────────────────────────────────────

    def _get_job(self, db: Session, job_id: str) -> Optional[Job]:
        result = db.execute(select(Job).where(Job.job_id == job_id))
        return result.scalar_one_or_none()

    def _get_job_with_version(self, db: Session, job_id: str) -> Optional[Job]:
        result = db.execute(
            select(Job)
            .options(load_only(Job.job_id, Job.status, Job.version))
            .where(Job.job_id == job_id)
        )
        return result.scalar_one_or_none()

    def _cas_update_state(
        self,
        db: Session,
        job_id: str,
        to_state: str,
        old_version: int,
    ) -> bool:
        result = db.execute(
            update(Job)
            .where(Job.job_id == job_id, Job.version == old_version)
            .values(
                status=to_state,
                version=old_version + 1,
                updated_at=_utc_now_naive(),
            )
        )
        return result.rowcount > 0

    def _record_audit_log(
        self,
        db: Session,
        job_id: str,
        from_state: str,
        to_state: str,
        transition_reason: str,
        operator_id: Optional[str],
        operator_type: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        serialized = None
        if metadata:
            try:
                serialized = make_json_safe(metadata)
            except Exception as e:
                logger.warning(f"Metadata serialization failed: {e}")
                serialized = {"error": "metadata_serialization_failed"}

        db.add(
            JobStateAuditLog(
                job_id=job_id,
                from_state=from_state,
                to_state=to_state,
                transition_reason=transition_reason,
                operator_id=operator_id,
                operator_type=operator_type,
                transition_metadata=serialized,
            )
        )

    def _update_job_error(
        self,
        db: Session,
        job_id: str,
        error_message: str,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            update_values: Dict[str, Any] = {
                "error_message": error_message,
                "error_code": error_code,
            }

            if error_details:
                import json as _json

                from sqlalchemy import func
                from sqlalchemy.dialects.postgresql import JSONB
                from sqlalchemy.dialects.postgresql import array as pg_array

                update_values["job_metadata"] = func.jsonb_set(
                    func.coalesce(Job.job_metadata.cast(JSONB), cast(literal("{}"), JSONB)),
                    pg_array(["error_details"]),
                    cast(literal(_json.dumps(error_details)), JSONB),
                )

            db.execute(update(Job).where(Job.job_id == job_id).values(**update_values))
        except Exception as e:
            logger.error(f"Failed to update Job {job_id} error info: {e}")

    def _update_redis_cache(
        self,
        job_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        try:
            status_key = redis_key_builder.task_status(job_id)
            self.redis.set(
                status_key,
                status,
                ttl=redis_key_builder.get_key_ttl(RedisKeyType.TASK),
            )

            progress_key = redis_key_builder.task_progress(job_id)
            progress_data: Dict[str, Any] = {
                "status": status,
                "timestamp": str(int(time.time())),
            }
            if metadata:
                try:
                    progress_data.update(make_json_safe(metadata))
                except Exception as e:
                    logger.warning(f"Metadata serialization skipped: {e}")

            self.redis.hset(progress_key, mapping=progress_data)
            self.redis.expire(
                progress_key,
                redis_key_builder.get_key_ttl(RedisKeyType.TASK),
            )
        except Exception as e:
            logger.error(f"Redis cache update failed for Job {job_id}: {e}")
