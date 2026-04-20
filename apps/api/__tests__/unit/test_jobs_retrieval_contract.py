from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import Request

from app.api.v1.routes import jobs
from app.services.rate_limit.data_structures import CurrentUser
from shared.models.schemas.job import JobCreate, ParsingParams


def _make_http_request() -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/jobs",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_create_job_defaults_namespace_for_new_documents(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)

    captured: dict[str, object] = {}

    class _JobRepo:
        async def create_job(self, **kwargs):
            captured["metadata"] = kwargs["metadata"]
            return type(
                "Job",
                (),
                {
                    "job_id": kwargs["job_id"],
                    "status": kwargs["initial_state"],
                    "created_at": datetime.now(timezone.utc),
                },
            )()

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())

    class _UploadService:
        async def generate_upload_url(self, _job_id, _file_extension):
            return {
                "upload_url": "https://example.com/upload",
                "upload_headers": {},
                "expires_in": 3600,
            }

    monkeypatch.setattr(jobs, "FileUploadService", lambda: _UploadService())
    monkeypatch.setattr(
        "shared.services.redis.job_metadata_service.JobMetadataService.save_metadata",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.redis.JobInfoRedisService.save_job_info",
        AsyncMock(),
    )

    payload = JobCreate(
        source_type="file",
        file_name="doc.pdf",
        parsing_params=ParsingParams(),
    )
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    response = await jobs.create_job(
        payload=payload,
        http_request=_make_http_request(),
        current_user=current_user,
        db=object(),
    )

    assert response.source_type == "file"
    assert response.namespace == "default"
    assert response.document_id is None
    assert captured["metadata"]["namespace"] == "default"


@pytest.mark.asyncio
async def test_create_job_update_omitting_namespace_keeps_existing_document_namespace(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)

    captured: dict[str, object] = {}

    class _JobRepo:
        async def create_job(self, **kwargs):
            captured["metadata"] = kwargs["metadata"]
            return type(
                "Job",
                (),
                {
                    "job_id": kwargs["job_id"],
                    "status": kwargs["initial_state"],
                    "created_at": datetime.now(timezone.utc),
                },
            )()

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id == "u_test"
            return type("Document", (), {"document_id": "doc_123", "namespace": "support-center"})()

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())
    monkeypatch.setattr(jobs, "DocumentRepository", lambda: _DocumentRepo())

    class _UploadService:
        async def generate_upload_url(self, _job_id, _file_extension):
            return {
                "upload_url": "https://example.com/upload",
                "upload_headers": {},
                "expires_in": 3600,
            }

    monkeypatch.setattr(jobs, "FileUploadService", lambda: _UploadService())
    monkeypatch.setattr(
        "shared.services.redis.job_metadata_service.JobMetadataService.save_metadata",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.redis.JobInfoRedisService.save_job_info",
        AsyncMock(),
    )

    payload = JobCreate(
        source_type="file",
        file_name="doc.pdf",
        document_id="doc_123",
        parsing_params=ParsingParams(),
    )
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    response = await jobs.create_job(
        payload=payload,
        http_request=_make_http_request(),
        current_user=current_user,
        db=object(),
    )

    assert response.namespace == "support-center"
    assert response.document_id == "doc_123"
    assert captured["metadata"]["namespace"] == "support-center"
