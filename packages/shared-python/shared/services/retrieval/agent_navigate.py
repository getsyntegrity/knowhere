"""Agent-driven KG navigation for retrieval — aligned with knowhere-kb.

Two-stage LLM-driven document routing (mirrors unified_retriever.agent_navigate):
  1. LLM reads a knowledge map overview (file-level metadata) and selects relevant files.
  2. For each file, LLM reads compact chunk previews and selects relevant chunk **paths**.

Additional KB-aligned mechanisms:
  - GREP discovery: term-search hits → include parent document_ids in KG scope.
  - Edge expansion: selected documents → follow GraphEdge → include neighbor documents.

Returns chunk paths (section_path / source_chunk_path), NOT hydrated rows.
The caller (app_service) handles path→row hydration and union with discovery results.

Falls back gracefully when LLM is unavailable or fails.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Sequence

from loguru import logger
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.document import Document, DocumentChunk, DocumentSection, GraphNode, GraphEdge
from shared.models.database.job_result import JobResult
from shared.services.retrieval.hit_stats_service import compute_importance_score
from shared.services.retrieval.llm_adapter import LLMFn
from shared.models.database.document import RetrievalHitStat

_CONTENT_PREVIEW_LEN = 120
_MAX_OVERVIEW_FILES = 50
_MAX_CHUNKS_SLIM_PER_DOC = 80

_FILE_SELECT_PROMPT = """\
You are a document routing assistant.

Below is a knowledge base overview showing all available documents,
their keywords, summaries, chunk counts, and retrieval popularity.

=== Knowledge Base Overview ===
{overview}
=== End Overview ===

User query: {query}

Based on the query, select the most relevant documents (return at most {max_files}).
Return ONLY a JSON array of document IDs, e.g.: ["doc_abc123", "doc_def456"]
Do not include any explanation.
"""

_CHUNK_SELECT_PROMPT = """\
You are a document chunk routing assistant.

Below are candidate chunks from document "{doc_name}" (id: {doc_id}):

=== Chunk Candidates ===
{chunks_overview}
=== End Candidates ===

User query: {query}

Select the most relevant chunks (at most {max_chunks}).
Return ONLY a JSON array of chunk path strings from the list above,
e.g.: ["doc_name/Section A/Subsection B", "tables/table-1.html"]
Do not include any explanation.
"""


def _parse_json_array(text: str) -> list[str]:
    """Best-effort extraction of a JSON array from LLM response text."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [str(x) for x in result]
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return [str(x) for x in result]
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _keywords_need_repair(keywords: list[str] | None) -> bool:
    if not isinstance(keywords, list) or not keywords:
        return True
    bad = sum(1 for kw in keywords if not kw or len(str(kw)) <= 1
              or re.match(r'^\d+[.,%]*$', str(kw)))
    return bad >= len(keywords) * 0.5


def _compute_tfidf_keywords(chunk_metadata_list: list[dict[str, Any]], top_k: int = 10) -> list[str]:
    df_count: dict[str, int] = {}
    tf_count: dict[str, int] = {}
    total = len(chunk_metadata_list) or 1
    for meta in chunk_metadata_list:
        if not isinstance(meta, dict):
            continue
        terms = list(meta.get('tokens', [])) + list(meta.get('keywords', []))
        seen: set[str] = set()
        for t in terms:
            if not t or len(str(t)) <= 1 or re.match(r'^\d+[.,%]*$', str(t)):
                continue
            lower = str(t).lower()
            tf_count[lower] = tf_count.get(lower, 0) + 1
            if lower not in seen:
                df_count[lower] = df_count.get(lower, 0) + 1
                seen.add(lower)
    scored = [(term, freq * (math.log(total / (df_count.get(term, 1))) + 1))
              for term, freq in tf_count.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:top_k]]


async def _build_knowledge_map_overview(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
) -> tuple[str, dict[str, str]]:
    """Build a file-level knowledge map overview for LLM file selection.

    Returns (overview_text, doc_id_to_name) where doc_id_to_name maps
    document_id -> source_file_name for validation after LLM response.
    """
    doc_stmt = (
        select(Document)
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
        .where(Document.current_job_result_id.is_not(None))
        .order_by(Document.updated_at.desc())
        .limit(_MAX_OVERVIEW_FILES)
    )
    doc_result = await db.execute(doc_stmt)
    documents = list(doc_result.scalars())

    if not documents:
        return '(empty)', {}

    doc_ids = [d.document_id for d in documents]
    doc_id_to_name: dict[str, str] = {
        d.document_id: (d.source_file_name or d.document_id)
        for d in documents
    }

    chunk_stats_stmt = (
        select(
            DocumentChunk.document_id,
            func.count(DocumentChunk.id).label('chunk_count'),
            func.count(func.nullif(DocumentChunk.chunk_type, 'text')).label('media_count'),
        )
        .join(Document, (Document.document_id == DocumentChunk.document_id) & (Document.current_job_result_id == DocumentChunk.job_result_id))
        .where(DocumentChunk.document_id.in_(doc_ids))
        .group_by(DocumentChunk.document_id)
    )
    chunk_stats_result = await db.execute(chunk_stats_stmt)
    chunk_stats: dict[str, dict[str, int]] = {}
    for row in chunk_stats_result.all():
        chunk_stats[row[0]] = {'total': row[1], 'media': row[2]}

    hit_stmt = (
        select(
            RetrievalHitStat.document_id,
            RetrievalHitStat.hit_count,
            RetrievalHitStat.last_hit_at,
            RetrievalHitStat.created_at,
        )
        .where(RetrievalHitStat.user_id == user_id)
        .where(RetrievalHitStat.namespace == namespace)
        .where(RetrievalHitStat.hit_kind == 'document')
        .where(RetrievalHitStat.document_id.in_(doc_ids))
    )
    hit_result = await db.execute(hit_stmt)
    doc_importance: dict[str, float] = {}
    for row in hit_result.all():
        doc_importance[row[0]] = compute_importance_score(row[1], row[2], row[3])

    section_summaries_stmt = (
        select(
            DocumentSection.document_id,
            func.string_agg(DocumentSection.section_title, ' / ').label('titles'),
        )
        .join(Document, (Document.document_id == DocumentSection.document_id) & (Document.current_job_result_id == DocumentSection.job_result_id))
        .where(DocumentSection.document_id.in_(doc_ids))
        .where(DocumentSection.section_level <= 2)
        .group_by(DocumentSection.document_id)
    )
    section_result = await db.execute(section_summaries_stmt)
    section_titles: dict[str, str] = {row[0]: row[1] or '' for row in section_result.all()}

    chunk_meta_stmt = (
        select(DocumentChunk.document_id, DocumentChunk.chunk_metadata)
        .join(Document, (Document.document_id == DocumentChunk.document_id) & (Document.current_job_result_id == DocumentChunk.job_result_id))
        .where(DocumentChunk.document_id.in_(doc_ids))
    )
    chunk_meta_result = await db.execute(chunk_meta_stmt)
    doc_chunk_metas: dict[str, list[dict[str, Any]]] = {}
    for did, meta in chunk_meta_result.all():
        doc_chunk_metas.setdefault(did, []).append(meta or {})

    doc_keywords: dict[str, str] = {}
    for did, metas in doc_chunk_metas.items():
        existing_kws = []
        for m in metas:
            existing_kws.extend(m.get('keywords', []))
        if _keywords_need_repair(existing_kws):
            kws = _compute_tfidf_keywords(metas)
        else:
            kws = [str(k) for k in existing_kws if k and len(str(k)) > 1][:10]
        if kws:
            doc_keywords[did] = ', '.join(kws[:8])

    lines: list[str] = []
    for doc in documents:
        did = doc.document_id
        name = doc_id_to_name[did]
        stats = chunk_stats.get(did, {'total': 0, 'media': 0})
        importance = doc_importance.get(did, 0.0)
        titles = section_titles.get(did, '')

        line = f'- [{did}] {name}  chunks={stats["total"]}'
        if stats['media'] > 0:
            line += f' media={stats["media"]}'
        if importance > 0:
            line += f' importance={importance}'
        kw_str = doc_keywords.get(did, '')
        if kw_str:
            line += f'  keywords="{kw_str}"'
        if titles:
            line += f'  sections="{titles[:200]}"'
        lines.append(line)

    return '\n'.join(lines), doc_id_to_name


async def _build_chunks_slim(
    db: AsyncSession,
    *,
    document_id: str,
    job_result_id: str,
) -> list[dict[str, str]]:
    """Build compact chunk descriptors for LLM chunk path selection.

    Aligned with KB's do_get_chunks_slim() + _build_slim_chunk():
    - Each entry has 'path' (section_path or source_chunk_path), 'type', 'preview'
    - 'preview' is summary-first (from chunk_metadata.summary), fallback to content[:N]
    - LLM will select paths, not chunk_ids
    """
    stmt = (
        select(
            DocumentChunk.chunk_id,
            DocumentChunk.chunk_type,
            DocumentChunk.content,
            DocumentChunk.source_chunk_path,
            DocumentChunk.chunk_metadata,
            DocumentSection.section_path,
        )
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .where(DocumentChunk.document_id == document_id)
        .where(DocumentChunk.job_result_id == job_result_id)
        .order_by(DocumentChunk.sort_order)
        .limit(_MAX_CHUNKS_SLIM_PER_DOC)
    )
    result = await db.execute(stmt)
    chunks: list[dict[str, str]] = []
    for chunk_id, chunk_type, content, source_chunk_path, chunk_metadata, section_path in result.all():
        # Path: prefer section_path, fallback to source_chunk_path
        path = section_path or source_chunk_path or ''
        if not path:
            continue

        # Preview: prefer metadata.summary (aligned with KB _build_slim_chunk)
        meta = chunk_metadata or {}
        summary = re.sub(r'\s+', ' ', str(meta.get('summary') or '')).strip()
        raw_content = re.sub(r'\s+', ' ', str(content or '')).strip()
        preview = summary or raw_content[:_CONTENT_PREVIEW_LEN]

        entry: dict[str, str] = {
            'path': path,
            'type': chunk_type or 'text',
        }
        if preview:
            entry['preview'] = preview[:_CONTENT_PREVIEW_LEN]
        chunks.append(entry)
    return chunks


def _format_chunks_for_llm(chunks: list[dict[str, str]], max_chars: int = 4000) -> str:
    """Format compact chunk descriptors for LLM prompt.

    Shows path (not chunk_id), aligned with KB's _format_chunks_slim().
    """
    if not chunks:
        return '(no chunks available)'

    def _render(include_preview: bool) -> str:
        lines: list[str] = []
        for c in chunks:
            line = f'- [{c["type"]}] path="{c["path"]}"'
            if include_preview and c.get('preview'):
                line += f' | {c["preview"]}'
            if len('\n'.join(lines + [line])) > max_chars:
                break
            lines.append(line)
        return '\n'.join(lines) if lines else '(no chunks available)'

    if len(chunks) > 50:
        return _render(include_preview=False)
    full = _render(include_preview=True)
    return full if len(full) <= max_chars else _render(include_preview=False)


# ------------------------------------------------------------------
# GREP document discovery (aligned with KB do_discover_files)
# ------------------------------------------------------------------

async def _grep_discover_document_ids(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    exclude_document_ids: Sequence[str] = (),
    limit: int = 10,
) -> list[str]:
    """GREP discovery: search term_search_text for query terms, return parent document_ids.

    Aligned with KB's do_discover_files(): if a chunk's term_search_text
    contains query terms, its parent document is included in the KG scope.
    """
    # Tokenize query into searchable units (Chinese groups + English words)
    units = re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z0-9]{2,}', query.lower())
    logger.info(f'  GREP tokenized units (cap 8): {units[:8]}  (total={len(units)})')
    if not units:
        return []

    # Build OR conditions for ILIKE matching
    conditions = []
    params: dict[str, str] = {
        'user_id': user_id,
        'namespace': namespace,
    }
    for i, unit in enumerate(units[:8]):  # cap at 8 terms to avoid huge queries
        param_name = f'unit_{i}'
        params[param_name] = f'%{unit}%'
        conditions.append(DocumentChunk.term_search_text.ilike(f'%{unit}%'))

    if not conditions:
        return []

    stmt = (
        select(Document.document_id)
        .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id)
              & (DocumentChunk.job_result_id == Document.current_job_result_id))
        .where(Document.user_id == user_id)
        .where(Document.namespace == namespace)
        .where(Document.status == 'active')
        .where(DocumentChunk.term_search_text.is_not(None))
        .where(or_(*conditions))
        .distinct()
        .limit(limit)
    )
    if exclude_document_ids:
        stmt = stmt.where(Document.document_id.notin_(list(exclude_document_ids)))

    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


# ------------------------------------------------------------------
# Edge expansion (aligned with KB KGIndex.neighbors)
# ------------------------------------------------------------------

async def _expand_by_edges(
    db: AsyncSession,
    *,
    document_ids: list[str],
    user_id: str,
    namespace: str,
    hops: int = 1,
) -> list[str]:
    """Expand document set by following GraphEdge relationships.

    Aligned with KB's KGIndex.neighbors(): traverse edges to include
    related documents. Only queries document-level nodes (no section nodes).
    No weight filtering — edges already passed threshold during publication.
    """
    if not document_ids:
        return document_ids

    current = set(document_ids)

    for hop_idx in range(hops):
        # Find document-level graph nodes for current document set
        doc_node_ids = [f"doc:{did}" for did in current]
        node_stmt = (
            select(GraphNode.node_id, GraphNode.owner_document_id)
            .where(GraphNode.user_id == user_id)
            .where(GraphNode.namespace == namespace)
            .where(GraphNode.node_kind == 'document')
            .where(GraphNode.node_id.in_(doc_node_ids))
        )
        node_result = await db.execute(node_stmt)
        node_rows = node_result.all()
        logger.info(f'  edge_expand hop={hop_idx}: doc_nodes_found={len(node_rows)} (of {len(doc_node_ids)} requested)')

        if not node_rows:
            break

        node_ids = {row[0] for row in node_rows}

        # Follow edges from/to these document nodes
        edge_stmt = (
            select(GraphEdge.source_node_id, GraphEdge.target_node_id)
            .where(GraphEdge.user_id == user_id)
            .where(GraphEdge.namespace == namespace)
            .where(or_(
                GraphEdge.source_node_id.in_(list(node_ids)),
                GraphEdge.target_node_id.in_(list(node_ids)),
            ))
        )
        edge_result = await db.execute(edge_stmt)
        edge_rows = edge_result.all()

        neighbor_node_ids: set[str] = set()
        for src, tgt in edge_rows:
            if src in node_ids:
                neighbor_node_ids.add(tgt)
            if tgt in node_ids:
                neighbor_node_ids.add(src)
        logger.info(f'  edge_expand hop={hop_idx}: edges_traversed={len(edge_rows)} neighbor_nodes={len(neighbor_node_ids)}')

        if not neighbor_node_ids:
            break

        # Resolve neighbor nodes to document_ids
        neighbor_doc_stmt = (
            select(GraphNode.owner_document_id)
            .where(GraphNode.node_id.in_(list(neighbor_node_ids)))
            .where(GraphNode.node_kind == 'document')
        )
        neighbor_doc_result = await db.execute(neighbor_doc_stmt)
        for (doc_id,) in neighbor_doc_result.all():
            current.add(doc_id)

    # Preserve original order, append new ones at end
    ordered = list(document_ids)
    for doc_id in current:
        if doc_id not in document_ids:
            ordered.append(doc_id)
    return ordered


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

async def agent_navigate(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    llm_fn: LLMFn,
    max_files: int = 3,
    max_chunks_per_file: int = 15,
    exclude_document_ids: Sequence[str] = (),
) -> list[str]:
    """Agent-driven KG navigation — returns chunk paths.

    Aligned with KB unified_retriever.agent_navigate():
      Step 1: LLM selects files from knowledge map overview.
      GREP:   term-search hit chunks → include their parent documents.
      Edge:   selected documents → follow edges → include neighbors.
      Step 2: For each file, LLM selects chunk paths from compact previews.

    Returns:
        List of chunk path strings (section_path or source_chunk_path).
        Empty list if no documents or LLM fails.
    """
    t0 = time.monotonic()
    logger.info('\n' + '=' * 70)
    logger.info('  🧭 AGENT NAVIGATE START')
    logger.info(f'  query="{query}"  max_files={max_files}  max_chunks/file={max_chunks_per_file}')
    logger.info('=' * 70)

    overview_text, doc_id_to_name = await _build_knowledge_map_overview(
        db, user_id=user_id, namespace=namespace,
    )
    if overview_text == '(empty)':
        logger.info('  ⚠️  No active documents in namespace, skipping agent navigate')
        return []

    logger.info(f'\n  📋 STEP 0: Knowledge Map Overview ({len(doc_id_to_name)} files)')
    logger.info(f'  {"─" * 60}')
    for line in overview_text.split('\n'):
        logger.info(f'  {line}')
    logger.info(f'  {"─" * 60}')

    # ── Step 1: LLM selects files ──
    logger.info(f'\n  📄 STEP 1: LLM File Selection')
    file_prompt = _FILE_SELECT_PROMPT.format(
        overview=overview_text, query=query, max_files=max_files,
    )
    t1 = time.monotonic()
    try:
        file_response = await llm_fn(file_prompt)
        selected_ids = _parse_json_array(file_response)
        logger.info(f'  LLM raw response: {file_response[:300]}')
        logger.info(f'  Parsed IDs: {selected_ids}')
    except Exception as exc:
        logger.error(f'  ❌ LLM file selection failed: {exc}')
        return []

    elapsed_file = round((time.monotonic() - t1) * 1000)

    exclude_set = set(exclude_document_ids)
    valid_ids = [did for did in selected_ids if did in doc_id_to_name and did not in exclude_set]

    if not valid_ids:
        logger.warning(
            f'  ⚠️  LLM returned no valid files (raw={selected_ids}) in {elapsed_file}ms'
        )
        return []

    logger.info(f'  ✅ LLM selected {len(valid_ids)} files in {elapsed_file}ms:')
    for did in valid_ids:
        logger.info(f'     → [{did}] {doc_id_to_name.get(did, "?")}')

    # ── GREP discovery: include parent documents of term-hit chunks ──
    logger.info(f'\n  🔎 STEP 1b: GREP Discovery')
    try:
        grep_doc_ids = await _grep_discover_document_ids(
            db, user_id=user_id, namespace=namespace, query=query,
            exclude_document_ids=exclude_document_ids,
        )
        logger.info(f'  GREP hit document_ids: {grep_doc_ids}')
        if grep_doc_ids:
            pre_count = len(valid_ids)
            for did in grep_doc_ids:
                if did not in valid_ids and did in doc_id_to_name:
                    valid_ids.append(did)
            added = len(valid_ids) - pre_count
            if added > 0:
                logger.info(f'  ✅ GREP added {added} new documents')
            else:
                logger.info(f'  ℹ️  GREP found {len(grep_doc_ids)} docs but all already selected')
        else:
            logger.info(f'  ℹ️  GREP found no matching documents')
    except Exception as exc:
        logger.warning(f'  ⚠️  GREP discovery failed (ignored): {exc}')

    # ── Edge expansion: include neighbor documents ──
    logger.info(f'\n  🔗 STEP 1c: Edge Expansion')
    logger.info(f'  Input documents: {valid_ids}')
    try:
        expanded_ids = await _expand_by_edges(
            db, document_ids=valid_ids, user_id=user_id, namespace=namespace,
        )
        if len(expanded_ids) > len(valid_ids):
            new_from_edges = [d for d in expanded_ids if d not in valid_ids]
            logger.info(f'  ✅ Edge expansion: {len(valid_ids)} → {len(expanded_ids)} documents')
            for did in new_from_edges:
                logger.info(f'     → added neighbor: [{did}] {doc_id_to_name.get(did, "?")}')
            valid_ids = expanded_ids
        else:
            logger.info(f'  ℹ️  No new neighbors found via edges')
    except Exception as exc:
        logger.warning(f'  ⚠️  Edge expansion failed (ignored): {exc}')

    logger.info(f'\n  📊 STEP 1 SUMMARY: {len(valid_ids)} documents after all expansions:')
    for did in valid_ids:
        logger.info(f'     [{did}] {doc_id_to_name.get(did, "?")}')

    # ── Step 2: For each file, LLM selects chunk paths ──
    logger.info(f'\n  📑 STEP 2: LLM Chunk Path Selection')
    doc_job_map: dict[str, str] = {}
    doc_stmt = (
        select(Document.document_id, Document.current_job_result_id)
        .where(Document.document_id.in_(valid_ids))
    )
    doc_result = await db.execute(doc_stmt)
    for did, jrid in doc_result.all():
        if jrid:
            doc_job_map[did] = jrid

    all_selected_paths: list[str] = []

    for doc_id in valid_ids:
        job_result_id = doc_job_map.get(doc_id)
        if not job_result_id:
            logger.warning(f'  ⚠️  doc={doc_id} has no job_result_id, skipping')
            continue

        doc_name = doc_id_to_name.get(doc_id, doc_id)
        logger.info(f'\n  {"─" * 50}')
        logger.info(f'  📖 Processing: {doc_name} [{doc_id}]')

        chunks_slim = await _build_chunks_slim(
            db, document_id=doc_id, job_result_id=job_result_id,
        )
        if not chunks_slim:
            logger.info(f'  ⚠️  No chunks found for this document')
            continue

        logger.info(f'  chunks_slim: {len(chunks_slim)} entries')
        for ci, c in enumerate(chunks_slim[:10]):
            logger.info(f'    [{ci}] [{c.get("type","?")}] path="{c.get("path","")}"  preview="{c.get("preview","")[:80]}"')
        if len(chunks_slim) > 10:
            logger.info(f'    ... and {len(chunks_slim) - 10} more')

        chunks_text = _format_chunks_for_llm(chunks_slim)
        chunk_prompt = _CHUNK_SELECT_PROMPT.format(
            doc_name=doc_name,
            doc_id=doc_id,
            chunks_overview=chunks_text,
            query=query,
            max_chunks=max_chunks_per_file,
        )

        valid_paths = {c['path'] for c in chunks_slim if c.get('path')}

        t2 = time.monotonic()
        try:
            chunk_response = await llm_fn(chunk_prompt)
            logger.info(f'  LLM raw response: {chunk_response[:300]}')
            selected_paths = [
                path for path in _parse_json_array(chunk_response)
                if path in valid_paths
            ]
        except Exception as exc:
            logger.error(f'  ❌ LLM chunk selection failed: {exc}')
            continue

        elapsed_chunk = round((time.monotonic() - t2) * 1000)
        logger.info(f'  ✅ Selected {len(selected_paths)} paths in {elapsed_chunk}ms:')
        for p in selected_paths:
            logger.info(f'     → {p}')

        rejected = [p for p in _parse_json_array(chunk_response) if p not in valid_paths]
        if rejected:
            logger.warning(f'  ⚠️  {len(rejected)} paths rejected (not in valid_paths): {rejected[:5]}')

        for path in selected_paths:
            if path not in all_selected_paths:
                all_selected_paths.append(path)

    elapsed_total = round((time.monotonic() - t0) * 1000)
    logger.info(f'\n{"=" * 70}')
    logger.info(f'  🧭 AGENT NAVIGATE COMPLETE: {len(all_selected_paths)} paths from {len(valid_ids)} files in {elapsed_total}ms')
    for i, p in enumerate(all_selected_paths):
        logger.info(f'    [{i+1}] {p}')
    logger.info(f'{"=" * 70}')
    return all_selected_paths
