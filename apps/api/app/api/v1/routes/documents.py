"""Document API routes for canonical document lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import inspect

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rate_limit.dependencies import with_current_user, CurrentUser
from shared.core.database import get_db
from shared.models.database.document import Document
from shared.services.retrieval.cache_service import invalidate_retrieval_cache_namespaces
from shared.services.retrieval.graph_service import DocumentGraphService, GraphScope

router = APIRouter(tags=["Documents"])


def _document_payload(document: Document) -> dict[str, Any]:
    return {
        'document_id': document.document_id,
        'namespace': document.namespace,
        'status': document.status,
        'current_job_result_id': document.current_job_result_id,
        'source_file_name': document.source_file_name,
        'created_at': document.created_at.isoformat() if document.created_at else None,
        'updated_at': document.updated_at.isoformat() if document.updated_at else None,
        'archived_at': document.archived_at.isoformat() if document.archived_at else None,
    }


async def list_canonical_documents(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .order_by(Document.updated_at.desc())
    )
    scalar_result = result.scalars()
    if inspect.isawaitable(scalar_result):
        scalar_result = await scalar_result
    documents = scalar_result.all()
    if inspect.isawaitable(documents):
        documents = await documents
    if not isinstance(documents, (list, tuple)):
        return []
    return [_document_payload(document) for document in documents]


async def get_canonical_document(
    db: AsyncSession,
    *,
    user_id: str,
    document_id: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .where(Document.document_id == document_id)
    )
    document = result.scalar_one_or_none()
    if inspect.isawaitable(document):
        document = await document
    if not isinstance(document, Document):
        return None
    return _document_payload(document)


async def archive_canonical_document(
    db: AsyncSession,
    *,
    user_id: str,
    document_id: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .where(Document.document_id == document_id)
    )
    document = result.scalar_one_or_none()
    if inspect.isawaitable(document):
        document = await document
    if not isinstance(document, Document):
        return None
    document.status = 'archived'
    document.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    graph_service = DocumentGraphService()
    previous_namespace = document.namespace

    await db.run_sync(
        lambda sync_db: graph_service.remove_document_graph(
            sync_db,
            scope=GraphScope(user_id=user_id, namespace=document.namespace),
            document_id=document_id,
        )
    )
    await db.commit()
    try:
        await invalidate_retrieval_cache_namespaces(user_id=user_id, namespaces=[previous_namespace])
    except Exception:
        pass
    return _document_payload(document)


@router.get('')
async def list_documents(
    namespace: str | None = Query(None),
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    effective_namespace = namespace or 'default'
    documents = list_canonical_documents(
        db,
        user_id=current_user.user_id,
        namespace=effective_namespace,
    )
    if inspect.isawaitable(documents):
        documents = await documents
    return {
        'namespace': effective_namespace,
        'documents': documents,
    }


@router.get('/{document_id}')
async def get_document(
    document_id: str,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = get_canonical_document(db, user_id=current_user.user_id, document_id=document_id)
    if inspect.isawaitable(document):
        document = await document
    if document is None:
        return {'document_id': document_id, 'status': 'not_found'}
    return document


@router.post('/{document_id}:archive')
async def archive_document(
    document_id: str,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = archive_canonical_document(db, user_id=current_user.user_id, document_id=document_id)
    if inspect.isawaitable(document):
        document = await document
    if document is None:
        return {'document_id': document_id, 'status': 'not_found'}
    return document
