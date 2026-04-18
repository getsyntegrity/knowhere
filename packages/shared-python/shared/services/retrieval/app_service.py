from __future__ import annotations

import asyncio
import inspect
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db_context
from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.services.retrieval.graph_service import GraphQueryService
from shared.services.retrieval.cache_service import get_cached_retrieval_query_result, set_cached_retrieval_query_result
from shared.services.retrieval.hit_stats_service import record_retrieval_hits


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


def schedule_retrieval_hit_stats_update(*, user_id: str, namespace: str, results: list[dict[str, Any]]) -> None:
    try:
        asyncio.create_task(
            _record_retrieval_hit_stats_best_effort(
                user_id=user_id,
                namespace=namespace,
                results=results,
            ),
            name=f'retrieval_hit_stats:{user_id}:{namespace}',
        )
    except Exception as e:
        logger.warning(f'Failed to schedule retrieval hit stats update (ignored): {e}')


async def _record_retrieval_hit_stats_best_effort(*, user_id: str, namespace: str, results: list[dict[str, Any]]) -> None:
    try:
        async with get_db_context() as db:
            await record_retrieval_hits(db, user_id=user_id, namespace=namespace, results=results)
            await db.commit()
    except Exception as e:
        logger.warning(f'Failed to record retrieval hit stats (ignored): {e}')


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


async def run_retrieval_query(
    *,
    db: AsyncSession,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    graph_enabled: bool,
) -> dict[str, Any]:
    try:
        cache_version, cached = await get_cached_retrieval_query_result(
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            graph_enabled=graph_enabled,
        )
        if cached:
            try:
                schedule_retrieval_hit_stats_update(
                    user_id=user_id,
                    namespace=namespace,
                    results=cached.get('results', []),
                )
            except Exception as e:
                logger.warning(f'Failed to trigger retrieval hit stats update (ignored): {e}')
            return cached
    except Exception as e:
        logger.warning(f'Failed to read retrieval cache (ignored): {e}')

    rows: list[dict[str, Any]] = []
    graph_used = False
    if graph_enabled:
        graph_rows = list_graph_routed_chunks(
            db,
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
        )
        if inspect.isawaitable(graph_rows):
            graph_rows = await graph_rows
        if graph_rows:
            rows = list(graph_rows)
            graph_used = True

    if not rows:
        lexical_rows = list_canonical_chunks(
            db,
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
        )
        if inspect.isawaitable(lexical_rows):
            lexical_rows = await lexical_rows
        rows = list(lexical_rows)

    results = [_with_citation(row) for row in rows]
    response = {
        'namespace': namespace,
        'query': query,
        'results': results,
        'graph_enabled': graph_used,
    }

    try:
        await set_cached_retrieval_query_result(
            user_id=user_id,
            namespace=namespace,
            version=cache_version,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            graph_enabled=graph_enabled,
            response=response,
        )
    except Exception as e:
        logger.warning(f'Failed to write retrieval cache (ignored): {e}')

    try:
        schedule_retrieval_hit_stats_update(
            user_id=user_id,
            namespace=namespace,
            results=results,
        )
    except Exception as e:
        logger.warning(f'Failed to trigger retrieval hit stats update (ignored): {e}')

    return response
