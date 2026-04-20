from __future__ import annotations

import asyncio
import inspect
from typing import Any

from loguru import logger
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db_context
from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.services.retrieval.graph_service import GraphQueryService, is_excluded_section
from shared.services.retrieval.cache_service import get_cached_retrieval_query_result, set_cached_retrieval_query_result
from shared.services.retrieval.hit_stats_service import record_retrieval_hits
from shared.services.storage.file_upload_service import FileUploadService
from shared.services.storage.result_artifact_service import (
    build_result_artifact_storage_key,
    normalize_client_result_artifact_path,
)
from shared.models.database.job_result import JobResult


_MEDIA_CHUNK_TYPES = {'image', 'table'}


def _filter_excluded_rows(
    rows: list[dict[str, Any]],
    *,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    excluded_documents = set(exclude_document_ids)
    for row in rows:
        document_id = row.get('document_id')
        if document_id in excluded_documents:
            continue
        if is_excluded_section(
            document_id=document_id,
            section_path=row.get('section_path'),
            exclude_sections=exclude_sections,
        ):
            continue
        filtered.append(row)
    return filtered


def _iter_connected_target_ids(row: dict[str, Any]) -> list[str]:
    metadata = row.get('chunk_metadata') or {}
    if not isinstance(metadata, dict):
        return []

    target_ids: list[str] = []
    for item in metadata.get('connect_to') or []:
        if not isinstance(item, dict):
            continue
        target_id = str(item.get('target') or '').strip()
        if target_id:
            target_ids.append(target_id)
    return target_ids


async def hydrate_connected_target_rows(
    *,
    db: AsyncSession | None,
    rows: list[dict[str, Any]],
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if db is None:
        return []

    existing_chunk_ids = {
        str(row.get('chunk_id') or '').strip()
        for row in rows
        if row.get('chunk_id')
    }
    target_ids_by_revision: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        chunk_type = str(row.get('chunk_type') or '').strip().split('\n', 1)[0].lower()
        if chunk_type != 'text':
            continue
        document_id = str(row.get('document_id') or '').strip()
        job_result_id = str(row.get('job_result_id') or '').strip()
        if not document_id or not job_result_id:
            continue
        for target_id in _iter_connected_target_ids(row):
            if target_id in existing_chunk_ids:
                continue
            target_ids_by_revision.setdefault((document_id, job_result_id), set()).add(target_id)

    if not target_ids_by_revision:
        return []

    revision_filters = [
        and_(
            DocumentChunk.document_id == document_id,
            DocumentChunk.job_result_id == job_result_id,
            DocumentChunk.chunk_id.in_(sorted(target_ids)),
        )
        for (document_id, job_result_id), target_ids in target_ids_by_revision.items()
        if target_ids
    ]
    if not revision_filters:
        return []

    stmt = (
        select(Document, DocumentChunk, DocumentSection, JobResult)
        .join(DocumentChunk, DocumentChunk.document_id == Document.document_id)
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .join(JobResult, JobResult.id == DocumentChunk.job_result_id)
        .where(or_(*revision_filters))
        .order_by(DocumentChunk.sort_order)
    )
    result = await db.execute(stmt)

    hydrated_rows: list[dict[str, Any]] = []
    for document, chunk, section, job_result in result.all():
        section_path = section.section_path if section else None
        hydrated_rows.append(
            {
                'document_id': document.document_id,
                'chunk_id': chunk.chunk_id,
                'section_id': chunk.section_id,
                'section_path': section_path,
                'source_file_name': document.source_file_name,
                'chunk_type': chunk.chunk_type,
                'content': chunk.content,
                'score': 0.0,
                'file_path': chunk.file_path,
                'chunk_metadata': chunk.chunk_metadata or {},
                'job_result_id': chunk.job_result_id,
                'job_id': job_result.job_id if job_result else None,
            }
        )

    return _filter_excluded_rows(
        hydrated_rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )


async def assemble_retrieval_results(
    *,
    db: AsyncSession | None = None,
    rows: list[dict[str, Any]],
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    filtered_rows = _filter_excluded_rows(
        rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )
    hydrated_rows = await hydrate_connected_target_rows(
        db=db,
        rows=filtered_rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )
    rows_by_chunk_id = {
        str(row.get('chunk_id') or ''): row
        for row in [*filtered_rows, *hydrated_rows]
        if row.get('chunk_id')
    }

    embedded_targets: set[str] = set()
    for row in filtered_rows:
        for target_id in _iter_connected_target_ids(row):
            if target_id in rows_by_chunk_id:
                embedded_targets.add(target_id)

    assembled: list[dict[str, Any]] = []
    for row in filtered_rows:
        if row.get('chunk_id') in embedded_targets:
            continue
        metadata = row.get('chunk_metadata') or {}
        if not isinstance(metadata, dict):
            metadata = {}
        assembled_row = dict(row)
        base_content = str(row.get('content') or '')
        if str(row.get('chunk_type') or '').strip().split('\n', 1)[0].lower() == 'text':
            related_parts: list[str] = []
            for target_id in _iter_connected_target_ids(row):
                target_row = rows_by_chunk_id.get(target_id)
                if not target_row:
                    continue
                if str(target_row.get('chunk_type') or '').strip().split('\n', 1)[0].lower() != 'table':
                    continue
                target_content = str(target_row.get('content') or '').strip()
                if target_content:
                    related_parts.append(target_content)
            if base_content and related_parts:
                assembled_row['content'] = '\n\n'.join([base_content, *related_parts])
            else:
                assembled_row['content'] = base_content
        else:
            assembled_row['content'] = base_content
        assembled.append(assembled_row)
    return assembled


async def list_canonical_chunks(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    stmt = (
        select(Document, DocumentChunk, DocumentSection, JobResult)
        .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id) & (DocumentChunk.job_result_id == Document.current_job_result_id))
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .join(JobResult, JobResult.id == DocumentChunk.job_result_id)
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
        .where(DocumentChunk.content.ilike(f'%{query}%'))
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
    for document, chunk, section, job_result in result_rows:
        section_path = section.section_path if section else None
        if is_excluded_section(
            document_id=document.document_id,
            section_path=section_path,
            exclude_sections=exclude_sections,
        ):
            continue
        rows.append({
            'document_id': document.document_id,
            'chunk_id': chunk.chunk_id,
            'section_id': chunk.section_id,
            'section_path': section_path,
            'source_file_name': document.source_file_name,
            'chunk_type': chunk.chunk_type,
            'content': chunk.content,
            'score': 1.0,
            'file_path': chunk.file_path,
            'chunk_metadata': chunk.chunk_metadata or {},
            'job_result_id': chunk.job_result_id,
            'job_id': job_result.job_id if job_result else None,
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
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    service = GraphQueryService()
    entry_document_ids = await service.find_entry_documents(
        db,
        user_id=user_id,
        namespace=namespace,
        query=query,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )
    return await service.collect_candidate_chunks(
        db,
        user_id=user_id,
        namespace=namespace,
        entry_document_ids=entry_document_ids,
        query=query,
        top_k=top_k,
        exclude_sections=exclude_sections,
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
    return {**row, 'citation': citation}


def _is_media_chunk(row: dict[str, Any]) -> bool:
    chunk_type = str(row.get('chunk_type') or '').strip().split('\n', 1)[0].lower()
    return chunk_type in _MEDIA_CHUNK_TYPES


async def generate_retrieval_asset_url(*, job_id: str, artifact_ref: str) -> str | None:
    storage_key = build_result_artifact_storage_key(job_id=job_id, artifact_ref=artifact_ref)
    url_info = await FileUploadService().generate_download_url(storage_key)
    if isinstance(url_info, dict):
        download_url = url_info.get('download_url')
        return str(download_url) if download_url else None
    return str(url_info) if url_info else None


def _is_client_result_artifact_ref(asset_ref: str | None) -> bool:
    return normalize_client_result_artifact_path(asset_ref) is not None


async def _to_public_response(response: dict[str, Any]) -> dict[str, Any]:
    public_response = {key: value for key, value in response.items() if key != 'results'}
    public_results: list[dict[str, Any]] = []
    for row in response.get('results', []):
        public_row = dict(row)
        public_row.pop('file_path', None)
        citation = row.get('citation')
        if isinstance(citation, dict):
            public_row['citation'] = dict(citation)
            public_row['citation'].pop('file_path', None)

        artifact_ref = row.get('file_path')
        if _is_media_chunk(row) and _is_client_result_artifact_ref(artifact_ref) and row.get('job_id'):
            try:
                asset_url = await generate_retrieval_asset_url(
                    job_id=str(row['job_id']),
                    artifact_ref=str(artifact_ref),
                )
                if asset_url:
                    public_row['asset_url'] = asset_url
            except Exception as e:
                logger.warning(f'Failed to generate retrieval asset URL (ignored): {e}')
        public_results.append(public_row)

    public_response['results'] = public_results
    return public_response


async def run_retrieval_query(
    *,
    db: AsyncSession,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
    graph_enabled: bool,
) -> dict[str, Any]:
    try:
        cache_version, cached = await get_cached_retrieval_query_result(
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
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
            return await _to_public_response(cached)
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
            exclude_sections=exclude_sections,
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
            exclude_sections=exclude_sections,
        )
        if inspect.isawaitable(lexical_rows):
            lexical_rows = await lexical_rows
        rows = list(lexical_rows)

    assembled_rows = await assemble_retrieval_results(
        db=db,
        rows=rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )
    results = [_with_citation(row) for row in assembled_rows]
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
            exclude_sections=exclude_sections,
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

    return await _to_public_response(response)
