from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from loguru import logger
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db_context
from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.services.retrieval.agent_navigate import agent_navigate
from shared.services.retrieval.graph_service import GraphQueryService, is_excluded_section
from shared.services.retrieval.cache_service import get_cached_retrieval_query_result, set_cached_retrieval_query_result
from shared.services.retrieval.hit_stats_service import record_retrieval_hits
from shared.services.retrieval.llm_adapter import create_retrieval_llm_fn
from shared.services.retrieval.channels import path_channel, content_channel, term_channel
from shared.services.storage.result_storage import get_result_storage
from shared.models.database.job_result import JobResult


_MEDIA_CHUNK_TYPES = {'image', 'table'}

_RRF_K = 60
_CHANNEL_WEIGHT_PATH = 1.0
_CHANNEL_WEIGHT_CONTENT = 2.0
_CHANNEL_WEIGHT_TERM = 1.5
_INTERNAL_RECALL_K_MULTIPLIER = 2

_DATA_TYPE_ALLOWED_CHUNK_TYPES: dict[int, set[str] | None] = {
    1: None,
    2: {'text'},
    3: {'image'},
    4: {'table'},
    5: {'text', 'image'},
    6: {'text', 'table'},
}


def _resolve_allowed_chunk_types(data_type: int) -> set[str] | None:
    return _DATA_TYPE_ALLOWED_CHUNK_TYPES.get(data_type)


_PATH_REF_RE = re.compile(r'\[(?:images|tables)/[^\]\n]+\]')


def _clean_content(content: str) -> str:
    return _PATH_REF_RE.sub('', content).strip()

_PUBLIC_RESULT_FIELDS = {
    'chunk_type', 'content', 'score', 'asset_url',
}

_PUBLIC_SOURCE_FIELDS = {
    'document_id', 'source_file_name', 'section_path',
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
    allowed_chunk_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    filtered_rows = _filter_excluded_rows(
        rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
    )
    if allowed_chunk_types is not None:
        filtered_rows = [
            row for row in filtered_rows
            if _normalize_chunk_type(row.get('chunk_type')) in allowed_chunk_types
        ]
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
        assembled_row['content'] = _clean_content(assembled_row['content'])
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

    # AsyncSession is stateful and should not be shared across concurrent tasks.
    content_result = await db.execute(content_stmt)
    path_result = await db.execute(path_stmt)

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


def _merge_same_section_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        key = row.get('section_path') or row.get('chunk_id', '')
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    merged: list[dict[str, Any]] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue
        base = dict(group[0])
        base['content'] = '\n'.join(str(r.get('content', '')) for r in group)
        base['score'] = max(r.get('score', 0.0) for r in group)
        merged.append(base)
    return merged


def merge_channels_rrf(
    channels: list[list[dict[str, Any]]],
    weights: list[float],
    top_k: int,
    k: int = _RRF_K,
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
            rrf_score = w / (k + rank + 1)
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


def _to_public_source(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in _PUBLIC_SOURCE_FIELDS}


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
        'router_used': response.get('router_used'),
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
            elif field in row:
                public_row[field] = row[field]
        public_row['source'] = _to_public_source(row)
        public_results.append(public_row)

    public_response['results'] = public_results
    return public_response


def _union_graph_results(
    fused_rows: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Union graph-discovered chunks after RRF fusion (original KB pattern)."""
    existing_ids = {str(row.get("chunk_id") or "") for row in fused_rows}
    for row in graph_rows:
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id and chunk_id not in existing_ids:
            existing_ids.add(chunk_id)
            fused_rows.append(row)
    return fused_rows[:top_k]


async def _count_scoped_chunks(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    exclude_document_ids: list[str],
    allowed_chunk_types: set[str] | None,
) -> int:
    stmt = (
        select(func.count(DocumentChunk.id))
        .join(Document, (Document.document_id == DocumentChunk.document_id) & (Document.current_job_result_id == DocumentChunk.job_result_id))
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
    )
    if exclude_document_ids:
        stmt = stmt.where(Document.document_id.notin_(list(exclude_document_ids)))
    if allowed_chunk_types is not None:
        stmt = stmt.where(func.lower(DocumentChunk.chunk_type).in_(list(allowed_chunk_types)))
    result = await db.execute(stmt)
    return result.scalar() or 0


async def _load_all_scoped_chunks(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
    allowed_chunk_types: set[str] | None,
    signal_paths: list[str],
    filter_mode: str,
) -> list[dict[str, Any]]:
    stmt = (
        select(Document, DocumentChunk, DocumentSection, JobResult)
        .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id) & (DocumentChunk.job_result_id == Document.current_job_result_id))
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .join(JobResult, JobResult.id == DocumentChunk.job_result_id)
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
        .order_by(DocumentChunk.sort_order)
    )
    if exclude_document_ids:
        stmt = stmt.where(Document.document_id.notin_(list(exclude_document_ids)))
    if allowed_chunk_types is not None:
        stmt = stmt.where(func.lower(DocumentChunk.chunk_type).in_(list(allowed_chunk_types)))

    result = await db.execute(stmt)
    rows: list[dict[str, Any]] = []
    for document, chunk, section, job_result in result.all():
        section_path = section.section_path if section else None
        if is_excluded_section(document_id=document.document_id, section_path=section_path, exclude_sections=exclude_sections):
            continue
        if signal_paths and section_path:
            path_lower = section_path.lower()
            matches_any = any(kw.lower() in path_lower for kw in signal_paths)
            if filter_mode == 'keep' and not matches_any:
                continue
            if filter_mode == 'delete' and matches_any:
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
            'sort_order': chunk.sort_order,
        })
    return rows


async def _llm_rerank(
    rows: list[dict[str, Any]],
    *,
    query: str,
    llm_fn: Any,
    top_k: int,
) -> list[dict[str, Any]]:
    """LLM-based reranking of RRF fusion results (recovered from knowhere-kb)."""
    if not rows:
        return rows

    import json as _json
    import re as _re

    candidates_text = []
    for i, row in enumerate(rows):
        content_preview = str(row.get('content') or '')[:300]
        path = row.get('section_path') or row.get('source_file_name') or ''
        candidates_text.append(f'[{i}] path={path}\n{content_preview}')

    prompt = (
        'You are a search result reranker.\n\n'
        f'Query: {query}\n\n'
        'Candidates:\n' + '\n\n'.join(candidates_text) + '\n\n'
        'Reorder the candidates by relevance to the query. '
        'Return ONLY a JSON array of indices in order of relevance, e.g.: [2, 0, 1, 3]\n'
        'Do not include any explanation.'
    )

    try:
        response_text = await llm_fn(prompt)
        text = response_text.strip()
        match = _re.search(r'\[.*?\]', text, _re.DOTALL)
        if match:
            indices = _json.loads(match.group())
            if isinstance(indices, list):
                valid_indices = [int(idx) for idx in indices if isinstance(idx, int) and 0 <= idx < len(rows)]
                seen: set[int] = set()
                reordered: list[dict[str, Any]] = []
                for idx in valid_indices:
                    if idx not in seen:
                        seen.add(idx)
                        reordered.append(rows[idx])
                for i, row in enumerate(rows):
                    if i not in seen:
                        reordered.append(row)
                return reordered[:top_k]
    except Exception as exc:
        logger.warning(f'retrieval: LLM rerank failed (keeping original order): {exc}')

    return rows[:top_k]


async def run_retrieval_query(
    *,
    db: AsyncSession,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
    data_type: int = 1,
    signal_paths: list[str] | None = None,
    filter_mode: str = 'delete',
    channels: list[str] | None = None,
    channel_weights: dict[str, float] | None = None,
    rerank: bool = False,
    threshold: float = 0.0,
    internal_recall_k: int | None = None,
) -> dict[str, Any]:
    """Checkerboard retrieval: 3 independent channels -> RRF -> agent/graph union -> assembly."""
    t_start = time.monotonic()
    logger.info(
        f'retrieval: query="{query[:80]}" user={user_id} ns={namespace} '
        f'top_k={top_k} exclude_docs={len(exclude_document_ids)} exclude_secs={len(exclude_sections)}'
    )

    allowed_chunk_types = _resolve_allowed_chunk_types(data_type)
    effective_recall_k = internal_recall_k if internal_recall_k is not None else top_k * _INTERNAL_RECALL_K_MULTIPLIER

    cache_extra = dict(
        data_type=data_type,
        signal_paths=signal_paths,
        filter_mode=filter_mode,
        channels=channels,
        channel_weights=channel_weights,
        rerank=rerank,
        threshold=threshold,
        internal_recall_k=internal_recall_k,
    )

    cache_version: int | None = None
    try:
        cache_version, cached = await get_cached_retrieval_query_result(
            user_id=user_id,
            namespace=namespace,
            query=query,
            top_k=top_k,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
            **cache_extra,
        )
        if cached:
            logger.info(f'retrieval: cache_hit=True version={cache_version}')
            try:
                schedule_retrieval_hit_stats_update(
                    user_id=user_id,
                    namespace=namespace,
                    results=cached.get("results", []),
                )
            except Exception as e:
                logger.warning(f"Failed to trigger retrieval hit stats update (ignored): {e}")
            return await _to_public_response(cached)
    except Exception as e:
        logger.warning(f"Failed to read retrieval cache (ignored): {e}")

    logger.debug(f'retrieval: cache_hit=False version={cache_version}')

    # ── Small KB optimization ──
    total_chunk_count = await _count_scoped_chunks(
        db, user_id=user_id, namespace=namespace,
        exclude_document_ids=exclude_document_ids,
        allowed_chunk_types=allowed_chunk_types,
    )
    if total_chunk_count <= top_k:
        logger.info(f'retrieval: small_kb_optimization total_chunks={total_chunk_count} <= top_k={top_k}')
        all_rows = await _load_all_scoped_chunks(
            db, user_id=user_id, namespace=namespace,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
            allowed_chunk_types=allowed_chunk_types,
            signal_paths=signal_paths or [],
            filter_mode=filter_mode,
        )
        assembled_rows = await assemble_retrieval_results(
            db=db, rows=all_rows,
            exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections,
            allowed_chunk_types=allowed_chunk_types,
        )
        results = [_with_citation(row) for row in assembled_rows]
        response = {
            "namespace": namespace, "query": query,
            "router_used": "small_kb_all", "results": results,
        }
        if cache_version is not None:
            try:
                await set_cached_retrieval_query_result(
                    user_id=user_id, namespace=namespace, version=cache_version,
                    query=query, top_k=top_k,
                    exclude_document_ids=exclude_document_ids,
                    exclude_sections=exclude_sections,
                    response=response, **cache_extra,
                )
            except Exception as e:
                logger.warning(f"Failed to write retrieval cache (ignored): {e}")
        try:
            schedule_retrieval_hit_stats_update(user_id=user_id, namespace=namespace, results=results)
        except Exception as e:
            logger.warning(f"Failed to trigger retrieval hit stats update (ignored): {e}")
        elapsed_total = round((time.monotonic() - t_start) * 1000)
        logger.info(f'retrieval: small_kb response={len(results)} results, total_time={elapsed_total}ms')
        return await _to_public_response(response)

    # ── Channel execution ──
    active_channels = set(channels) if channels else {'path', 'content', 'term'}

    path_rows: list[dict[str, Any]] = []
    content_rows: list[dict[str, Any]] = []
    term_rows: list[dict[str, Any]] = []

    if 'path' in active_channels:
        t_ch = time.monotonic()
        path_rows = await path_channel(
            db, user_id=user_id, namespace=namespace, query=query,
            top_k=effective_recall_k, exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections, allowed_chunk_types=allowed_chunk_types,
            signal_paths=signal_paths, filter_mode=filter_mode,
        )
        logger.info(f'retrieval: path_channel={len(path_rows)} rows in {round((time.monotonic() - t_ch) * 1000)}ms')

    if 'content' in active_channels:
        t_ch = time.monotonic()
        content_rows = await content_channel(
            db, user_id=user_id, namespace=namespace, query=query,
            top_k=effective_recall_k, exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections, allowed_chunk_types=allowed_chunk_types,
            signal_paths=signal_paths, filter_mode=filter_mode,
        )
        logger.info(f'retrieval: content_channel={len(content_rows)} rows in {round((time.monotonic() - t_ch) * 1000)}ms')

    if 'term' in active_channels:
        t_ch = time.monotonic()
        term_rows = await term_channel(
            db, user_id=user_id, namespace=namespace, query=query,
            top_k=effective_recall_k, exclude_document_ids=exclude_document_ids,
            exclude_sections=exclude_sections, allowed_chunk_types=allowed_chunk_types,
            signal_paths=signal_paths, filter_mode=filter_mode,
        )
        logger.info(f'retrieval: term_channel={len(term_rows)} rows in {round((time.monotonic() - t_ch) * 1000)}ms')

    # ── RRF fusion with configurable weights ──
    default_weights = {
        'path': _CHANNEL_WEIGHT_PATH,
        'content': _CHANNEL_WEIGHT_CONTENT,
        'term': _CHANNEL_WEIGHT_TERM,
    }
    effective_weights = {**default_weights, **(channel_weights or {})}

    channel_lists: list[list[dict[str, Any]]] = []
    weight_list: list[float] = []

    if path_rows:
        channel_lists.append(path_rows)
        weight_list.append(effective_weights.get('path', _CHANNEL_WEIGHT_PATH))
    if content_rows:
        channel_lists.append(content_rows)
        weight_list.append(effective_weights.get('content', _CHANNEL_WEIGHT_CONTENT))
    if term_rows:
        channel_lists.append(term_rows)
        weight_list.append(effective_weights.get('term', _CHANNEL_WEIGHT_TERM))

    fused_rows = merge_channels_rrf(channel_lists, weight_list, top_k) if channel_lists else []
    logger.info(f'retrieval: rrf_fusion={len(fused_rows)} rows from {len(channel_lists)} channels')

    # ── Section merging ──
    pre_merge = len(fused_rows)
    fused_rows = _merge_same_section_rows(fused_rows)
    if len(fused_rows) != pre_merge:
        logger.info(f'retrieval: section_merge={pre_merge}->{len(fused_rows)}')

    # ── Threshold filtering ──
    if threshold > 0.0 and fused_rows:
        pre_count = len(fused_rows)
        fused_rows = [row for row in fused_rows if row.get('score', 0.0) >= threshold]
        logger.info(f'retrieval: threshold_filter={pre_count}->{len(fused_rows)} (threshold={threshold})')

    # ── LLM reranking ──
    if rerank and fused_rows:
        t_rerank = time.monotonic()
        rerank_llm_fn = create_retrieval_llm_fn()
        if rerank_llm_fn is not None:
            fused_rows = await _llm_rerank(fused_rows, query=query, llm_fn=rerank_llm_fn, top_k=top_k)
            logger.info(f'retrieval: llm_rerank={len(fused_rows)} rows in {round((time.monotonic() - t_rerank) * 1000)}ms')
        else:
            logger.warning('retrieval: rerank requested but no LLM configured, skipping')

    # ── Agent navigation or lexical graph fallback ──
    router_used = 'discovery_only'
    llm_fn = create_retrieval_llm_fn()

    if llm_fn is not None:
        t_agent = time.monotonic()
        try:
            graph_rows = await agent_navigate(
                db,
                user_id=user_id,
                namespace=namespace,
                query=query,
                llm_fn=llm_fn,
                exclude_document_ids=exclude_document_ids,
            )
            if graph_rows:
                router_used = 'discovery+agent'
                logger.info(
                    f'retrieval: agent_navigate={len(graph_rows)} rows '
                    f'in {round((time.monotonic() - t_agent) * 1000)}ms (router={router_used})'
                )
            else:
                logger.info(
                    f'retrieval: agent_navigate=0 rows '
                    f'in {round((time.monotonic() - t_agent) * 1000)}ms, '
                    f'falling back to lexical graph routing'
                )
                graph_rows = await list_graph_routed_chunks(
                    db, user_id=user_id, namespace=namespace, query=query,
                    top_k=top_k, exclude_document_ids=exclude_document_ids,
                    exclude_sections=exclude_sections,
                )
                if graph_rows:
                    logger.info(f'retrieval: graph_fallback={len(graph_rows)} rows')
        except Exception as exc:
            logger.error(f'retrieval: agent_navigate failed, falling back to lexical: {exc}')
            graph_rows = await list_graph_routed_chunks(
                db, user_id=user_id, namespace=namespace, query=query,
                top_k=top_k, exclude_document_ids=exclude_document_ids,
                exclude_sections=exclude_sections,
            )
            if graph_rows:
                logger.info(f'retrieval: graph_fallback={len(graph_rows)} rows')
    else:
        logger.debug('retrieval: no LLM configured, using lexical graph routing')
        try:
            graph_rows = await list_graph_routed_chunks(
                db, user_id=user_id, namespace=namespace, query=query,
                top_k=top_k, exclude_document_ids=exclude_document_ids,
                exclude_sections=exclude_sections,
            )
            if graph_rows:
                logger.info(f'retrieval: graph_fallback={len(graph_rows)} rows')
        except Exception as exc:
            logger.error(f'retrieval: graph routing failed (ignored): {exc}')
            graph_rows = []

    if graph_rows:
        fused_rows = _union_graph_results(fused_rows, graph_rows, top_k)
        logger.info(f'retrieval: union={len(fused_rows)} rows after graph merge')

    assembled_rows = await assemble_retrieval_results(
        db=db,
        rows=fused_rows,
        exclude_document_ids=exclude_document_ids,
        exclude_sections=exclude_sections,
        allowed_chunk_types=allowed_chunk_types,
    )
    results = [_with_citation(row) for row in assembled_rows]
    logger.info(f'retrieval: assembled={len(results)} results')

    response = {
        "namespace": namespace,
        "query": query,
        "router_used": router_used,
        "results": results,
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
                **cache_extra,
            )
        except Exception as e:
            logger.warning(f"Failed to write retrieval cache (ignored): {e}")

    try:
        schedule_retrieval_hit_stats_update(
            user_id=user_id,
            namespace=namespace,
            results=results,
        )
    except Exception as e:
        logger.warning(f"Failed to trigger retrieval hit stats update (ignored): {e}")

    elapsed_total = round((time.monotonic() - t_start) * 1000)
    logger.info(
        f'retrieval: response={len(results)} results, '
        f'router={router_used}, total_time={elapsed_total}ms'
    )

    return await _to_public_response(response)
