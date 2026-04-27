"""Agentic retrieval tools — thin wrappers around existing retrieval components.

Each tool:
  1. Calls existing functions from channels.py, agent_navigate.py, app_service.py
  2. Returns a unified ToolResult
  3. Never raises — errors are captured in ToolResult.error

No new retrieval algorithms, ranking strategies, or prompts.
LLM calls inside kg_document_select / document_path_select reuse
the exact same prompts and parsing logic from agent_navigate.py.
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.document import Document
from shared.services.retrieval.agentic.types import AgentRunConfig, ToolResult
from shared.services.retrieval.agent_navigate import (
    _build_chunks_slim,
    _build_knowledge_map_overview,
    _build_sub_sections_from_db,
    _collect_leaf_paths,
    _expand_by_edges,
    _format_chunks_for_llm,
    _format_sections_for_llm,
    _grep_discover_document_ids,
    _load_nav_sections_from_graph,
    _parse_chunk_path_selections,
    _parse_json_array,
    _parse_section_selections,
    _CHUNK_SELECT_PROMPT,
    _FILE_SELECT_PROMPT,
    _NAV_SECTION_PROMPT,
    _default_confidence_for_rank,
    CHUNK_COUNT_THRESHOLD,
)
from shared.services.retrieval.app_service import (
    _CHANNEL_WEIGHT_CONTENT,
    _CHANNEL_WEIGHT_PATH,
    _CHANNEL_WEIGHT_TERM,
    _INTERNAL_RECALL_K_MULTIPLIER,
    _merge_same_section_rows,
    _normalize_row_scores,
    _resolve_allowed_chunk_types,
    merge_channels_rrf,
)
from shared.services.retrieval.channels import content_channel, path_channel, term_channel
from shared.services.retrieval.llm_adapter import LLMFn


# ---------------------------------------------------------------------------
# Tool: bottom_discovery
# ---------------------------------------------------------------------------

async def bottom_discovery(
    db: AsyncSession,
    *,
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
    internal_recall_k: int | None = None,
    **_kwargs: Any,
) -> ToolResult:
    """Run 3-channel BM25 discovery + RRF fusion.

    Reuses: channels.path_channel, content_channel, term_channel,
            app_service.merge_channels_rrf, _merge_same_section_rows.
    """
    t0 = time.monotonic()
    try:
        allowed_chunk_types = _resolve_allowed_chunk_types(data_type)
        effective_recall_k = internal_recall_k if internal_recall_k is not None else top_k * _INTERNAL_RECALL_K_MULTIPLIER
        active_channels = set(channels) if channels else {'path', 'content', 'term'}

        path_rows: list[dict[str, Any]] = []
        content_rows: list[dict[str, Any]] = []
        term_rows: list[dict[str, Any]] = []

        if 'path' in active_channels:
            path_rows = await path_channel(
                db, user_id=user_id, namespace=namespace, query=query,
                top_k=effective_recall_k, exclude_document_ids=exclude_document_ids,
                exclude_sections=exclude_sections, allowed_chunk_types=allowed_chunk_types,
                signal_paths=signal_paths, filter_mode=filter_mode,
            )

        if 'content' in active_channels:
            content_rows = await content_channel(
                db, user_id=user_id, namespace=namespace, query=query,
                top_k=effective_recall_k, exclude_document_ids=exclude_document_ids,
                exclude_sections=exclude_sections, allowed_chunk_types=allowed_chunk_types,
                signal_paths=signal_paths, filter_mode=filter_mode,
            )

        if 'term' in active_channels:
            term_rows = await term_channel(
                db, user_id=user_id, namespace=namespace, query=query,
                top_k=effective_recall_k, exclude_document_ids=exclude_document_ids,
                exclude_sections=exclude_sections, allowed_chunk_types=allowed_chunk_types,
                signal_paths=signal_paths, filter_mode=filter_mode,
            )

        # RRF fusion — same logic as app_service
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
        fused_rows = _merge_same_section_rows(fused_rows)

        if fused_rows:
            _normalize_row_scores(fused_rows, source_field='score', target_field='discovery_score', default=0.5)

        # Extract top document IDs as hints for KG selection
        doc_id_counts: dict[str, int] = {}
        for row in fused_rows:
            did = row.get('document_id', '')
            if did:
                doc_id_counts[did] = doc_id_counts.get(did, 0) + 1
        top_doc_ids = sorted(doc_id_counts, key=lambda d: doc_id_counts[d], reverse=True)[:5]

        latency = int((time.monotonic() - t0) * 1000)
        logger.info(
            f'  agentic.bottom_discovery: {len(fused_rows)} fused rows, '
            f'top_doc_ids={top_doc_ids}, {latency}ms'
        )
        return ToolResult(
            status='discovery_done',
            payload={
                'fused_rows': fused_rows,
                'top_doc_ids': top_doc_ids,
                'channel_counts': {
                    'path': len(path_rows),
                    'content': len(content_rows),
                    'term': len(term_rows),
                },
            },
            latency_ms=latency,
        )
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.bottom_discovery failed: {e}')
        return ToolResult(status='error', error=str(e), latency_ms=latency)


# ---------------------------------------------------------------------------
# Tool: kg_document_select
# ---------------------------------------------------------------------------

async def kg_document_select(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    llm_fn: LLMFn | None,
    exclude_document_ids: list[str],
    **_kwargs: Any,
) -> ToolResult:
    """Select candidate documents from document-level KG.

    Reuses: agent_navigate._build_knowledge_map_overview, _parse_json_array.
    Same LLM prompt as agent_navigate._FILE_SELECT_PROMPT.
    """
    t0 = time.monotonic()
    try:
        overview_text, doc_id_to_name = await _build_knowledge_map_overview(
            db, user_id=user_id, namespace=namespace,
        )
        if overview_text == '(empty)':
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_confident_doc',
                payload={'reason': 'no active documents in namespace'},
                latency_ms=latency,
            )

        if llm_fn is None:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_confident_doc',
                payload={'reason': 'LLM not available'},
                latency_ms=latency,
            )

        # LLM file selection — same prompt as agent_navigate
        file_prompt = _FILE_SELECT_PROMPT.format(
            overview=overview_text, query=query,
        )
        file_response = await llm_fn(file_prompt)
        selected_ids = _parse_json_array(file_response)

        exclude_set = set(exclude_document_ids)
        valid_ids = [did for did in selected_ids if did in doc_id_to_name and did not in exclude_set]

        if not valid_ids:
            latency = int((time.monotonic() - t0) * 1000)
            logger.info(f'  agentic.kg_document_select: LLM returned no valid docs, {latency}ms')
            return ToolResult(
                status='no_confident_doc',
                payload={'reason': 'LLM returned no valid document IDs', 'raw_ids': selected_ids},
                latency_ms=latency,
            )

        # Load job_result_ids for selected documents
        doc_job_map: dict[str, str] = {}
        doc_stmt = (
            select(Document.document_id, Document.current_job_result_id)
            .where(Document.document_id.in_(valid_ids))
        )
        doc_result = await db.execute(doc_stmt)
        for did, jrid in doc_result.all():
            if jrid:
                doc_job_map[did] = jrid

        candidate_docs = []
        for did in valid_ids:
            candidate_docs.append({
                'document_id': did,
                'source_file_name': doc_id_to_name.get(did, ''),
                'confidence': 0.8,
                'reason': 'LLM selected from KG overview',
                'source': 'kg_llm_select',
            })

        latency = int((time.monotonic() - t0) * 1000)
        logger.info(f'  agentic.kg_document_select: {len(candidate_docs)} docs selected, {latency}ms')
        return ToolResult(
            status='selected_docs',
            payload={
                'candidate_docs': candidate_docs,
                'doc_id_to_name': doc_id_to_name,
                'doc_job_map': doc_job_map,
            },
            latency_ms=latency,
        )
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.kg_document_select failed: {e}')
        return ToolResult(status='error', error=str(e), latency_ms=latency)


# ---------------------------------------------------------------------------
# Tool: document_path_select
# ---------------------------------------------------------------------------

async def document_path_select(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    llm_fn: LLMFn | None,
    document_id: str,
    job_result_id: str,
    doc_name: str = '',
    max_chunks_per_file: int = 15,
    **_kwargs: Any,
) -> ToolResult:
    """Select chunk paths within a single document.

    Reuses: agent_navigate._build_chunks_slim, _format_chunks_for_llm,
            _CHUNK_SELECT_PROMPT, _parse_chunk_path_selections.

    Returns one of:
      - selected_paths: found relevant paths
      - need_nav_drill: large document with doc_nav available, switch to hierarchical mode
      - need_more_docs: document not relevant, suggest going back to doc select
      - no_confident_match: no paths match above threshold
    """
    t0 = time.monotonic()
    try:
        if llm_fn is None:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_confident_match',
                payload={'document_id': document_id, 'reason': 'LLM not available'},
                latency_ms=latency,
            )

        # Check if doc_nav sections are available for large documents
        nav_data = await _load_nav_sections_from_graph(db, document_id)
        if nav_data:
            total_chunks = nav_data.get('total_chunks', 0)
            if total_chunks > CHUNK_COUNT_THRESHOLD:
                latency = int((time.monotonic() - t0) * 1000)
                logger.info(
                    f'  agentic.document_path_select: doc={document_id} '
                    f'total_chunks={total_chunks} > {CHUNK_COUNT_THRESHOLD}, '
                    f'switching to nav_section_select'
                )
                return ToolResult(
                    status='need_nav_drill',
                    payload={
                        'document_id': document_id,
                        'total_chunks': total_chunks,
                    },
                    latency_ms=latency,
                )

        chunks_slim = await _build_chunks_slim(
            db, document_id=document_id, job_result_id=job_result_id,
        )
        if not chunks_slim:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_confident_match',
                payload={'document_id': document_id, 'reason': 'no chunks found'},
                latency_ms=latency,
            )

        chunks_text = _format_chunks_for_llm(chunks_slim)
        chunk_prompt = _CHUNK_SELECT_PROMPT.format(
            doc_name=doc_name or document_id,
            doc_id=document_id,
            chunks_overview=chunks_text,
            query=query,
            max_chunks=max_chunks_per_file,
        )

        valid_paths = {c['path'] for c in chunks_slim if c.get('path')}
        chunk_response = await llm_fn(chunk_prompt)
        parsed_selections = _parse_chunk_path_selections(chunk_response)

        accepted: list[dict[str, Any]] = []
        for item in parsed_selections:
            path = str(item.get('path') or '').strip()
            if path not in valid_paths:
                continue
            confidence = item.get('confidence')
            if confidence is None:
                confidence = _default_confidence_for_rank(len(accepted))
            accepted.append({'path': path, 'confidence': confidence})
            if len(accepted) >= max_chunks_per_file:
                break

        latency = int((time.monotonic() - t0) * 1000)

        if accepted:
            logger.info(
                f'  agentic.document_path_select: {len(accepted)} paths from doc={document_id}, {latency}ms'
            )
            return ToolResult(
                status='selected_paths',
                payload={'document_id': document_id, 'selected_paths': accepted},
                latency_ms=latency,
            )

        # No paths accepted — not relevant
        return ToolResult(
            status='no_confident_match',
            payload={'document_id': document_id, 'reason': 'no path matches query intent'},
            latency_ms=latency,
        )
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.document_path_select failed for doc={document_id}: {e}')
        return ToolResult(
            status='error',
            payload={'document_id': document_id},
            error=str(e),
            latency_ms=latency,
        )


# ---------------------------------------------------------------------------
# Tool: grep_document_discover
# ---------------------------------------------------------------------------

async def grep_document_discover(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    exclude_document_ids: list[str],
    **_kwargs: Any,
) -> ToolResult:
    """Discover documents via term search (GREP).

    Reuses: agent_navigate._grep_discover_document_ids.
    """
    t0 = time.monotonic()
    try:
        grep_doc_ids = await _grep_discover_document_ids(
            db, user_id=user_id, namespace=namespace, query=query,
            exclude_document_ids=exclude_document_ids,
        )

        if not grep_doc_ids:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_docs_found',
                payload={'reason': 'GREP found no matching documents'},
                latency_ms=latency,
            )

        # Load doc names and job_result_ids
        doc_stmt = (
            select(Document.document_id, Document.source_file_name, Document.current_job_result_id)
            .where(Document.document_id.in_(grep_doc_ids))
        )
        doc_result = await db.execute(doc_stmt)
        doc_id_to_name: dict[str, str] = {}
        doc_job_map: dict[str, str] = {}
        for did, fname, jrid in doc_result.all():
            doc_id_to_name[did] = fname or did
            if jrid:
                doc_job_map[did] = jrid

        latency = int((time.monotonic() - t0) * 1000)
        logger.info(f'  agentic.grep_document_discover: {len(grep_doc_ids)} docs found, {latency}ms')
        return ToolResult(
            status='discovered_docs',
            payload={
                'document_ids': grep_doc_ids,
                'doc_id_to_name': doc_id_to_name,
                'doc_job_map': doc_job_map,
            },
            latency_ms=latency,
        )
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.grep_document_discover failed: {e}')
        return ToolResult(status='error', error=str(e), latency_ms=latency)


# ---------------------------------------------------------------------------
# Tool: graph_expand_docs
# ---------------------------------------------------------------------------

async def graph_expand_docs(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    document_ids: list[str],
    **_kwargs: Any,
) -> ToolResult:
    """Expand document set via KG edge traversal.

    Reuses: agent_navigate._expand_by_edges.
    """
    t0 = time.monotonic()
    try:
        expanded_ids = await _expand_by_edges(
            db, document_ids=document_ids, user_id=user_id, namespace=namespace,
        )
        new_ids = [did for did in expanded_ids if did not in document_ids]

        if not new_ids:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_expansion',
                payload={'reason': 'no new neighbors found via edges'},
                latency_ms=latency,
            )

        # Load names and job maps for new docs
        doc_stmt = (
            select(Document.document_id, Document.source_file_name, Document.current_job_result_id)
            .where(Document.document_id.in_(new_ids))
        )
        doc_result = await db.execute(doc_stmt)
        doc_id_to_name: dict[str, str] = {}
        doc_job_map: dict[str, str] = {}
        for did, fname, jrid in doc_result.all():
            doc_id_to_name[did] = fname or did
            if jrid:
                doc_job_map[did] = jrid

        latency = int((time.monotonic() - t0) * 1000)
        logger.info(f'  agentic.graph_expand_docs: {len(new_ids)} new docs from edges, {latency}ms')
        return ToolResult(
            status='expanded_docs',
            payload={
                'document_ids': new_ids,
                'doc_id_to_name': doc_id_to_name,
                'doc_job_map': doc_job_map,
            },
            latency_ms=latency,
        )
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.graph_expand_docs failed: {e}')
        return ToolResult(status='error', error=str(e), latency_ms=latency)


# ---------------------------------------------------------------------------
# Tool: nav_section_select
# ---------------------------------------------------------------------------

async def nav_section_select(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    llm_fn: LLMFn | None,
    document_id: str,
    job_result_id: str,
    doc_name: str = '',
    section_path: str | None = None,
    **_kwargs: Any,
) -> ToolResult:
    """Navigate doc_nav.json tree hierarchically.

    When section_path is None, show top-level sections (from GraphNode).
    When section_path is given, show children of that section (from DB).

    For small documents (≤ CHUNK_COUNT_THRESHOLD), falls back to
    flat chunks_slim selection via the existing chunk selection prompt.
    """
    t0 = time.monotonic()
    try:
        if llm_fn is None:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_confident_match',
                payload={'document_id': document_id, 'reason': 'LLM not available'},
                latency_ms=latency,
            )

        # Load section view at the appropriate level
        sections: list[dict] = []
        if section_path is None:
            # Top-level: from GraphNode.properties.nav_sections
            nav_data = await _load_nav_sections_from_graph(db, document_id)
            if nav_data:
                sections = nav_data.get('sections', [])
        else:
            # Sub-level: from DocumentSection table
            sections = await _build_sub_sections_from_db(
                db,
                document_id=document_id,
                job_result_id=job_result_id,
                parent_path=section_path,
            )

        if not sections:
            # No section data — fallback to chunks_slim direct selection
            logger.info(
                f'  agentic.nav_section_select: no sections for doc={document_id} '
                f'section_path={section_path}, falling back to chunks_slim'
            )
            return await _nav_fallback_chunks_slim(
                db,
                document_id=document_id,
                job_result_id=job_result_id,
                query=query,
                llm_fn=llm_fn,
                doc_name=doc_name,
                path_scope=section_path,
            )

        # Format and prompt LLM
        sections_text = _format_sections_for_llm(sections)
        prompt = _NAV_SECTION_PROMPT.format(
            doc_name=doc_name or document_id,
            doc_id=document_id,
            sections_overview=sections_text,
            query=query,
        )

        response = await llm_fn(prompt)
        logger.info(f'  agentic.nav_section_select LLM response: {response[:300]}')
        selections = _parse_section_selections(response)

        # Validate and categorize selections
        valid_paths = {s['path'] for s in sections if s.get('path')}
        section_lookup = {s['path']: s for s in sections}

        selected_paths: list[dict[str, Any]] = []
        drill_entries: list[dict[str, Any]] = []

        for sel in selections:
            path = sel['path']
            action = sel.get('action', 'select')

            if path not in valid_paths:
                logger.warning(f'  nav_section_select: rejected invalid path: {path}')
                continue

            section = section_lookup[path]
            chunk_count = section.get('chunk_count', 0)
            has_children = section.get('children_count', 0) > 0

            # Convert chunk path (kb/file/Section) → section_path (Section)
            from shared.services.retrieval.lexical_text import section_path_from_chunk_path
            db_section_path = section_path_from_chunk_path(path) or path

            if action == 'drill' and has_children and chunk_count > CHUNK_COUNT_THRESHOLD:
                drill_entries.append({
                    'document_id': document_id,
                    'section_path': db_section_path,
                    'depth': section.get('level', 1),
                })
            else:
                # "select" or no children → collect leaf paths
                leaf_paths = await _collect_leaf_paths(
                    db,
                    document_id=document_id,
                    job_result_id=job_result_id,
                    section_path=db_section_path,
                )
                selected_paths.extend(leaf_paths)

        latency = int((time.monotonic() - t0) * 1000)

        if drill_entries and not selected_paths:
            logger.info(
                f'  agentic.nav_section_select: {len(drill_entries)} sections need deeper drill, {latency}ms'
            )
            return ToolResult(
                status='need_deeper_drill',
                payload={'drill_entries': drill_entries, 'document_id': document_id},
                latency_ms=latency,
            )
        elif selected_paths:
            # If we also have drill entries, add them back
            # (mixed drill + select is fine)
            logger.info(
                f'  agentic.nav_section_select: {len(selected_paths)} paths selected'
                + (f', {len(drill_entries)} pending drills' if drill_entries else '')
                + f', {latency}ms'
            )
            result = ToolResult(
                status='selected_paths',
                payload={'document_id': document_id, 'selected_paths': selected_paths},
                latency_ms=latency,
            )
            # If mixed, we need to push drill entries separately
            if drill_entries:
                result.payload['pending_drill_entries'] = drill_entries
            return result
        else:
            logger.info(f'  agentic.nav_section_select: no match for doc={document_id}, {latency}ms')
            return ToolResult(
                status='no_confident_match',
                payload={'document_id': document_id, 'reason': 'no section matches query'},
                latency_ms=latency,
            )

    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.nav_section_select failed for doc={document_id}: {e}')
        return ToolResult(
            status='error',
            payload={'document_id': document_id},
            error=str(e),
            latency_ms=latency,
        )


async def _nav_fallback_chunks_slim(
    db: AsyncSession,
    *,
    document_id: str,
    job_result_id: str,
    query: str,
    llm_fn: LLMFn,
    doc_name: str,
    path_scope: str | None = None,
) -> ToolResult:
    """Fallback: use flat chunks_slim selection when no sections available.

    Builds chunks_slim in-memory from DB (no files), applies path_scope
    filter if given, and uses the standard chunk selection prompt.
    """
    t0 = time.monotonic()
    try:
        chunks_slim = await _build_chunks_slim(
            db, document_id=document_id, job_result_id=job_result_id,
        )
        if not chunks_slim:
            latency = int((time.monotonic() - t0) * 1000)
            return ToolResult(
                status='no_confident_match',
                payload={'document_id': document_id, 'reason': 'no chunks found'},
                latency_ms=latency,
            )

        if path_scope:
            chunks_slim = [c for c in chunks_slim if c.get('path', '').startswith(path_scope)]
            if not chunks_slim:
                latency = int((time.monotonic() - t0) * 1000)
                return ToolResult(
                    status='no_confident_match',
                    payload={'document_id': document_id, 'reason': f'no chunks under {path_scope}'},
                    latency_ms=latency,
                )

        chunks_text = _format_chunks_for_llm(chunks_slim)
        prompt = _CHUNK_SELECT_PROMPT.format(
            doc_name=doc_name or document_id,
            doc_id=document_id,
            chunks_overview=chunks_text,
            query=query,
            max_chunks=15,
        )

        valid_paths = {c['path'] for c in chunks_slim if c.get('path')}
        response = await llm_fn(prompt)
        parsed = _parse_chunk_path_selections(response)

        accepted: list[dict[str, Any]] = []
        for item in parsed:
            path = str(item.get('path') or '').strip()
            if path not in valid_paths:
                continue
            confidence = item.get('confidence')
            if confidence is None:
                confidence = _default_confidence_for_rank(len(accepted))
            accepted.append({'path': path, 'confidence': confidence})

        latency = int((time.monotonic() - t0) * 1000)

        if accepted:
            return ToolResult(
                status='selected_paths',
                payload={'document_id': document_id, 'selected_paths': accepted},
                latency_ms=latency,
            )
        return ToolResult(
            status='no_confident_match',
            payload={'document_id': document_id, 'reason': 'no chunk paths matched'},
            latency_ms=latency,
        )
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        logger.error(f'  agentic.nav_fallback failed for doc={document_id}: {e}')
        return ToolResult(
            status='error',
            payload={'document_id': document_id},
            error=str(e),
            latency_ms=latency,
        )
