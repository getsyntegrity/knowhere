from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.document import RetrievalHitStat


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
            db.add(RetrievalHitStat(
                user_id=user_id,
                namespace=namespace,
                hit_kind='document',
                document_id=document_id,
                chunk_id=None,
                hit_count=1,
                last_hit_at=now,
            ))
            seen_documents.add(document_id)
        if chunk_id:
            db.add(RetrievalHitStat(
                user_id=user_id,
                namespace=namespace,
                hit_kind='chunk',
                document_id=document_id,
                chunk_id=chunk_id,
                hit_count=1,
                last_hit_at=now,
            ))

    await db.flush()
