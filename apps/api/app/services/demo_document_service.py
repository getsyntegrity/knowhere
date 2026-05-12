"""API-owned canonical demo document catalog and materialization."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.demo_materialization import DemoMaterialization
from shared.models.database.document import Document
from shared.models.database.job import Job
from shared.models.database.job_result import JobResult
from shared.services.retrieval.publication_service import RetrievalPublicationService


@dataclass(frozen=True)
class DemoCitationDefinition:
    """Curated answer citation that resolves to a canonical demo chunk."""

    section_path: str
    description: str
    content: str


@dataclass(frozen=True)
class DemoExampleDefinition:
    """Curated user-facing demo question and answer."""

    id: str
    question: str
    answer: str
    citations: tuple[DemoCitationDefinition, ...]


@dataclass(frozen=True)
class DemoSourceDefinition:
    """Canonical demo source metadata and local asset pointers."""

    demo_source_id: str
    canonical_document_id: str
    title: str
    mime_type: str
    size_bytes: int
    asset_directory: str
    chunk_count: int
    examples: tuple[DemoExampleDefinition, ...]


@dataclass(frozen=True)
class MaterializedDemoSource:
    """User-owned copy of one canonical demo source."""

    demo_source_id: str
    document_id: str
    status: str
    title: str
    mime_type: str
    size_bytes: int
    chunk_count: int


_DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "demo_documents"
_DEMO_SOURCE_DEFINITIONS: tuple[DemoSourceDefinition, ...] = (
    DemoSourceDefinition(
        demo_source_id="demo-tsla-q4-2025",
        canonical_document_id="demo-doc-tsla-q4-2025",
        title="TSLA-Q4-2025-Update.pdf",
        mime_type="application/pdf",
        size_bytes=5_648_867,
        asset_directory="tsla-q4-2025",
        chunk_count=70,
        examples=(
            DemoExampleDefinition(
                id="demo-tsla-q4-2025-xai",
                question="What does the document say about Tesla's xAI investment?",
                answer=(
                    "Tesla entered an agreement on January 16, 2026 to invest "
                    "approximately $2 billion in xAI Series E Preferred Stock.\n\n"
                    "The document also says Tesla and xAI entered a framework "
                    "agreement to evaluate AI collaboration, with the investment "
                    "expected to close in Q1 2026 subject to customary regulatory "
                    "conditions."
                ),
                citations=(
                    DemoCitationDefinition(
                        section_path=(
                            "Default_Root/TSLA-Q4-2025-Update.pdf-->OTHER UPDATES"
                        ),
                        description="xAI investment",
                        content=(
                            "On January 16, 2026, Tesla entered into an agreement "
                            "to invest approximately"
                        ),
                    ),
                ),
            ),
            DemoExampleDefinition(
                id="demo-tsla-q4-2025-energy-storage",
                question="What does the document say about energy storage?",
                answer=(
                    "Tesla achieved its highest quarterly energy storage "
                    "deployments, driven by record Megapack deployments.\n\n"
                    "Energy gross profit reached a record $1.1 billion, marking "
                    "the fifth consecutive record quarter.\n\n"
                    "Tesla also plans to begin Megapack 3 and Megablock "
                    "production at Megafactory Houston in 2026."
                ),
                citations=(
                    DemoCitationDefinition(
                        section_path=(
                            "Default_Root/TSLA-Q4-2025-Update.pdf-->SUMMARY-->"
                            "Energy generation and storage"
                        ),
                        description="Storage deployment growth",
                        content=(
                            "We achieved our highest quarterly energy storage "
                            "deployments, driven by record Megapack deployments."
                        ),
                    ),
                ),
            ),
            DemoExampleDefinition(
                id="demo-tsla-q4-2025-production-plans",
                question="What production plans does Tesla mention for 2026?",
                answer=(
                    "Tesla says Cybercab, Tesla Semi, and Megapack 3 are on "
                    "schedule for volume production starting in 2026.\n\n"
                    "The same product update also notes that first-generation "
                    "Optimus production lines are being installed before volume "
                    "production."
                ),
                citations=(
                    DemoCitationDefinition(
                        section_path=(
                            "Default_Root/TSLA-Q4-2025-Update.pdf-->OUTLOOK-->"
                            "Product"
                        ),
                        description="2026 production plans",
                        content=(
                            "Cybercab, Tesla Semi and Megapack 3 are on schedule "
                            "for volume production starting in 2026."
                        ),
                    ),
                ),
            ),
        ),
    ),
)


class DemoDocumentService:
    """Serves canonical demo data and copies it into user namespaces."""

    def __init__(
        self,
        *,
        publication_service: RetrievalPublicationService | None = None,
    ) -> None:
        self._publication_service = publication_service or RetrievalPublicationService()

    def get_catalog(self) -> dict[str, Any]:
        """Return the cacheable canonical demo source catalog."""
        return {
            "sources": [
                self._source_catalog_payload(source)
                for source in _DEMO_SOURCE_DEFINITIONS
            ],
        }

    def list_chunks(
        self,
        *,
        demo_source_id: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any] | None:
        """Return paginated canonical demo chunks."""
        source = _get_source_definition(demo_source_id)
        if source is None:
            return None

        chunks = _load_source_chunks(source)
        start = (page - 1) * page_size
        page_chunks = chunks[start : start + page_size]
        return {
            "demo_source_id": source.demo_source_id,
            "canonical_document_id": source.canonical_document_id,
            "title": source.title,
            "mime_type": source.mime_type,
            "chunks": [
                _chunk_payload(source=source, chunk=chunk)
                for chunk in page_chunks
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": len(chunks),
                "total_pages": math.ceil(len(chunks) / page_size) if chunks else 0,
            },
        }

    def get_chunk(
        self,
        *,
        demo_source_id: str,
        demo_chunk_id: str,
    ) -> dict[str, Any] | None:
        """Return one canonical demo chunk by canonical row id or parser chunk id."""
        source = _get_source_definition(demo_source_id)
        if source is None:
            return None

        for chunk in _load_source_chunks(source):
            if demo_chunk_id in {_canonical_chunk_id(source, chunk), chunk["chunk_id"]}:
                return {
                    "demo_source_id": source.demo_source_id,
                    "canonical_document_id": source.canonical_document_id,
                    "chunk": _chunk_payload(source=source, chunk=chunk),
                }

        return None

    def get_original_file_path(self, *, demo_source_id: str) -> Path | None:
        """Return the canonical original file path for a demo source."""
        source = _get_source_definition(demo_source_id)
        if source is None:
            return None

        file_path = _source_directory(source) / "original.pdf"
        return file_path if file_path.is_file() else None

    def get_asset_file_path(
        self,
        *,
        demo_source_id: str,
        asset_path: str,
    ) -> Path | None:
        """Return a canonical parsed media/table asset path."""
        source = _get_source_definition(demo_source_id)
        if source is None:
            return None

        source_directory = _source_directory(source).resolve()
        candidate = (source_directory / asset_path).resolve()
        if not candidate.is_relative_to(source_directory):
            return None

        return candidate if candidate.is_file() else None

    async def materialize_sources(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
        demo_source_ids: list[str],
    ) -> list[MaterializedDemoSource]:
        """Copy selected canonical demo sources into a user namespace."""
        results: list[MaterializedDemoSource] = []
        for demo_source_id in _deduplicate_source_ids(demo_source_ids):
            source = _require_source_definition(demo_source_id)
            result = await self._materialize_source(
                db,
                user_id=user_id,
                namespace=namespace,
                source=source,
            )
            results.append(result)

        await db.commit()
        return results

    async def _materialize_source(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
        source: DemoSourceDefinition,
    ) -> MaterializedDemoSource:
        existing = await self._get_existing_materialization(
            db,
            user_id=user_id,
            namespace=namespace,
            demo_source_id=source.demo_source_id,
        )
        if existing is not None and await self._is_active_document(
            db,
            document_id=existing.document_id,
        ):
            return _materialized_source_payload(
                source=source,
                document_id=existing.document_id,
                status="existing",
            )

        document_id = f"doc_{uuid4().hex[:12]}"
        job_id = f"job_demo_{uuid4().hex[:12]}"
        job_result_id = str(uuid4())
        timestamp = _utc_now()

        db.add(
            Job(
                job_id=job_id,
                user_id=user_id,
                job_type="demo_materialization",
                status="done",
                source_type="demo",
                webhook_enabled=False,
                job_metadata={
                    "document_id": document_id,
                    "namespace": namespace,
                    "source_type": "demo",
                    "source_file_name": source.title,
                    "demo_source_id": source.demo_source_id,
                },
                version=0,
                created_at=timestamp,
                updated_at=timestamp,
                credits_charged=0,
                billing_status="skipped",
            )
        )
        db.add(
            JobResult(
                id=job_result_id,
                job_id=job_id,
                delivery_mode="inline",
                document_metadata={
                    "source_file_name": source.title,
                    "demo_source_id": source.demo_source_id,
                },
                inline_payload={"source": "canonical_demo"},
                result_s3_key=None,
                result_size=0,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        await db.flush()
        chunks = _load_source_chunks(source)
        await db.run_sync(
            lambda sync_db: self._publication_service.publish_document_state(
                sync_db,
                job_id=job_id,
                job_result_id=job_result_id,
                chunks=[dict(chunk) for chunk in chunks],
            )
        )
        await db.flush()

        if existing is None:
            db.add(
                DemoMaterialization(
                    user_id=user_id,
                    namespace=namespace,
                    demo_source_id=source.demo_source_id,
                    document_id=document_id,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        else:
            existing.document_id = document_id
            existing.updated_at = timestamp
        await db.flush()
        return _materialized_source_payload(
            source=source,
            document_id=document_id,
            status="created",
        )

    async def _get_existing_materialization(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
        demo_source_id: str,
    ) -> DemoMaterialization | None:
        result = await db.execute(
            select(DemoMaterialization)
            .where(DemoMaterialization.user_id == user_id)
            .where(DemoMaterialization.namespace == namespace)
            .where(DemoMaterialization.demo_source_id == demo_source_id)
            .with_for_update()
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _is_active_document(
        self,
        db: AsyncSession,
        *,
        document_id: str,
    ) -> bool:
        result = await db.execute(
            select(Document.document_id)
            .where(Document.document_id == document_id)
            .where(Document.status == "active")
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    def _source_catalog_payload(self, source: DemoSourceDefinition) -> dict[str, Any]:
        return {
            "demo_source_id": source.demo_source_id,
            "canonical_document_id": source.canonical_document_id,
            "title": source.title,
            "mime_type": source.mime_type,
            "size_bytes": source.size_bytes,
            "status": "ready",
            "chunk_count": source.chunk_count,
            "original_file": {
                "url": f"/api/v1/demo/sources/{source.demo_source_id}/original",
                "mime_type": source.mime_type,
                "size_bytes": source.size_bytes,
                "can_download": False,
            },
            "examples": [
                self._example_payload(source=source, example=example)
                for example in source.examples
            ],
        }

    def _example_payload(
        self,
        *,
        source: DemoSourceDefinition,
        example: DemoExampleDefinition,
    ) -> dict[str, Any]:
        return {
            "id": example.id,
            "question": example.question,
            "answer": example.answer,
            "citations": [
                _citation_payload(source=source, citation=citation)
                for citation in example.citations
            ],
        }


def _deduplicate_source_ids(demo_source_ids: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for demo_source_id in demo_source_ids:
        normalized = str(demo_source_id).strip()
        if not normalized or normalized in seen:
            continue
        selected.append(normalized)
        seen.add(normalized)
    return selected


def _materialized_source_payload(
    *,
    source: DemoSourceDefinition,
    document_id: str,
    status: str,
) -> MaterializedDemoSource:
    return MaterializedDemoSource(
        demo_source_id=source.demo_source_id,
        document_id=document_id,
        status=status,
        title=source.title,
        mime_type=source.mime_type,
        size_bytes=source.size_bytes,
        chunk_count=source.chunk_count,
    )


def _citation_payload(
    *,
    source: DemoSourceDefinition,
    citation: DemoCitationDefinition,
) -> dict[str, Any]:
    chunk = _resolve_citation_chunk(source=source, citation=citation)
    return {
        "demo_source_id": source.demo_source_id,
        "canonical_document_id": source.canonical_document_id,
        "canonical_chunk_id": _canonical_chunk_id(source, chunk),
        "chunk_id": chunk["chunk_id"],
        "chunk_type": _normalize_chunk_type(chunk.get("type")),
        "content": citation.content,
        "description": citation.description,
        "source": {
            "document_id": source.canonical_document_id,
            "source_file_name": source.title,
            "section_path": citation.section_path,
        },
    }


def _resolve_citation_chunk(
    *,
    source: DemoSourceDefinition,
    citation: DemoCitationDefinition,
) -> dict[str, Any]:
    chunks = _load_source_chunks(source)
    normalized_content = _normalize_text(citation.content)
    if normalized_content:
        for chunk in chunks:
            if normalized_content in _normalize_text(str(chunk.get("content") or "")):
                return chunk

    for chunk in chunks:
        if str(chunk.get("path") or "") == citation.section_path:
            return chunk

    raise ValueError(
        "Demo citation does not resolve to a canonical chunk: "
        f"demo_source_id={source.demo_source_id}, section_path={citation.section_path}"
    )


def _chunk_payload(
    *,
    source: DemoSourceDefinition,
    chunk: dict[str, Any],
) -> dict[str, Any]:
    metadata = _metadata(chunk)
    file_path = _first_string(
        metadata.get("file_path"),
        metadata.get("filePath"),
        chunk.get("file_path"),
        chunk.get("path") if _is_media_chunk(chunk) else None,
    )
    return {
        "id": _canonical_chunk_id(source, chunk),
        "chunk_id": chunk["chunk_id"],
        "chunk_type": _normalize_chunk_type(chunk.get("type")),
        "content": str(chunk.get("content") or ""),
        "section_path": str(chunk.get("path") or "") or None,
        "source_chunk_path": str(chunk.get("path") or "") or None,
        "file_path": file_path,
        "sort_order": _sort_order(source=source, chunk=chunk),
        "metadata": metadata,
        "asset_url": _asset_url(source=source, file_path=file_path),
        "created_at": None,
    }


def _sort_order(
    *,
    source: DemoSourceDefinition,
    chunk: dict[str, Any],
) -> int:
    try:
        return _load_source_chunks(source).index(chunk)
    except ValueError:
        return 0


def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _is_media_chunk(chunk: dict[str, Any]) -> bool:
    return _normalize_chunk_type(chunk.get("type")) in {"image", "table"}


def _canonical_chunk_id(
    source: DemoSourceDefinition,
    chunk: dict[str, Any],
) -> str:
    return f"{source.demo_source_id}:{chunk['chunk_id']}"


def _asset_url(
    *,
    source: DemoSourceDefinition,
    file_path: str | None,
) -> str | None:
    if not file_path:
        return None
    encoded_path = quote(file_path, safe="/")
    return f"/api/v1/demo/sources/{source.demo_source_id}/assets/{encoded_path}"


def _normalize_chunk_type(value: object) -> str:
    raw = str(value or "").strip().split("\n", 1)[0].lower()
    return raw if raw in {"text", "image", "table"} else "text"


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _get_source_definition(demo_source_id: str) -> DemoSourceDefinition | None:
    return next(
        (
            source
            for source in _DEMO_SOURCE_DEFINITIONS
            if source.demo_source_id == demo_source_id
        ),
        None,
    )


def _require_source_definition(demo_source_id: str) -> DemoSourceDefinition:
    source = _get_source_definition(demo_source_id)
    if source is None:
        raise KeyError(demo_source_id)
    return source


def _source_directory(source: DemoSourceDefinition) -> Path:
    return _DATA_ROOT / source.asset_directory


@lru_cache(maxsize=8)
def _load_source_chunks(source: DemoSourceDefinition) -> tuple[dict[str, Any], ...]:
    chunks_path = _source_directory(source) / "chunks.json"
    with chunks_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    chunks = payload.get("chunks") if isinstance(payload, dict) else None
    if not isinstance(chunks, list):
        return ()

    return tuple(
        dict(chunk)
        for chunk in chunks
        if isinstance(chunk, dict) and isinstance(chunk.get("chunk_id"), str)
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
