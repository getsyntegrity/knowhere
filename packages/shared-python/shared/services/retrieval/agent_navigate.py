"""Agent-driven KG navigation for retrieval.

Two-stage LLM-driven document routing:
  1. LLM reads a knowledge map overview (file-level metadata) and selects relevant files.
  2. For each file, LLM reads compact chunk previews and selects relevant chunks.

Falls back gracefully when LLM is unavailable or fails.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Sequence

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.document import Document, DocumentChunk, DocumentSection, RetrievalHitStat
from shared.models.database.job_result import JobResult
from shared.services.retrieval.llm_adapter import LLMFn

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
Return ONLY a JSON array of chunk_id strings from the list above,
e.g.: ["chunk_abc", "chunk_def"]
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
        select(RetrievalHitStat.document_id, RetrievalHitStat.hit_count)
        .where(RetrievalHitStat.user_id == user_id)
        .where(RetrievalHitStat.namespace == namespace)
        .where(RetrievalHitStat.hit_kind == 'document')
        .where(RetrievalHitStat.document_id.in_(doc_ids))
    )
    hit_result = await db.execute(hit_stmt)
    hit_counts: dict[str, int] = {row[0]: row[1] for row in hit_result.all()}

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
        hits = hit_counts.get(did, 0)
        titles = section_titles.get(did, '')

        line = f'- [{did}] {name}  chunks={stats["total"]}'
        if stats['media'] > 0:
            line += f' media={stats["media"]}'
        if hits > 0:
            line += f' hits={hits}'
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
    """Build compact chunk descriptors for LLM chunk selection."""
    stmt = (
        select(DocumentChunk.chunk_id, DocumentChunk.chunk_type, DocumentChunk.content, DocumentSection.section_path)
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .where(DocumentChunk.document_id == document_id)
        .where(DocumentChunk.job_result_id == job_result_id)
        .order_by(DocumentChunk.sort_order)
        .limit(_MAX_CHUNKS_SLIM_PER_DOC)
    )
    result = await db.execute(stmt)
    chunks: list[dict[str, str]] = []
    for chunk_id, chunk_type, content, section_path in result.all():
        preview = re.sub(r'\s+', ' ', str(content or '')).strip()[:_CONTENT_PREVIEW_LEN]
        entry: dict[str, str] = {
            'chunk_id': chunk_id,
            'type': chunk_type or 'text',
        }
        if section_path:
            entry['path'] = section_path
        if preview:
            entry['preview'] = preview
        chunks.append(entry)
    return chunks


def _format_chunks_for_llm(chunks: list[dict[str, str]], max_chars: int = 4000) -> str:
    """Format compact chunk descriptors for LLM prompt."""
    if not chunks:
        return '(no chunks available)'

    def _render(include_preview: bool) -> str:
        lines: list[str] = []
        for c in chunks:
            line = f'- [{c["type"]}] id={c["chunk_id"]}'
            if c.get('path'):
                line += f' path="{c["path"]}"'
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
) -> list[dict[str, Any]]:
    """Agent-driven KG navigation — returns hydrated chunk rows.

    Two-stage LLM routing:
      1. LLM selects relevant files from a knowledge map overview.
      2. For each file, LLM selects relevant chunks from compact previews.

    Returns chunk rows in the same format as list_graph_routed_chunks().
    """
    t0 = time.monotonic()

    overview_text, doc_id_to_name = await _build_knowledge_map_overview(
        db, user_id=user_id, namespace=namespace,
    )
    if overview_text == '(empty)':
        logger.info('retrieval: agent_navigate: no active documents, skipping')
        return []

    logger.info(
        f'retrieval: agent_navigate: kg_overview={len(doc_id_to_name)} files'
    )

    # ── Step 1: LLM selects files ──
    file_prompt = _FILE_SELECT_PROMPT.format(
        overview=overview_text, query=query, max_files=max_files,
    )
    t1 = time.monotonic()
    try:
        file_response = await llm_fn(file_prompt)
        selected_ids = _parse_json_array(file_response)
    except Exception as exc:
        logger.error(f'retrieval: agent_navigate: LLM file selection failed: {exc}')
        return []

    elapsed_file = round((time.monotonic() - t1) * 1000)

    exclude_set = set(exclude_document_ids)
    valid_ids = [did for did in selected_ids if did in doc_id_to_name and did not in exclude_set]

    if not valid_ids:
        logger.warning(
            f'retrieval: agent_navigate: LLM returned no valid files '
            f'(raw={selected_ids}) in {elapsed_file}ms'
        )
        return []

    logger.info(
        f'retrieval: agent_navigate: llm_file_select → '
        f'{[doc_id_to_name.get(d, d) for d in valid_ids]} in {elapsed_file}ms'
    )

    # ── Step 2: For each file, LLM selects chunks ──
    doc_job_map: dict[str, str] = {}
    doc_stmt = (
        select(Document.document_id, Document.current_job_result_id)
        .where(Document.document_id.in_(valid_ids))
    )
    doc_result = await db.execute(doc_stmt)
    for did, jrid in doc_result.all():
        if jrid:
            doc_job_map[did] = jrid

    all_selected_chunk_ids: list[str] = []

    for doc_id in valid_ids:
        job_result_id = doc_job_map.get(doc_id)
        if not job_result_id:
            continue

        chunks_slim = await _build_chunks_slim(
            db, document_id=doc_id, job_result_id=job_result_id,
        )
        if not chunks_slim:
            logger.debug(f'retrieval: agent_navigate: no chunks for doc={doc_id}')
            continue

        chunks_text = _format_chunks_for_llm(chunks_slim)
        chunk_prompt = _CHUNK_SELECT_PROMPT.format(
            doc_name=doc_id_to_name.get(doc_id, doc_id),
            doc_id=doc_id,
            chunks_overview=chunks_text,
            query=query,
            max_chunks=max_chunks_per_file,
        )

        valid_chunk_ids = {c['chunk_id'] for c in chunks_slim}

        t2 = time.monotonic()
        try:
            chunk_response = await llm_fn(chunk_prompt)
            selected_chunks = [
                cid for cid in _parse_json_array(chunk_response)
                if cid in valid_chunk_ids
            ]
        except Exception as exc:
            logger.error(
                f'retrieval: agent_navigate: LLM chunk selection failed '
                f'for doc={doc_id}: {exc}'
            )
            continue

        elapsed_chunk = round((time.monotonic() - t2) * 1000)
        logger.info(
            f'retrieval: agent_navigate: llm_chunk_select '
            f'doc={doc_id_to_name.get(doc_id, doc_id)} → '
            f'{len(selected_chunks)} chunks in {elapsed_chunk}ms'
        )

        for cid in selected_chunks:
            if cid not in all_selected_chunk_ids:
                all_selected_chunk_ids.append(cid)

    if not all_selected_chunk_ids:
        logger.info('retrieval: agent_navigate: no chunks selected by LLM')
        return []

    # ── Step 3: Hydrate selected chunks ──
    rows = await _hydrate_chunks_by_ids(db, chunk_ids=all_selected_chunk_ids)

    elapsed_total = round((time.monotonic() - t0) * 1000)
    logger.info(
        f'retrieval: agent_navigate: total={len(rows)} chunks '
        f'from {len(valid_ids)} files in {elapsed_total}ms'
    )
    return rows


async def _hydrate_chunks_by_ids(
    db: AsyncSession,
    *,
    chunk_ids: list[str],
) -> list[dict[str, Any]]:
    """Load full chunk rows by chunk_id, matching the standard retrieval row format."""
    if not chunk_ids:
        return []

    stmt = (
        select(Document, DocumentChunk, DocumentSection, JobResult)
        .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id) & (DocumentChunk.job_result_id == Document.current_job_result_id))
        .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
        .join(JobResult, JobResult.id == DocumentChunk.job_result_id)
        .where(DocumentChunk.chunk_id.in_(chunk_ids))
        .where(Document.status == 'active')
    )
    result = await db.execute(stmt)

    chunk_id_order = {cid: idx for idx, cid in enumerate(chunk_ids)}
    rows: list[dict[str, Any]] = []
    for document, chunk, section, job_result in result.all():
        rows.append({
            'document_id': document.document_id,
            'chunk_id': chunk.chunk_id,
            'section_id': chunk.section_id,
            'section_path': section.section_path if section else None,
            'source_file_name': document.source_file_name,
            'chunk_type': chunk.chunk_type,
            'content': chunk.content,
            'score': 2.0,
            'file_path': chunk.file_path,
            'chunk_metadata': chunk.chunk_metadata or {},
            'job_result_id': chunk.job_result_id,
            'job_id': job_result.job_id if job_result else None,
        })

    rows.sort(key=lambda r: chunk_id_order.get(str(r.get('chunk_id', '')), 10**9))
    return rows
