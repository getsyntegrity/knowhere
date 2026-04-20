from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from shared.models.database.document import Document, DocumentChunk, DocumentSection, GraphEdge, GraphNode
from shared.models.database.job_result import JobResult


def is_excluded_section(
    *,
    document_id: str | None,
    section_path: str | None,
    exclude_sections: Iterable[dict[str, str]],
) -> bool:
    document_id = str(document_id or '').strip()
    section_path = str(section_path or '').strip()
    if not document_id or not section_path:
        return False
    for item in exclude_sections:
        if not isinstance(item, dict):
            continue
        if document_id == str(item.get('document_id') or '').strip() and section_path == str(item.get('section_path') or '').strip():
            return True
    return False


@dataclass
class GraphScope:
    user_id: str
    namespace: str


class DocumentGraphService:
    """Write-side graph publication over persisted graph_nodes/graph_edges."""

    def publish_document_graph(self, db: Session, *, user_id: str, namespace: str, document_id: str, job_result_id: str) -> None:
        sections = list(
            db.execute(
                select(DocumentSection)
                .where(DocumentSection.document_id == document_id)
                .where(DocumentSection.job_result_id == job_result_id)
                .order_by(DocumentSection.sort_order)
            ).scalars()
        )

        document = db.execute(
            select(Document).where(Document.document_id == document_id)
        ).scalar_one_or_none()
        if document is None:
            return

        self.remove_document_graph(db, scope=GraphScope(user_id=user_id, namespace=namespace), document_id=document_id)

        document_node_id = f"doc:{document_id}"
        db.add(
            GraphNode(
                node_id=document_node_id,
                user_id=user_id,
                namespace=namespace,
                node_kind='document',
                owner_document_id=document_id,
                job_result_id=job_result_id,
                ref_document_id=document_id,
                ref_section_id=None,
                properties={
                    'source_file_name': document.source_file_name,
                },
            )
        )

        contains_edges = []
        for section in sections:
            section_node_id = f"sec:{section.section_id}"
            db.add(
                GraphNode(
                    node_id=section_node_id,
                    user_id=user_id,
                    namespace=namespace,
                    node_kind='section',
                    owner_document_id=document_id,
                    job_result_id=job_result_id,
                    ref_document_id=document_id,
                    ref_section_id=section.section_id,
                    properties={
                        'section_path': section.section_path,
                        'section_title': section.section_title,
                        'section_level': section.section_level,
                    },
                )
            )
            parent_node_id = f"sec:{section.parent_section_id}" if section.parent_section_id else document_node_id
            contains_edges.append((parent_node_id, section_node_id))

        # Persist nodes before any edge rows can be flushed.
        db.flush()

        for parent_node_id, section_node_id in contains_edges:
            db.add(
                GraphEdge(
                    edge_id=f"contains:{parent_node_id}->{section_node_id}",
                    user_id=user_id,
                    namespace=namespace,
                    edge_kind='contains',
                    source_node_id=parent_node_id,
                    target_node_id=section_node_id,
                    owner_document_id=document_id,
                    job_result_id=job_result_id,
                    is_directed=True,
                    weight=1,
                    properties={},
                )
            )

        other_documents: Sequence[Document] = list(
            db.execute(
                select(Document)
                .where(Document.user_id == user_id)
                .where(Document.namespace == namespace)
                .where(Document.status == 'active')
                .where(Document.document_id != document_id)
            ).scalars()
        )
        for other in other_documents:
            peer_node_id = f"doc:{other.document_id}"
            peer_node = db.execute(
                select(GraphNode).where(GraphNode.node_id == peer_node_id)
            ).scalar_one_or_none()
            if peer_node is None:
                continue
            db.add(
                GraphEdge(
                    edge_id=f"similar:{document_id}<->{other.document_id}",
                    user_id=user_id,
                    namespace=namespace,
                    edge_kind='similar',
                    source_node_id=document_node_id,
                    target_node_id=peer_node_id,
                    owner_document_id=document_id,
                    job_result_id=job_result_id,
                    is_directed=False,
                    weight=1,
                    properties={},
                )
            )

        db.flush()

    def remove_document_graph(self, db: Session, *, scope: GraphScope | None, document_id: str) -> None:
        edge_delete = delete(GraphEdge).where(GraphEdge.owner_document_id == document_id)
        node_delete = delete(GraphNode).where(GraphNode.owner_document_id == document_id)
        if scope is not None:
            edge_delete = edge_delete.where(GraphEdge.user_id == scope.user_id)
            node_delete = node_delete.where(GraphNode.user_id == scope.user_id)
        db.execute(edge_delete)
        db.execute(node_delete)
        db.flush()


class GraphQueryService:
    """Read-side graph service for document routing before canonical chunk hydration."""

    async def find_entry_documents(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
        query: str,
        exclude_document_ids: Iterable[str] = (),
        exclude_sections: Iterable[dict[str, str]] = (),
    ) -> list[str]:
        query_lc = query.lower().strip()
        exclude_document_ids = set(exclude_document_ids)
        stmt = (
            select(GraphNode)
            .where(GraphNode.user_id == user_id)
            .where(GraphNode.namespace == namespace)
            .where(GraphNode.node_kind == 'section')
        )
        result = await db.execute(stmt)
        candidates = []
        for node in result.scalars().all():
            if node.ref_document_id in exclude_document_ids:
                continue
            props = node.properties or {}
            if is_excluded_section(
                document_id=node.ref_document_id,
                section_path=props.get('section_path'),
                exclude_sections=exclude_sections,
            ):
                continue
            haystacks = [
                str(props.get('section_title') or '').lower(),
                str(props.get('section_path') or '').lower(),
            ]
            if any(query_lc and query_lc in haystack for haystack in haystacks):
                candidates.append(node.ref_document_id)
        seen = []
        for doc_id in candidates:
            if doc_id and doc_id not in seen:
                seen.append(doc_id)
        return seen

    async def collect_candidate_chunks(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
        entry_document_ids: Sequence[str],
        query: str,
        top_k: int,
        exclude_sections: Iterable[dict[str, str]] = (),
    ) -> list[dict[str, Any]]:
        if not entry_document_ids:
            return []
        stmt = (
            select(Document, DocumentChunk, DocumentSection, JobResult)
            .join(DocumentChunk, (DocumentChunk.document_id == Document.document_id) & (DocumentChunk.job_result_id == Document.current_job_result_id))
            .outerjoin(DocumentSection, DocumentSection.section_id == DocumentChunk.section_id)
            .join(JobResult, JobResult.id == DocumentChunk.job_result_id)
            .where(Document.user_id == user_id)
            .where(Document.namespace == namespace)
            .where(Document.status == 'active')
            .where(Document.document_id.in_(list(entry_document_ids)))
            .where(DocumentChunk.content.ilike(f'%{query}%'))
            .order_by(DocumentChunk.sort_order)
            .limit(top_k)
        )
        result = await db.execute(stmt)
        rows = []
        for document, chunk, section, job_result in result.all():
            section_path = section.section_path if section else None
            if is_excluded_section(
                document_id=document.document_id,
                section_path=section_path,
                exclude_sections=exclude_sections,
            ):
                continue
            rows.append({
                'document_id': document.document_id,
                'chunk_id': chunk.chunk_id,
                'section_id': chunk.section_id,
                'section_path': section_path,
                'source_file_name': document.source_file_name,
                'chunk_type': chunk.chunk_type,
                'content': chunk.content,
                'score': 2.0,
                'file_path': chunk.file_path,
                'chunk_metadata': chunk.chunk_metadata or {},
                'job_result_id': chunk.job_result_id,
                'job_id': job_result.job_id if job_result else None,
            })
        return rows
