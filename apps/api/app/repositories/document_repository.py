"""
Document data access for retrieval document lifecycle flows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.document import Document


class DocumentRepository:
    async def list_by_user_namespace(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
    ) -> Sequence[Document]:
        result = await db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .where(Document.namespace == namespace)
            .where(Document.status != "archived")
            .order_by(Document.updated_at.desc())
        )
        return result.scalars().all()

    async def get_document(
        self,
        db: AsyncSession,
        *,
        document_id: str,
        user_id: str,
    ) -> Document | None:
        result = await db.execute(
            select(Document)
            .where(Document.document_id == document_id)
            .where(Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def archive_document(
        self,
        db: AsyncSession,
        *,
        document: Document,
    ) -> Document:
        document.status = "archived"
        document.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return document
