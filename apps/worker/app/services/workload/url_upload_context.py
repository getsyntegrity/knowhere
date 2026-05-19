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
    metadata_service = SyncJobMetadataService(redis_service)

    if job_info:
        raw_s3_key = job_info.get("s3_key")
    else:
        job_metadata = metadata_service.get_metadata(job_id)
        raw_s3_key = job_metadata.get("s3_key") if job_metadata else None

    if not raw_s3_key:
        logger.warning(
            f"URL upload JobInfo missing in Redis for job_id={job_id}; falling back to database"
        )
        job_row = _load_job_row(job_id)
        if job_row and job_row.s3_key:
            raw_s3_key = str(job_row.s3_key)
            job_info_service.save_job_info(
                job_id,
                {
                    "job_id": job_id,
                    "s3_key": raw_s3_key,
                    "user_id": str(job_row.user_id) if job_row.user_id else None,
                    "webhook_enabled": bool(job_row.webhook_enabled),
                    "job_type": "document_ingestion",
                    "source_type": job_row.source_type,
                },
            )
            if isinstance(job_row.job_metadata, dict) and job_row.job_metadata:
                metadata_service.save_metadata(job_id, job_row.job_metadata)

    if not raw_s3_key:
        raise NotFoundException(
            resource="JobInfo",
            resource_id="s3_key",
            internal_message=f"Missing s3_key in Redis or database for job_id={job_id}",
        )

    return UrlUploadContext(s3_key=str(raw_s3_key))


def _load_job_row(job_id: str) -> Job | None:
    with get_sync_db_context() as db:
        return _select_job_row(db, job_id)


def _select_job_row(db: Session, job_id: str) -> Job | None:
    return db.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
