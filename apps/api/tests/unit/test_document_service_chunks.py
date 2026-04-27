from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("USERS_DATA_PATH", "/tmp")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")

from app.repositories.document_repository import DocumentRepository  # noqa: E402
import app.services.document_service as document_service_module  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402


class _FakeDocumentRepository:
    def __init__(self) -> None:
        self.document = SimpleNamespace(
            document_id="doc_123",
            namespace="default",
            current_job_result_id="result_123",
        )
        self.total_chunks = 2
        self.chunks: list[tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]] = [
            (
                SimpleNamespace(
                    id="dchk_1",
                    chunk_id="parser-1",
                    chunk_type="text",
                    content="First chunk",
                    section_id="sec_1",
                    source_chunk_path="Chapter 1/Intro",
                    file_path=None,
                    chunk_metadata={"summary": "Intro"},
                    sort_order=0,
                    created_at=datetime(2026, 4, 27, 3, 0, 0),
                ),
                SimpleNamespace(section_path="Chapter 1"),
                SimpleNamespace(job_id="job_123"),
            )
        ]
        self.chunk = self.chunks[0]
        self.list_call: dict[str, Any] | None = None

    async def get_document(
        self, _db: object, *, document_id: str, user_id: str
    ) -> SimpleNamespace:
        assert document_id == "doc_123"
        assert user_id == "user_123"
        return self.document

    async def count_current_document_chunks(
        self,
        _db: object,
        *,
        document_id: str,
        job_result_id: str,
        chunk_type: str | None,
    ) -> int:
        assert document_id == "doc_123"
        assert job_result_id == "result_123"
        assert chunk_type == "text"
        return self.total_chunks

    async def list_current_document_chunks(
        self,
        _db: object,
        *,
        document_id: str,
        job_result_id: str,
        limit: int,
        offset: int,
        chunk_type: str | None,
    ) -> list[tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]]:
        self.list_call = {
            "document_id": document_id,
            "job_result_id": job_result_id,
            "limit": limit,
            "offset": offset,
            "chunk_type": chunk_type,
        }
        return self.chunks

    async def get_current_document_chunk(
        self,
        _db: object,
        *,
        document_id: str,
        job_result_id: str,
        document_chunk_id: str,
    ) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
        assert document_id == "doc_123"
        assert job_result_id == "result_123"
        assert document_chunk_id == "dchk_1"
        return self.chunk


@pytest.mark.asyncio
async def test_list_document_chunks_returns_the_current_revision_page() -> None:
    repository = _FakeDocumentRepository()
    service = DocumentService(repository=cast(DocumentRepository, repository))

    result = await service.list_document_chunks(
        cast(AsyncSession, None),
        user_id="user_123",
        document_id="doc_123",
        page=2,
        page_size=1,
        chunk_type="text",
        include_asset_urls=False,
    )

    assert repository.list_call == {
        "document_id": "doc_123",
        "job_result_id": "result_123",
        "limit": 1,
        "offset": 1,
        "chunk_type": "text",
    }
    assert result == {
        "document_id": "doc_123",
        "namespace": "default",
        "job_result_id": "result_123",
        "job_id": "job_123",
        "chunks": [
            {
                "id": "dchk_1",
                "chunk_id": "parser-1",
                "chunk_type": "text",
                "content": "First chunk",
                "section_id": "sec_1",
                "section_path": "Chapter 1",
                "source_chunk_path": "Chapter 1/Intro",
                "file_path": None,
                "sort_order": 0,
                "metadata": {"summary": "Intro"},
                "asset_url": None,
                "created_at": "2026-04-27T03:00:00",
            }
        ],
        "pagination": {
            "page": 2,
            "page_size": 1,
            "total": 2,
            "total_pages": 2,
        },
    }


@pytest.mark.asyncio
async def test_get_document_chunk_returns_one_current_revision_chunk() -> None:
    repository = _FakeDocumentRepository()
    service = DocumentService(repository=cast(DocumentRepository, repository))

    result = await service.get_document_chunk(
        cast(AsyncSession, None),
        user_id="user_123",
        document_id="doc_123",
        document_chunk_id="dchk_1",
        include_asset_urls=False,
    )

    assert result == {
        "document_id": "doc_123",
        "namespace": "default",
        "job_result_id": "result_123",
        "job_id": "job_123",
        "chunk": {
            "id": "dchk_1",
            "chunk_id": "parser-1",
            "chunk_type": "text",
            "content": "First chunk",
            "section_id": "sec_1",
            "section_path": "Chapter 1",
            "source_chunk_path": "Chapter 1/Intro",
            "file_path": None,
            "sort_order": 0,
            "metadata": {"summary": "Intro"},
            "asset_url": None,
            "created_at": "2026-04-27T03:00:00",
        },
    }


@pytest.mark.asyncio
async def test_get_document_chunk_generates_asset_url_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FakeDocumentRepository()
    chunk, section, job_result = repository.chunk
    chunk.chunk_type = "image"
    chunk.file_path = "images/figure-1.png"
    service = DocumentService(repository=cast(DocumentRepository, repository))

    class _FakeResultStorage:
        def generate_artifact_url(self, *, job_id: str, artifact_ref: str) -> str:
            assert job_id == job_result.job_id
            assert artifact_ref == "images/figure-1.png"
            return "https://assets.example.com/figure-1.png"

    monkeypatch.setattr(
        document_service_module,
        "get_result_storage",
        lambda: _FakeResultStorage(),
    )

    result = await service.get_document_chunk(
        cast(AsyncSession, None),
        user_id="user_123",
        document_id="doc_123",
        document_chunk_id="dchk_1",
        include_asset_urls=True,
    )

    assert result is not None
    response_chunk = cast(dict[str, object], result["chunk"])
    assert response_chunk["section_path"] == section.section_path
    assert response_chunk["asset_url"] == "https://assets.example.com/figure-1.png"
