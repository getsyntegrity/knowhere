"""
Document-scope rules used by job creation/update flows.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from shared.core.exceptions.domain_exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from shared.core.state_machine.states import JobStatus
from shared.models.database.job import Job


ACTIVE_DOCUMENT_JOB_STATES = (
    JobStatus.WAITING_FILE.value,
    JobStatus.PENDING.value,
    JobStatus.RUNNING.value,
    JobStatus.CONVERTING.value,
)


def build_active_job_for_document_query(*, user_id: str, document_id: str):
    return (
        select(Job)
        .where(Job.user_id == user_id)
        .where(Job.status.in_(ACTIVE_DOCUMENT_JOB_STATES))
        .where(Job.job_metadata["document_id"].as_string() == document_id)
    )


async def find_active_job_for_document(
    db: AsyncSession,
    *,
    user_id: str,
    document_id: str,
):
    if not hasattr(db, "execute"):
        return None
    result = await db.execute(
        build_active_job_for_document_query(
            user_id=user_id,
            document_id=document_id,
        )
    )
    return result.scalar_one_or_none()


def is_active_document_job_unique_violation(exc: IntegrityError) -> bool:
    text = str(getattr(exc, "orig", exc))
    return "uq_jobs_user_active_document" in text


def raise_document_ingestion_conflict(
    *,
    document_id: str,
    active_job_id: Optional[str] = None,
) -> None:
    raise ConflictException(
        user_message="Another ingestion job for this document is already in progress",
        reason="ABORTED",
        resource="Document",
        resource_id=document_id,
        internal_message=(
            f"Concurrent ingestion blocked for document_id={document_id}; "
            f"active_job_id={active_job_id or 'unknown'}"
        ),
    )


async def resolve_effective_document_scope(
    db: AsyncSession,
    *,
    user_id: str,
    document_id: Optional[str],
    requested_namespace: Optional[str],
    repository: DocumentRepository | None = None,
) -> tuple[str, str]:
    if not document_id:
        return f"doc_{uuid.uuid4().hex[:12]}", requested_namespace or "default"

    document = await (repository or DocumentRepository()).get_document(
        db,
        document_id=document_id,
        user_id=user_id,
    )
    if document is None:
        raise NotFoundException(
            resource="Document",
            resource_id=document_id,
            internal_message=f"Document not found for update flow: {document_id}",
        )
    if requested_namespace and requested_namespace != document.namespace:
        raise ValidationException(
            user_message="namespace must match the existing document namespace",
            violations=[{"field": "namespace", "description": "Does not match existing document namespace"}],
        )
    return document.document_id, document.namespace
