from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.core.database_sync import get_sync_db_context
from shared.core.exceptions.domain_exceptions import NotFoundException
from shared.models.database.job import Job
from shared.services.redis.redis_sync_service import (
    SyncJobInfoRedisService,
    SyncJobMetadataService,
)


@dataclass(frozen=True)
class UrlUploadContext:
    s3_key: str


def load_url_upload_context(job_id: str, redis_service: Any) -> UrlUploadContext:
    job_info_service = SyncJobInfoRedisService(redis_service)
    job_info = job_info_service.get_job_info(job_id)

    if job_info:
        raw_s3_key = job_info.get("s3_key")
    else:
        metadata_service = SyncJobMetadataService(redis_service)
        job_metadata = metadata_service.get_metadata(job_id)
        raw_s3_key = job_metadata.get("s3_key") if job_metadata else None

    if not raw_s3_key:
        logger.warning(
            f"URL upload JobInfo missing in Redis for job_id={job_id}; falling back to database"
        )
        raw_s3_key = _load_job_s3_key(job_id)

    if not raw_s3_key:
        raise NotFoundException(
            resource="JobInfo",
            resource_id="s3_key",
            internal_message=f"Missing s3_key in Redis or database for job_id={job_id}",
        )

    return UrlUploadContext(s3_key=str(raw_s3_key))


def _load_job_s3_key(job_id: str) -> str | None:
    with get_sync_db_context() as db:
        job = _select_job_row(db, job_id)
        if not job:
            return None
        return str(job.s3_key) if job.s3_key else None


def _select_job_row(db: Session, job_id: str) -> Job | None:
    return db.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
