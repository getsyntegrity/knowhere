from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db_context
from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.services.retrieval.graph_service import GraphQueryService, is_excluded_section
from shared.services.retrieval.cache_service import get_cached_retrieval_query_result, set_cached_retrieval_query_result
from shared.services.retrieval.hit_stats_service import record_retrieval_hits
from shared.services.storage.result_storage import get_result_storage
from shared.models.database.job_result import JobResult


_MEDIA_CHUNK_TYPES = {'image', 'table'}

_RRF_K = 60
_CHANNEL_WEIGHT_PATH = 1.0
_CHANNEL_WEIGHT_CONTENT = 2.0
_CHANNEL_WEIGHT_TERM = 1.5
_INTERNAL_RECALL_K_MULTIPLIER = 2

_PUBLIC_RESULT_FIELDS = {
    'document_id', 'chunk_id', 'section_id', 'section_path',
    'source_file_name', 'chunk_type', 'content', 'score',
    'asset_url', 'citation',
}


def _normalize_chunk_type(raw: str | None) -> str:
    return str(raw or '').strip().split('\n', 1)[0].lower()


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
        if _normalize_chunk_type(row.get('chunk_type')) != 'text':
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
                'sort_order': chunk.sort_order,
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
        if _normalize_chunk_type(row.get('chunk_type')) == 'text':
            connected_targets: list[tuple[int, str]] = []
            for target_id in _iter_connected_target_ids(row):
                target_row = rows_by_chunk_id.get(target_id)
                if not target_row:
                    continue
                if _normalize_chunk_type(target_row.get('chunk_type')) != 'table':
                    continue
                target_content = str(target_row.get('content') or '').strip()
                if target_content:
                    sort_key = int(target_row.get('sort_order', 0) or 0)
                    connected_targets.append((sort_key, target_content))
            connected_targets.sort(key=lambda x: x[0])
            related_parts = [content for _, content in connected_targets]
            if base_content and related_parts:
                assembled_row['content'] = '\n\n'.join([base_content, *related_parts])
            else:
                assembled_row['content'] = base_content
        else:
            assembled_row['content'] = base_content
        assembled.append(assembled_row)
    return assembled


async def list_lexical_chunks(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Independent lexical retrieval: path + content channels via ILIKE."""
    recall_k = top_k * _INTERNAL_RECALL_K_MULTIPLIER
    excluded_docs = set(exclude_document_ids)

    base_stmt = (
        select(Document, DocumentChunk, DocumentSection, JobResult)
        .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id) & (DocumentChunk.job_result_id == Document.current_job_result_id))
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .join(JobResult, JobResult.id == DocumentChunk.job_result_id)
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
    )
    if excluded_docs:
        base_stmt = base_stmt.where(Document.document_id.notin_(list(excluded_docs)))

    like = f'%{query}%'
    content_stmt = base_stmt.where(DocumentChunk.content_lexical_text.ilike(like)).order_by(DocumentChunk.sort_order).limit(recall_k)
    path_stmt = base_stmt.where(DocumentChunk.path_lexical_text.ilike(like)).order_by(DocumentChunk.sort_order).limit(recall_k)

    content_result, path_result = await asyncio.gather(
        db.execute(content_stmt),
        db.execute(path_stmt),
    )

    def _to_rows(result, channel_score: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for document, chunk, section, job_result in result.all():
            section_path = section.section_path if section else None
            if is_excluded_section(document_id=document.document_id, section_path=section_path, exclude_sections=exclude_sections):
                continue
            rows.append({
                'document_id': document.document_id,
                'chunk_id': chunk.chunk_id,
                'section_id': chunk.section_id,
                'section_path': section_path,
                'source_file_name': document.source_file_name,
                'chunk_type': chunk.chunk_type,
                'content': chunk.content,
                'score': channel_score,
                'file_path': chunk.file_path,
                'chunk_metadata': chunk.chunk_metadata or {},
                'job_result_id': chunk.job_result_id,
                'job_id': job_result.job_id if job_result else None,
            })
        return rows

    content_rows = _to_rows(content_result, _CHANNEL_WEIGHT_CONTENT)
    path_rows = _to_rows(path_result, _CHANNEL_WEIGHT_PATH)
    return content_rows, path_rows


def _grep_search_rows(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Term/grep channel: exact substring matching with scoring from knowhere-kb."""
    import re
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    units = re.findall(r'[一-鿿]+|[a-zA-Z0-9]+', query_lower)
    units = [u for u in units if len(u) > 1]

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        haystack = (str(row.get('content') or '') + ' ' + str(row.get('section_path') or '')).lower()
        if query_lower in haystack:
            scored.append((100.0, row))
        elif units:
            hit_count = sum(1 for u in units if u in haystack)
            if hit_count > 0:
                scored.append((float(hit_count), row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [dict(row, score=score) for score, row in scored]


def merge_channels_rrf(
    channels: list[list[dict[str, Any]]],
    weights: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion across multiple retrieval channels."""
    score_dict: dict[str, float] = {}
    row_by_chunk_id: dict[str, dict[str, Any]] = {}

    for channel_idx, channel_rows in enumerate(channels):
        w = weights[channel_idx] if channel_idx < len(weights) else 1.0
        for rank, row in enumerate(channel_rows):
            chunk_id = str(row.get('chunk_id') or '')
            if not chunk_id:
                continue
            rrf_score = w / (_RRF_K + rank + 1)
            score_dict[chunk_id] = score_dict.get(chunk_id, 0.0) + rrf_score
            if chunk_id not in row_by_chunk_id:
                row_by_chunk_id[chunk_id] = row

    ranked = sorted(score_dict.items(), key=lambda x: x[1], reverse=True)
    results: list[dict[str, Any]] = []
    for chunk_id, fused_score in ranked[:top_k]:
        row = row_by_chunk_id[chunk_id]
        results.append(dict(row, score=round(fused_score, 6)))
    return results


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
        top_k=top_k * _INTERNAL_RECALL_K_MULTIPLIER,
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
    return _normalize_chunk_type(row.get('chunk_type')) in _MEDIA_CHUNK_TYPES


async def generate_retrieval_asset_url(*, job_id: str, artifact_ref: str) -> str | None:
    return get_result_storage().generate_artifact_url(job_id=job_id, artifact_ref=artifact_ref)


def _is_client_result_artifact_ref(asset_ref: str | None) -> bool:
    return get_result_storage().normalize_artifact_ref(asset_ref) is not None


async def _to_public_response(response: dict[str, Any]) -> dict[str, Any]:
    public_response = {
        'namespace': response.get('namespace'),
        'query': response.get('query'),
        'graph_enabled': response.get('graph_enabled', True),
        'results': [],
    }
    public_results: list[dict[str, Any]] = []
    for row in response.get('results', []):
        artifact_ref = row.get('file_path')
        asset_url = None
        if _is_media_chunk(row) and _is_client_result_artifact_ref(artifact_ref) and row.get('job_id'):
            try:
                asset_url = await generate_retrieval_asset_url(
                    job_id=str(row['job_id']),
                    artifact_ref=str(artifact_ref),
                )
            except Exception as e:
                logger.warning(f'Failed to generate retrieval asset URL (ignored): {e}')

        public_row: dict[str, Any] = {}
        for field in _PUBLIC_RESULT_FIELDS:
            if field == 'asset_url':
                if asset_url:
                    public_row['asset_url'] = asset_url
            elif field == 'citation':
                citation = row.get('citation')
                if isinstance(citation, dict):
                    public_row['citation'] = {
                        'document_id': citation.get('document_id'),
                        'chunk_id': citation.get('chunk_id'),
                        'source_file_name': citation.get('source_file_name'),
                        'section_path': citation.get('section_path'),
                    }
            elif field in row:
                public_row[field] = row[field]
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
    graph_enabled: bool = True,
) -> dict[str, Any]:
    cache_version: int | None = None
    try:
        cache_version, cached = await get_cached_retrieval_query_result(
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
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

    graph_actually_used = False
    channels: list[list[dict[str, Any]]] = []
    channel_weights: list[float] = []

    content_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []

    async def _run_lexical() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return await list_lexical_chunks(
            db,
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
        )

    if graph_enabled:
        graph_coro = list_graph_routed_chunks(
            db,
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
        )
        try:
            (content_rows, path_rows), graph_rows = await asyncio.gather(
                _run_lexical(),
                graph_coro,
            )
            if graph_rows:
                graph_actually_used = True
                channels.append(graph_rows)
                channel_weights.append(_CHANNEL_WEIGHT_CONTENT)
        except Exception as e:
            logger.warning(f'Graph retrieval failed, falling back to lexical only: {e}')
            content_rows, path_rows = await _run_lexical()
    else:
        content_rows, path_rows = await _run_lexical()

    channels.append(content_rows)
    channel_weights.append(_CHANNEL_WEIGHT_CONTENT)
    channels.append(path_rows)
    channel_weights.append(_CHANNEL_WEIGHT_PATH)

    all_lexical_rows = [*content_rows, *path_rows]
    seen_chunk_ids: set[str] = set()
    deduped_rows: list[dict[str, Any]] = []
    for row in all_lexical_rows:
        cid = str(row.get('chunk_id') or '')
        if cid and cid not in seen_chunk_ids:
            seen_chunk_ids.add(cid)
            deduped_rows.append(row)
    term_rows = _grep_search_rows(deduped_rows, query)
    if term_rows:
        channels.append(term_rows)
        channel_weights.append(_CHANNEL_WEIGHT_TERM)

    fused_rows = merge_channels_rrf(channels, channel_weights, top_k)

    assembled_rows = await assemble_retrieval_results(
        db=db,
        rows=fused_rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )
    results = [_with_citation(row) for row in assembled_rows]
    response = {
        'namespace': namespace,
        'query': query,
        'results': results,
        'graph_enabled': graph_actually_used,
    }

    if cache_version is not None:
        try:
            await set_cached_retrieval_query_result(
                user_id=user_id,
                namespace=namespace,
                version=cache_version,
                query=query,
                top_k=top_k,
                exclude_document_ids=exclude_document_ids,
                exclude_sections=exclude_sections,
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
