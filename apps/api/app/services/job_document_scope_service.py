"""
Document-scope rules used by job creation/update flows.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from shared.core.exceptions.domain_exceptions import (
    NotFoundException,
    ValidationException,
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
