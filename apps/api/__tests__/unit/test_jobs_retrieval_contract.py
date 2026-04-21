from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from sqlalchemy.exc import IntegrityError

from app.api.v1.routes import jobs
from app.repositories.job_repository import JobRepository
from app.services import job_document_scope_service
from app.services.rate_limit.data_structures import CurrentUser
from shared.core.exceptions.domain_exceptions import NotFoundException
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


def test_jobs_model_does_not_define_active_document_unique_guard():
    from shared.models.database.job import Job

    indexes = {index.name: index for index in Job.__table__.indexes}

    assert "uq_jobs_user_active_document" not in indexes


def test_retrieval_service_v1_migration_drops_legacy_active_document_unique_guard():
    source = (
        Path(__file__).parents[2]
        / "alembic/versions/c3d4e5f6a7b8_add_retrieval_service_v1.py"
    ).read_text(encoding="utf-8")

    assert "drop_index('uq_jobs_user_active_document'" in source
    assert "ON public.jobs" not in source


def _job_integrity_error() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO jobs ...",
        {},
        Exception("generic job insert failure"),
    )


@pytest.mark.asyncio
async def test_job_repository_rolls_back_and_propagates_integrity_errors():
    class _Db:
        def add(self, _job):
            return None

        async def commit(self):
            raise _job_integrity_error()

        async def rollback(self):
            self.rolled_back = True

    db = _Db()

    with pytest.raises(IntegrityError):
        await JobRepository().create_job(
            db=db,
            user_id="u_test",
            job_type="kb_management",
            source_type="file",
            metadata={"document_id": "doc_123"},
        )

    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_create_job_update_allows_concurrent_non_terminal_job_for_same_document(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)
    monkeypatch.setattr(
        jobs,
        "find_active_job_for_document",
        AsyncMock(return_value=type("Job", (), {"job_id": "job_active"})()),
        raising=False,
    )

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
    monkeypatch.setattr(job_document_scope_service, "DocumentRepository", lambda: _DocumentRepo())

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

    assert response.document_id == "doc_123"
    assert response.namespace == "support-center"
    assert captured["metadata"]["document_id"] == "doc_123"
    assert captured["metadata"]["namespace"] == "support-center"


@pytest.mark.asyncio
async def test_create_job_defaults_namespace_and_generates_document_id_for_new_documents(monkeypatch):
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
    assert response.document_id is not None
    assert response.document_id.startswith("doc_")
    assert captured["metadata"]["document_id"] == response.document_id
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
    monkeypatch.setattr(job_document_scope_service, "DocumentRepository", lambda: _DocumentRepo())

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


@pytest.mark.asyncio
async def test_resolve_effective_document_scope_rejects_archived_document_update_target():
    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id == "u_test"
            return type(
                "Document",
                (),
                {
                    "document_id": "doc_123",
                    "namespace": "support-center",
                    "status": "archived",
                },
            )()

    with pytest.raises(NotFoundException) as exc_info:
        await job_document_scope_service.resolve_effective_document_scope(
            object(),
            user_id="u_test",
            document_id="doc_123",
            requested_namespace=None,
            repository=_DocumentRepo(),
        )

    assert exc_info.value.details == {"resource": "Document", "id": "doc_123"}


@pytest.mark.asyncio
async def test_create_job_returns_404_when_update_target_document_is_missing(
    authenticated_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id
            return None

    monkeypatch.setattr(
        job_document_scope_service,
        "DocumentRepository",
        lambda: _DocumentRepo(),
    )

    response = await authenticated_client.post(
        "/v1/jobs",
        json={
            "source_type": "file",
            "file_name": "doc.pdf",
            "document_id": "doc_123",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Document not found"


@pytest.mark.asyncio
async def test_create_job_returns_404_when_update_target_document_is_archived(
    authenticated_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id
            return type(
                "Document",
                (),
                {
                    "document_id": "doc_123",
                    "namespace": "support-center",
                    "status": "archived",
                },
            )()

    class _JobRepo:
        async def create_job(self, **kwargs):
            return type(
                "Job",
                (),
                {
                    "job_id": kwargs["job_id"],
                    "status": kwargs["initial_state"],
                    "created_at": datetime.now(timezone.utc),
                },
            )()

    class _UploadService:
        async def generate_upload_url(self, _job_id, _file_extension):
            return {
                "upload_url": "https://example.com/upload",
                "upload_headers": {},
                "expires_in": 3600,
            }

    monkeypatch.setattr(
        job_document_scope_service,
        "DocumentRepository",
        lambda: _DocumentRepo(),
    )
    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())
    monkeypatch.setattr(jobs, "FileUploadService", lambda: _UploadService())
    monkeypatch.setattr(
        "shared.services.redis.job_metadata_service.JobMetadataService.save_metadata",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.redis.JobInfoRedisService.save_job_info",
        AsyncMock(),
    )

    response = await authenticated_client.post(
        "/v1/jobs",
        json={
            "source_type": "file",
            "file_name": "doc.pdf",
            "document_id": "doc_123",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Document not found"


def test_jobs_routes_keep_document_scope_logic_out_of_router():
    source = (
        Path(__file__).parents[2]
        / "app/api/v1/routes/jobs.py"
    ).read_text(encoding="utf-8")

    assert "class DocumentRepository" not in source
    assert "async def resolve_effective_document_scope" not in source
    assert "find_active_job_for_document(" not in source
    assert "raise_document_ingestion_conflict(" not in source


@pytest.mark.asyncio
async def test_get_jobs_list_route_uses_canonical_v1_path(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )

    created_at = datetime.now(timezone.utc)

    class _JobRepo:
        async def count_jobs_by_user(self, **_kwargs):
            return 1

        async def get_jobs_by_user(self, **_kwargs):
            return [
                type(
                    "Job",
                    (),
                    {
                        "job_id": "job_123",
                        "status": "waiting-file",
                        "source_type": "file",
                        "job_result": None,
                        "created_at": created_at,
                        "updated_at": created_at,
                        "credits_charged": 0,
                        "error_code": None,
                        "error_message": None,
                    },
                )()
            ]

        async def get_job_metadata(self, _db, _job_id, _redis_service):
            return {
                "original_request": {
                    "file_name": "jobs-list-smoke.pdf",
                    "parsing_params": {
                        "model": "base",
                        "ocr_enabled": False,
                    },
                }
            }

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())

    response = await authenticated_client.get("/v1/jobs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["jobs"][0]["job_id"] == "job_123"
    assert payload["jobs"][0]["status"] == "waiting-file"
