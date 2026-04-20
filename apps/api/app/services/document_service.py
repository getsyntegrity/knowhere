"""
Application service for document lifecycle routes.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from shared.services.retrieval.cache_service import invalidate_retrieval_cache_namespaces
from shared.services.retrieval.graph_service import DocumentGraphService, GraphScope


def document_payload(document) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "namespace": document.namespace,
        "status": document.status,
        "current_job_result_id": document.current_job_result_id,
        "source_file_name": document.source_file_name,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "archived_at": document.archived_at.isoformat() if document.archived_at else None,
    }


class DocumentService:
    def __init__(
        self,
        *,
        repository: DocumentRepository | None = None,
        graph_service: DocumentGraphService | None = None,
    ) -> None:
        self._repository = repository or DocumentRepository()
        self._graph_service = graph_service or DocumentGraphService()

    async def list_documents(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
    ) -> list[dict[str, Any]]:
        documents = await self._repository.list_by_user_namespace(
            db,
            user_id=user_id,
            namespace=namespace,
        )
        return [document_payload(document) for document in documents]

    async def get_document(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        document = await self._repository.get_document(
            db,
            user_id=user_id,
            document_id=document_id,
        )
        if document is None:
            return None
        return document_payload(document)

    async def archive_document(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        document = await self._repository.get_document(
            db,
            user_id=user_id,
            document_id=document_id,
        )
        if document is None:
            return None

        previous_namespace = document.namespace
        await self._repository.archive_document(db, document=document)
        await db.run_sync(
            lambda sync_db: self._graph_service.remove_document_graph(
                sync_db,
                scope=GraphScope(user_id=user_id, namespace=document.namespace),
                document_id=document_id,
            )
        )
        await db.commit()
        try:
            await invalidate_retrieval_cache_namespaces(
                user_id=user_id,
                namespaces=[previous_namespace],
            )
        except Exception:
            pass
        return document_payload(document)
