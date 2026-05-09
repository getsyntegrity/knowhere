"""
Canonical retrieval publication service.

This module owns the retrieval-specific publication work that happens during
job finalization. The job lifecycle service should orchestrate transaction
boundaries and call this service, not define retrieval state construction.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.models.database.document import Document, DocumentChunk, DocumentSection
from shared.models.database.job import Job
from shared.models.database.job_result import JobResult
from shared.services.retrieval.graph_service import DocumentGraphService, GraphScope
from shared.services.retrieval.lexical_text import (
    build_content_lexical_text,
    build_content_search_text,
    build_path_lexical_text,
    build_path_search_text,
    build_term_search_text,
    section_path_from_chunk_path,
)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RetrievalPublicationService:

    # ── Chunk-level content-hash dedup ──────────────────────────────────
    # Mirrors graph_builder._dedup_chunks_by_content but operates on
    # the DB document_chunks table instead of local knowledge_graph.json.

    @staticmethod
    def _collect_existing_chunk_id_map(
        db: Session,
        *,
        user_id: str,
        namespace: str,
    ) -> Dict[str, str]:
        """Return {chunk_id -> document_id} for all active document chunks
        in the given (user_id, namespace) scope.

        Only considers chunks belonging to the *current* revision of each
        active document (Document.current_job_result_id == DocumentChunk.job_result_id).
        """
        rows = db.execute(
            select(DocumentChunk.chunk_id, DocumentChunk.document_id)
            .join(
                Document,
                (Document.document_id == DocumentChunk.document_id)
                & (Document.current_job_result_id == DocumentChunk.job_result_id),
            )
            .where(
                Document.user_id == user_id,
                Document.namespace == namespace,
                Document.status == "active",
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _dedup_chunks_by_content(
        new_chunks: List[Dict[str, Any]],
        existing_chunk_map: Dict[str, str],
    ) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Filter new_chunks: discard any whose chunk_id already exists.

        Uses the same deterministic know_id (content-hash) comparison as
        graph_builder._dedup_chunks_by_content.

        Returns:
            (deduped_chunks, overlap_by_document)
            - deduped_chunks: chunks whose chunk_id is NOT in existing_chunk_map
            - overlap_by_document: {document_id: count} of skipped chunks per
              existing document (for observability logging)
        """
        overlap_by_document: Dict[str, int] = defaultdict(int)
        deduped: List[Dict[str, Any]] = []
        skipped = 0

        for chunk in new_chunks:
            cid = str(chunk.get("chunk_id") or chunk.get("know_id", ""))
            if cid and cid in existing_chunk_map:
                skipped += 1
                overlap_by_document[existing_chunk_map[cid]] += 1
            else:
                deduped.append(chunk)

        if skipped > 0:
            logger.warning(
                f"📊 DB chunk dedup: {skipped}/{len(new_chunks)} duplicate chunks "
                f"skipped (by chunk_id), {len(deduped)} new chunks to insert. "
                f"Overlap by document: {dict(overlap_by_document)}"
            )
        return deduped, dict(overlap_by_document)

    @classmethod
    def garbage_collect_and_dedup_local_media(
        cls,
        db: Session,
        *,
        job_id: str,
        user_id: str,
        namespace: str,
        add_dir: str,
        chunks: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Deduplicates chunks against the DB and physically deletes associated redundant 
        media files (images/tables) from the local add_dir before ZIP packaging.
        Returns the deduplicated chunks.
        """
        import os
        
        logger.info(f"[{job_id}] Starting local GC for redundant media files in namespace: {namespace}...")
        try:
            existing_map = cls._collect_existing_chunk_id_map(
                db, user_id=user_id, namespace=namespace
            )
            deduped_chunks, overlap = cls._dedup_chunks_by_content(chunks, existing_map)
            
            stats = {
                "total_incoming": len(chunks),
                "duplicates_skipped": len(chunks) - len(deduped_chunks),
                "new_chunks_inserted": len(deduped_chunks),
                "overlap_by_document": overlap,
            }
            
            if len(deduped_chunks) < len(chunks):
                active_paths = set()
                for c in deduped_chunks:
                    fp = c.get("metadata", {}).get("file_path") or c.get("file_path")
                    if fp:
                        active_paths.add(fp)
                        
                deleted_count = 0
                if add_dir and os.path.exists(add_dir):
                    for c in chunks:
                        fp = c.get("metadata", {}).get("file_path") or c.get("file_path")
                        if fp and fp not in active_paths:
                            abs_path = os.path.join(add_dir, fp)
                            if os.path.exists(abs_path):
                                os.remove(abs_path)
                                deleted_count += 1
                                
                logger.info(f"[{job_id}] GC complete: permanently removed {deleted_count} redundant local media files.")
                return deduped_chunks, stats
            else:
                logger.info(f"[{job_id}] GC complete: no redundant chunks found.")
                return chunks, stats
        except Exception as e:
            logger.error(f"[{job_id}] GC failed (non-fatal): {e}")
            stats = {
                "total_incoming": len(chunks),
                "duplicates_skipped": 0,
                "new_chunks_inserted": len(chunks),
                "overlap_by_document": {},
            }
            return chunks, stats

    # ── Public API ──────────────────────────────────────────────────────

    def get_existing_document_scope(
        self,
        db: Session,
        *,
        job_id: str,
    ) -> Optional[Dict[str, str]]:
        job = db.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
        if not job:
            return None

        metadata = job.job_metadata or {}
        document_id = metadata.get("document_id")
        if not document_id:
            return None

        document = db.execute(
            select(Document).where(Document.document_id == document_id)
        ).scalar_one_or_none()
        if not document:
            return None

        return {"document_id": document.document_id, "namespace": document.namespace}

    def publish_document_state(
        self,
        db: Session,
        *,
        job_id: str,
        job_result_id: str,
        chunks: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        job = db.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
        if not job:
            logger.warning(f"Job not found for document publication: {job_id}")
            return None

        return self._publish_document_state_for_job(
            db,
            job=job,
            job_result_id=job_result_id,
            chunks=chunks,
        )

    def _publish_document_state_for_job(
        self,
        db: Session,
        *,
        job: Job,
        job_result_id: str,
        chunks: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

        job_metadata = job.job_metadata or {}
        namespace = job_metadata.get("namespace") or "default"
        document_id = job_metadata.get("document_id")
        source_file_name = job_metadata.get("source_file_name") or job_metadata.get("file_name")

        deduped_chunks = chunks

        # If ALL chunks are duplicates → skip document creation entirely
        if not deduped_chunks:
            logger.warning(
                f"⏭️  All chunks are duplicates of existing documents. "
                f"Skipping document creation for job_id={job.job_id}."
            )
            return {
                "user_id": str(job.user_id),
                "namespace": namespace,
                "document_id": None,
                "skipped_all_duplicate": True,
            }

        # ── Document upsert (original logic, but only for deduped chunks) ──
        document = None
        if document_id:
            document = db.execute(
                select(Document)
                .where(
                    Document.document_id == document_id,
                    Document.user_id == str(job.user_id),
                )
                .with_for_update()
            ).scalar_one_or_none()

        if document is None:
            document = Document(
                document_id=document_id or f"doc_{uuid4().hex[:12]}",
                user_id=str(job.user_id),
                namespace=namespace,
                status="active",
                current_job_result_id=job_result_id,
                source_file_name=source_file_name,
            )
            db.add(document)
        else:
            namespace = namespace or document.namespace
            if self._is_stale_document_completion(
                db,
                document=document,
                job=job,
            ):
                logger.warning(
                    f"Skipping stale document publication: job_id={job.job_id}, document_id={document.document_id}"
                )
                return None
            document.status = "active"
            document.archived_at = None
            document.current_job_result_id = job_result_id
            document.source_file_name = source_file_name or document.source_file_name
            document.updated_at = utc_now_naive()

        db.flush()
        document_id = document.document_id
        result = db.execute(select(JobResult).where(JobResult.id == job_result_id))
        job_result = result.scalar_one_or_none()
        if job_result:
            job_result.document_id = document_id
        namespace = namespace or document.namespace

        db.execute(
            delete(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .where(DocumentChunk.job_result_id == job_result_id)
        )
        db.execute(
            delete(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .where(DocumentSection.job_result_id == job_result_id)
        )

        # ── Insert only deduped (non-duplicate) chunks ──────────────────
        sections_by_path: Dict[str, DocumentSection] = {}
        for index, chunk in enumerate(deduped_chunks):
            chunk_metadata = chunk.get("metadata") or {}
            source_path = chunk_metadata.get("path") or chunk.get("path")
            section_path = section_path_from_chunk_path(source_path)
            section = sections_by_path.get(section_path)
            if section is None:
                path_parts = [p for p in section_path.split(" / ") if p]
                # Ensure all ancestor sections exist (top-down)
                for depth in range(1, len(path_parts) + 1):
                    ancestor_path = " / ".join(path_parts[:depth])
                    if ancestor_path in sections_by_path:
                        continue
                    ancestor_parent_id = None
                    if depth > 1:
                        parent_path = " / ".join(path_parts[:depth - 1])
                        parent = sections_by_path.get(parent_path)
                        if parent is not None:
                            ancestor_parent_id = parent.section_id
                    ancestor_section = DocumentSection(
                        user_id=str(job.user_id),
                        namespace=namespace,
                        document_id=document_id,
                        job_result_id=job_result_id,
                        parent_section_id=ancestor_parent_id,
                        section_path=ancestor_path,
                        section_title=path_parts[depth - 1],
                        section_level=depth,
                        section_metadata={},
                        sort_order=len(sections_by_path),
                    )
                    db.add(ancestor_section)
                    db.flush()
                    sections_by_path[ancestor_path] = ancestor_section
                section = sections_by_path[section_path]

            chunk_id = chunk.get("chunk_id") or f"chunk_{uuid4().hex[:12]}"
            section_summary = section.summary if section else None
            section_path_str = section.section_path if section else "Root"
            section_title_str = section.section_title if section else None
            path_text = f"{source_file_name or ''} {section_path_str}".strip()

            db.add(
                DocumentChunk(
                    id=f"dchk_{uuid4().hex[:12]}",
                    chunk_id=chunk_id,
                    user_id=str(job.user_id),
                    namespace=namespace,
                    document_id=document_id,
                    job_result_id=job_result_id,
                    section_id=section.section_id,
                    chunk_type=chunk.get("type") or chunk.get("chunk_type") or "text",
                    content=chunk.get("content") or chunk.get("text"),
                    content_lexical_text=build_content_lexical_text(chunk),
                    path_lexical_text=build_path_lexical_text(source_path),
                    content_search_text=build_content_search_text(
                        chunk, section_summary=section_summary
                    ),
                    path_search_text=build_path_search_text(
                        source_file_name=source_file_name,
                        section_path=section_path_str,
                        section_title=section_title_str,
                        section_summary=section_summary,
                    ),
                    term_search_text=build_term_search_text(chunk, path_text=path_text),
                    source_chunk_path=source_path,
                    file_path=chunk_metadata.get("file_path") or chunk.get("file_path"),
                    chunk_metadata=chunk_metadata,
                    sort_order=chunk.get("order", index),
                )
            )

        db.flush()
        return {
            "user_id": str(job.user_id),
            "namespace": namespace,
            "document_id": document_id,
        }

    def publish_document_graph(
        self,
        db: Session,
        *,
        job_id: str,
        job_result_id: str,
    ) -> None:
        job = db.execute(select(Job).where(Job.job_id == job_id)).scalar_one_or_none()
        if not job:
            raise RuntimeError(f"Job not found for graph publication: {job_id}")

        self._publish_document_graph_for_job(db, job=job, job_result_id=job_result_id)

    def _publish_document_graph_for_job(
        self,
        db: Session,
        *,
        job: Job,
        job_result_id: str,
    ) -> None:

        metadata = job.job_metadata or {}
        namespace = metadata.get("namespace") or "default"
        document_id = metadata.get("document_id")
        if not document_id:
            document = db.execute(
                select(Document).where(Document.current_job_result_id == job_result_id)
            ).scalar_one_or_none()
            document_id = document.document_id if document else None
        if not document_id:
            raise RuntimeError(
                f"Document not found for graph publication: job_id={job.job_id}"
            )

        DocumentGraphService().publish_document_graph(
            db,
            user_id=str(job.user_id),
            namespace=namespace,
            document_id=document_id,
            job_result_id=job_result_id,
        )

    def remove_document_graph(
        self,
        db: Session,
        *,
        user_id: str,
        namespace: str,
        document_id: str,
    ) -> None:
        DocumentGraphService().remove_document_graph(
            db,
            scope=GraphScope(user_id=user_id, namespace=namespace),
            document_id=document_id,
        )

    def _is_stale_document_completion(
        self,
        db: Session,
        *,
        document: Document,
        job: Job,
    ) -> bool:
        current_job_result_id = getattr(document, "current_job_result_id", None)
        if not current_job_result_id:
            return False

        current_job_result = db.execute(
            select(JobResult).where(JobResult.id == current_job_result_id)
        ).scalar_one_or_none()
        current_job_id = getattr(current_job_result, "job_id", None)
        if current_job_result is None or not current_job_id:
            return False

        current_job = db.execute(
            select(Job).where(Job.job_id == current_job_id)
        ).scalar_one_or_none()
        if current_job is None:
            return False

        current_created_at = getattr(current_job, "created_at", None)
        candidate_created_at = getattr(job, "created_at", None)
        if current_created_at is None or candidate_created_at is None:
            return False

        return current_created_at > candidate_created_at
