"""Document API routes for canonical document lifecycle."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_service import DocumentService
from app.services.rate_limit.dependencies import CurrentUser, with_current_user
from shared.core.database import get_db
from shared.core.exceptions.domain_exceptions import NotFoundException

router = APIRouter(tags=["Documents"])

_document_service = DocumentService()


@router.get("")
async def list_documents(
    namespace: str | None = Query(None),
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    effective_namespace = namespace or "default"
    documents = await _document_service.list_documents(
        db,
        user_id=current_user.user_id,
        namespace=effective_namespace,
    )
    return {
        "namespace": effective_namespace,
        "documents": documents,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await _document_service.get_document(
        db,
        user_id=current_user.user_id,
        document_id=document_id,
    )
    if document is None:
        raise NotFoundException(
            resource="Document",
            resource_id=document_id,
            internal_message="Document not found",
        )
    return document


@router.post("/{document_id}:archive")
async def archive_document(
    document_id: str,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await _document_service.archive_document(
        db,
        user_id=current_user.user_id,
        document_id=document_id,
    )
    if document is None:
        raise NotFoundException(
            resource="Document",
            resource_id=document_id,
            internal_message="Document not found",
        )
    return document
