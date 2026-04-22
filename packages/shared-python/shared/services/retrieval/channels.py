"""
Independent retrieval channels for checkerboard search.

Each channel queries the full scoped corpus independently and returns
ranked rows. Channels are fused via RRF in the orchestrator.
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.services.retrieval.graph_service import is_excluded_section
from shared.utils.text_utils import tokenize2stw_remove


def tokenize_query_for_fts(query: str) -> str:
    """Jieba-tokenize a query string for plainto_tsquery('simple', ...) compatibility."""
    tokens = tokenize2stw_remove([query], stopwords=[], link_char=" ")
    return tokens[0] if tokens else query


_SCOPED_CORPUS_CTE = """
WITH scoped_chunks AS (
    SELECT
        dc.id,
        dc.chunk_id,
        dc.document_id,
        dc.section_id,
        dc.chunk_type,
        dc.content,
        dc.file_path,
        dc.chunk_metadata,
        dc.job_result_id,
        dc.sort_order,
        dc.content_search_text,
        dc.content_search_tsv,
        dc.path_search_text,
        dc.path_search_tsv,
        dc.term_search_text,
        d.source_file_name,
        d.user_id,
        d.namespace,
        ds.section_path,
        jr.job_id
    FROM document_chunks dc
    JOIN documents d
        ON d.document_id = dc.document_id
        AND d.current_job_result_id = dc.job_result_id
    LEFT JOIN document_sections ds
        ON ds.section_id = dc.section_id
    JOIN job_results jr
        ON jr.id = dc.job_result_id
    WHERE d.user_id = :user_id
        AND d.namespace = :namespace
        AND d.status = 'active'
        {exclude_clause}
)
"""


def _build_exclude_clause(exclude_document_ids: list[str]) -> str:
    if not exclude_document_ids:
        return ""
    return "AND d.document_id NOT IN :excluded_doc_ids"


def _build_base_params(
    *,
    user_id: str,
    namespace: str,
    exclude_document_ids: list[str],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "user_id": user_id,
        "namespace": namespace,
    }
    if exclude_document_ids:
        params["excluded_doc_ids"] = tuple(exclude_document_ids)
    return params


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def _filter_excluded_sections(
    rows: list[dict[str, Any]],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not exclude_sections:
        return rows
    return [
        row for row in rows
        if not is_excluded_section(
            document_id=row.get("document_id"),
            section_path=row.get("section_path"),
            exclude_sections=exclude_sections,
        )
    ]


async def path_channel(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Path channel: full-text search on path_search_tsv using ts_rank."""
    tokenized_query = tokenize_query_for_fts(query)
    if not tokenized_query.strip():
        return []

    recall_k = top_k * 2
    exclude_clause = _build_exclude_clause(exclude_document_ids)
    params = _build_base_params(
        user_id=user_id,
        namespace=namespace,
        exclude_document_ids=exclude_document_ids,
    )
    params["tokenized_query"] = tokenized_query
    params["recall_k"] = recall_k

    sql = _SCOPED_CORPUS_CTE.format(exclude_clause=exclude_clause) + """
    SELECT
        sc.*,
        ts_rank(sc.path_search_tsv, plainto_tsquery('simple', :tokenized_query)) AS rank_score
    FROM scoped_chunks sc
    WHERE sc.path_search_tsv @@ plainto_tsquery('simple', :tokenized_query)
    ORDER BY rank_score DESC
    LIMIT :recall_k
    """

    result = await db.execute(text(sql), params)
    rows = [_row_to_dict(r) for r in result.all()]
    rows = _filter_excluded_sections(rows, exclude_sections)

    for row in rows:
        row["score"] = row.get("rank_score", 0.0)

    return rows


async def content_channel(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Content channel: FTS recall on content_search_tsv, then BM25 re-rank in Python."""
    tokenized_query = tokenize_query_for_fts(query)
    if not tokenized_query.strip():
        return []

    recall_k = top_k * 3
    exclude_clause = _build_exclude_clause(exclude_document_ids)
    params = _build_base_params(
        user_id=user_id,
        namespace=namespace,
        exclude_document_ids=exclude_document_ids,
    )
    params["tokenized_query"] = tokenized_query
    params["recall_k"] = recall_k

    sql = _SCOPED_CORPUS_CTE.format(exclude_clause=exclude_clause) + """
    SELECT
        sc.*,
        ts_rank(sc.content_search_tsv, plainto_tsquery('simple', :tokenized_query)) AS rank_score
    FROM scoped_chunks sc
    WHERE sc.content_search_tsv @@ plainto_tsquery('simple', :tokenized_query)
    ORDER BY rank_score DESC
    LIMIT :recall_k
    """

    result = await db.execute(text(sql), params)
    rows = [_row_to_dict(r) for r in result.all()]
    rows = _filter_excluded_sections(rows, exclude_sections)

    if not rows:
        return []

    rows = _bm25_rerank(rows, tokenized_query)
    return rows


def _bm25_rerank(rows: list[dict[str, Any]], tokenized_query: str) -> list[dict[str, Any]]:
    """Re-rank FTS recall set using BM25Okapi over pre-tokenized content_search_text."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank_bm25 not installed, skipping BM25 re-rank")
        for row in rows:
            row["score"] = row.get("rank_score", 0.0)
        return rows

    corpus = [
        (row.get("content_search_text") or "").split()
        for row in rows
    ]
    query_tokens = tokenized_query.split()

    if not corpus or not query_tokens:
        for row in rows:
            row["score"] = row.get("rank_score", 0.0)
        return rows

    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query_tokens)

    for i, row in enumerate(rows):
        row["score"] = float(scores[i])

    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


async def term_channel(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    query: str,
    top_k: int,
    exclude_document_ids: list[str],
    exclude_sections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Term/grep channel: independent search over full corpus with substring matching."""
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    units = re.findall(r"[一-鿿]+|[a-zA-Z0-9]+", query_lower)
    units = [u for u in units if len(u) > 1]

    if not units and not query_lower:
        return []

    exclude_clause = _build_exclude_clause(exclude_document_ids)
    params = _build_base_params(
        user_id=user_id,
        namespace=namespace,
        exclude_document_ids=exclude_document_ids,
    )

    ilike_conditions = []
    for i, unit in enumerate(units):
        param_key = f"unit_{i}"
        ilike_conditions.append(f"LOWER(sc.term_search_text) LIKE :{param_key}")
        params[param_key] = f"%{unit}%"

    if not ilike_conditions:
        ilike_conditions.append("LOWER(sc.term_search_text) LIKE :full_query")
        params["full_query"] = f"%{query_lower}%"

    where_clause = " OR ".join(ilike_conditions)
    recall_k = top_k * 3
    params["recall_k"] = recall_k

    sql = _SCOPED_CORPUS_CTE.format(exclude_clause=exclude_clause) + f"""
    SELECT sc.*
    FROM scoped_chunks sc
    WHERE sc.term_search_text IS NOT NULL
        AND ({where_clause})
    LIMIT :recall_k
    """

    result = await db.execute(text(sql), params)
    rows = [_row_to_dict(r) for r in result.all()]
    rows = _filter_excluded_sections(rows, exclude_sections)

    scored: list[dict[str, Any]] = []
    for row in rows:
        haystack = (row.get("term_search_text") or "").lower()
        if query_lower in haystack:
            row["score"] = 100.0
            scored.append(row)
        elif units:
            hit_count = sum(1 for u in units if u in haystack)
            if hit_count > 0:
                row["score"] = float(hit_count)
                scored.append(row)

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored
