from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.document import RetrievalHitStat


async def _get_existing_hit_stat(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    hit_kind: str,
    document_id: str,
    chunk_id: str | None,
) -> RetrievalHitStat | None:
    result = await db.execute(
        select(RetrievalHitStat)
        .where(RetrievalHitStat.user_id == user_id)
        .where(RetrievalHitStat.namespace == namespace)
        .where(RetrievalHitStat.hit_kind == hit_kind)
        .where(RetrievalHitStat.document_id == document_id)
        .where(RetrievalHitStat.chunk_id == chunk_id)
    )
    return result.scalar_one_or_none()


async def _increment_or_create_hit_stat(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    hit_kind: str,
    document_id: str,
    chunk_id: str | None,
    now: datetime,
) -> None:
    existing = await _get_existing_hit_stat(
        db,
        user_id=user_id,
        namespace=namespace,
        hit_kind=hit_kind,
        document_id=document_id,
        chunk_id=chunk_id,
    )
    if existing is not None:
        existing.hit_count += 1
        existing.last_hit_at = now
        return

    db.add(RetrievalHitStat(
        user_id=user_id,
        namespace=namespace,
        hit_kind=hit_kind,
        document_id=document_id,
        chunk_id=chunk_id,
        hit_count=1,
        last_hit_at=now,
    ))


async def record_retrieval_hits(
    db: AsyncSession,
    *,
    user_id: str,
    namespace: str,
    results: list[dict[str, Any]],
) -> None:
    seen_documents: set[str] = set()
    now = datetime.utcnow()

    for row in results:
        document_id = row.get('document_id')
        chunk_id = row.get('chunk_id')
        if not document_id:
            continue
        if document_id not in seen_documents:
            await _increment_or_create_hit_stat(
                db,
                user_id=user_id,
                namespace=namespace,
                hit_kind='document',
                document_id=document_id,
                chunk_id=None,
                now=now,
            )
            seen_documents.add(document_id)
        if chunk_id:
            await _increment_or_create_hit_stat(
                db,
                user_id=user_id,
                namespace=namespace,
                hit_kind='chunk',
                document_id=document_id,
                chunk_id=chunk_id,
                now=now,
            )

    await db.flush()
