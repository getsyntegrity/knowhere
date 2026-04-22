from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.api.v1.routes import jobs
from app.repositories.job_repository import JobRepository
from app.services import job_document_scope_service
from app.services.rate_limit.data_structures import CurrentUser
from shared.core.exceptions.domain_exceptions import ConflictException, NotFoundException
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


def test_find_active_job_for_document_query_compiles_for_postgres():
    statement = job_document_scope_service.build_active_job_for_document_query(
        user_id="u_test",
        document_id="doc_123",
    )

    compiled = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert ".astext" not in compiled
    assert "document_id" in compiled


def test_jobs_model_defines_active_document_unique_guard():
    from shared.models.database.job import Job

    indexes = {index.name: index for index in Job.__table__.indexes}

    assert "uq_jobs_user_active_document" in indexes
    index_sql = str(indexes["uq_jobs_user_active_document"].expressions[1])
    where_sql = str(indexes["uq_jobs_user_active_document"].dialect_options["postgresql"]["where"])
    assert "job_metadata ->> 'document_id'" in index_sql
    assert "(job_metadata ->> 'document_id') IS NOT NULL" in where_sql


def test_retrieval_service_v1_migration_keeps_active_document_unique_guard():
    source = (
        Path(__file__).parents[2]
        / "alembic/versions/c3d4e5f6a7b8_add_retrieval_service_v1.py"
    ).read_text(encoding="utf-8")

    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_user_active_document" in source
    assert "DROP INDEX IF EXISTS uq_jobs_user_active_document" in source


def _job_integrity_error() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO jobs ...",
        {},
        Exception("generic job insert failure"),
    )


def _active_document_integrity_error() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO jobs ...",
        {},
        Exception("duplicate key value violates unique constraint uq_jobs_user_active_document"),
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
async def test_create_file_job_translates_active_document_unique_race(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))

    class _JobRepo:
        async def create_job(self, **_kwargs):
            raise _active_document_integrity_error()

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id == "u_test"
            return type("Document", (), {"document_id": "doc_123", "namespace": "support-center"})()

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())
    monkeypatch.setattr(job_document_scope_service, "DocumentRepository", lambda: _DocumentRepo())

    payload = JobCreate(
        source_type="file",
        file_name="doc.pdf",
        document_id="doc_123",
        parsing_params=ParsingParams(),
    )
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    with pytest.raises(ConflictException) as exc_info:
        await jobs.create_job(
            payload=payload,
            http_request=_make_http_request(),
            current_user=current_user,
            db=object(),
        )

    assert exc_info.value.details == {
        "reason": "ABORTED",
        "resource": "Document",
        "id": "doc_123",
    }


@pytest.mark.asyncio
async def test_create_url_job_translates_active_document_unique_race(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "resolve_file_extension_async", AsyncMock(return_value=".pdf"))
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))

    class _JobRepo:
        async def create_job(self, **_kwargs):
            raise _active_document_integrity_error()

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id == "u_test"
            return type("Document", (), {"document_id": "doc_123", "namespace": "support-center"})()

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())
    monkeypatch.setattr(job_document_scope_service, "DocumentRepository", lambda: _DocumentRepo())

    payload = JobCreate(
        source_type="url",
        source_url="https://example.com/doc.pdf",
        document_id="doc_123",
        parsing_params=ParsingParams(),
    )
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    with pytest.raises(ConflictException) as exc_info:
        await jobs.create_job(
            payload=payload,
            http_request=_make_http_request(),
            current_user=current_user,
            db=object(),
        )

    assert exc_info.value.details == {
        "reason": "ABORTED",
        "resource": "Document",
        "id": "doc_123",
    }


@pytest.mark.asyncio
async def test_create_job_defaults_namespace_and_generates_document_id_for_new_documents(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))

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
    assert isinstance(captured["metadata"]["document_id"], str)
    assert captured["metadata"]["document_id"].startswith("doc_")
    assert captured["metadata"]["namespace"] == "default"


@pytest.mark.asyncio
async def test_create_job_update_omitting_namespace_keeps_existing_document_namespace(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))

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
async def test_create_job_update_rejects_concurrent_non_terminal_job_for_same_document(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_123"
            assert user_id == "u_test"
            return type("Document", (), {"document_id": "doc_123", "namespace": "support-center"})()

    monkeypatch.setattr(job_document_scope_service, "DocumentRepository", lambda: _DocumentRepo())
    monkeypatch.setattr(
        jobs,
        "find_active_job_for_document",
        AsyncMock(return_value=type("Job", (), {"job_id": "job_active"})()),
    )

    payload = JobCreate(
        source_type="file",
        file_name="doc.pdf",
        document_id="doc_123",
        parsing_params=ParsingParams(),
    )
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    with pytest.raises(ConflictException) as exc_info:
        await jobs.create_job(
            payload=payload,
            http_request=_make_http_request(),
            current_user=current_user,
            db=object(),
        )

    assert exc_info.value.details == {
        "reason": "ABORTED",
        "resource": "Document",
        "id": "doc_123",
    }


@pytest.mark.asyncio
async def test_create_job_rejects_prepublication_active_document_id_before_document_exists(monkeypatch):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )
    monkeypatch.setattr(jobs, "enforce_job_creation_capacity", AsyncMock())
    monkeypatch.setattr(jobs, "validate_file_type", lambda _file_name: True)

    class _DocumentRepo:
        async def get_document(self, _db, *, document_id, user_id):
            assert document_id == "doc_prepub"
            assert user_id == "u_test"
            return None

    monkeypatch.setattr(job_document_scope_service, "DocumentRepository", lambda: _DocumentRepo())
    monkeypatch.setattr(
        jobs,
        "find_active_job_for_document",
        AsyncMock(return_value=type("Job", (), {"job_id": "job_waiting"})()),
    )

    payload = JobCreate(
        source_type="file",
        file_name="doc.pdf",
        document_id="doc_prepub",
        parsing_params=ParsingParams(),
    )
    current_user = CurrentUser(user_id="u_test", user_tier="free")

    with pytest.raises(ConflictException) as exc_info:
        await jobs.create_job(
            payload=payload,
            http_request=_make_http_request(),
            current_user=current_user,
            db=object(),
        )

    assert exc_info.value.details == {
        "reason": "ABORTED",
        "resource": "Document",
        "id": "doc_prepub",
    }


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
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))

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
    monkeypatch.setattr(jobs, "find_active_job_for_document", AsyncMock(return_value=None))

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
    assert "async def find_active_job_for_document" not in source
    assert "def raise_document_ingestion_conflict" not in source


@pytest.mark.asyncio
async def test_get_job_result_omits_reserved_document_id_for_new_ingestion_until_publication(
    authenticated_client, mock_user_id, monkeypatch,
):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )

    created_at = datetime.now(timezone.utc)

    class _JobRepo:
        async def get_job_by_id(self, _db, job_id):
            assert job_id == "job_123"
            return type(
                "Job",
                (),
                {
                    "job_id": "job_123",
                    "user_id": mock_user_id,
                    "status": "done",
                    "source_type": "url",
                    "job_result": None,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "credits_charged": 0,
                    "error_code": None,
                    "error_message": None,
                },
            )()

        async def get_job_metadata(self, _db, _job_id, _redis_service):
            return {
                "namespace": "support-center",
                "document_id": "doc_123",
                "data_id": "caller-data",
                "original_request": {
                    "source_url": "https://example.com/doc.pdf",
                    "parsing_params": {
                        "model": "base",
                        "ocr_enabled": False,
                    },
                },
            }

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())

    response = await authenticated_client.get("/v1/jobs/job_123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["namespace"] == "support-center"
    assert payload["document_id"] is None
    assert payload["data_id"] == "caller-data"


@pytest.mark.asyncio
async def test_get_job_result_returns_published_document_id_after_success(
    authenticated_client, mock_user_id, monkeypatch,
):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )

    created_at = datetime.now(timezone.utc)

    class _JobRepo:
        async def get_job_by_id(self, _db, job_id):
            assert job_id == "job_123"
            return type(
                "Job",
                (),
                {
                    "job_id": "job_123",
                    "user_id": mock_user_id,
                    "status": "done",
                    "source_type": "url",
                    "job_result": type(
                        "JobResult",
                        (),
                        {
                            "document_id": "doc_123",
                            "result_s3_key": None,
                            "inline_payload": None,
                        },
                    )(),
                    "created_at": created_at,
                    "updated_at": created_at,
                    "credits_charged": 0,
                    "error_code": None,
                    "error_message": None,
                },
            )()

        async def get_job_metadata(self, _db, _job_id, _redis_service):
            return {
                "namespace": "support-center",
                "document_id": "doc_123",
                "data_id": "caller-data",
                "original_request": {
                    "source_url": "https://example.com/doc.pdf",
                    "parsing_params": {
                        "model": "base",
                        "ocr_enabled": False,
                    },
                },
            }

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())

    response = await authenticated_client.get("/v1/jobs/job_123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["namespace"] == "support-center"
    assert payload["document_id"] == "doc_123"
    assert payload["data_id"] == "caller-data"


@pytest.mark.asyncio
async def test_get_job_result_returns_existing_document_id_for_update_flow(
    authenticated_client, mock_user_id, monkeypatch,
):
    monkeypatch.setattr(
        "shared.services.redis.RedisServiceFactory.get_service",
        lambda: object(),
    )

    created_at = datetime.now(timezone.utc)

    class _JobRepo:
        async def get_job_by_id(self, _db, job_id):
            assert job_id == "job_123"
            return type(
                "Job",
                (),
                {
                    "job_id": "job_123",
                    "user_id": mock_user_id,
                    "status": "running",
                    "source_type": "url",
                    "job_result": None,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "credits_charged": 0,
                    "error_code": None,
                    "error_message": None,
                },
            )()

        async def get_job_metadata(self, _db, _job_id, _redis_service):
            return {
                "namespace": "support-center",
                "document_id": "doc_123",
                "data_id": "caller-data",
                "original_request": {
                    "source_url": "https://example.com/doc.pdf",
                    "document_id": "doc_123",
                    "parsing_params": {
                        "model": "base",
                        "ocr_enabled": False,
                    },
                },
            }

    monkeypatch.setattr(jobs, "JobRepository", lambda: _JobRepo())

    response = await authenticated_client.get("/v1/jobs/job_123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["namespace"] == "support-center"
    assert payload["document_id"] == "doc_123"
    assert payload["data_id"] == "caller-data"


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
