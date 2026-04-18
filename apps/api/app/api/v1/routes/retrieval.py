"""Retrieval API routes for lexical + graph-routing baseline."""

from __future__ import annotations

from typing import Any
import inspect

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rate_limit.dependencies import with_current_user, CurrentUser
from shared.core.database import get_db
from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.services.retrieval.graph_service import GraphQueryService

router = APIRouter(tags=["Retrieval"])


class RetrievalQueryRequest(BaseModel):
    namespace: str | None = Field(None, description="Effective namespace; defaults to default")
    query: str
    top_k: int = 10
    exclude_document_ids: list[str] = Field(default_factory=list)
    graph_enabled: bool = False


async def list_canonical_chunks(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
) -> list[dict[str, Any]]:
    stmt = (
        select(Document, DocumentChunk, DocumentSection)
        .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id) & (DocumentChunk.job_result_id == Document.current_job_result_id))
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
        .where(DocumentChunk.text.ilike(f'%{query}%'))
        .order_by(DocumentChunk.sort_order)
        .limit(top_k)
    )
    if exclude_document_ids:
        stmt = stmt.where(Document.document_id.not_in(exclude_document_ids))
    result = await db.execute(stmt)
    result_rows = result.all()
    if inspect.isawaitable(result_rows):
        result_rows = await result_rows
    if not isinstance(result_rows, (list, tuple)):
        return []
    rows = []
    for document, chunk, section in result_rows:
        rows.append({
            'document_id': document.document_id,
            'chunk_id': chunk.chunk_id,
            'section_id': chunk.section_id,
            'section_path': section.section_path if section else None,
            'source_file_name': document.source_file_name,
            'chunk_type': chunk.chunk_type,
            'text': chunk.text,
            'score': 1.0,
            'file_path': chunk.file_path,
        })
    return rows


async def list_graph_routed_chunks(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
) -> list[dict[str, Any]]:
    service = GraphQueryService()
    entry_document_ids = await service.find_entry_documents(
        db,
        user_id=user_id,
        namespace=namespace,
        query=query,
        exclude_document_ids=exclude_document_ids,
    )
    return await service.collect_candidate_chunks(
        db,
        user_id=user_id,
        namespace=namespace,
        entry_document_ids=entry_document_ids,
        query=query,
        top_k=top_k,
    )


def _with_citation(row: dict[str, Any]) -> dict[str, Any]:
    citation = {
        'document_id': row.get('document_id'),
        'chunk_id': row.get('chunk_id'),
        'source_file_name': row.get('source_file_name'),
        'section_path': row.get('section_path'),
    }
    if row.get('file_path'):
        citation['file_path'] = row['file_path']
    return {**row, 'citation': citation}


@router.post('/query')
async def query_retrieval(
    payload: RetrievalQueryRequest,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    namespace = payload.namespace or 'default'
    rows: list[dict[str, Any]] = []
    graph_used = False
    if payload.graph_enabled:
        graph_rows = list_graph_routed_chunks(
            db,
            user_id=current_user.user_id,
            namespace=namespace,
            query=payload.query,
            top_k=payload.top_k,
            exclude_document_ids=payload.exclude_document_ids,
        )
        if inspect.isawaitable(graph_rows):
            graph_rows = await graph_rows
        if graph_rows:
            rows = list(graph_rows)
            graph_used = True

    if not rows:
        lexical_rows = list_canonical_chunks(
            db,
            user_id=current_user.user_id,
            namespace=namespace,
            query=payload.query,
            top_k=payload.top_k,
            exclude_document_ids=payload.exclude_document_ids,
        )
        if inspect.isawaitable(lexical_rows):
            lexical_rows = await lexical_rows
        rows = list(lexical_rows)

    return {
        'namespace': namespace,
        'query': payload.query,
        'results': [_with_citation(row) for row in rows],
        'graph_enabled': graph_used,
    }
